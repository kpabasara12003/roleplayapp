"""Durable turn stages, database job claims, and commit-time fencing."""
import json
import uuid
import random
from contextvars import ContextVar
from dataclasses import dataclass
from shared.db.postgres import transaction, fetch_one, fetch_all, execute, execute_returning

job_claim = ContextVar('job_claim', default=None)

class StaleJob(RuntimeError):
    pass

@dataclass(frozen=True)
class Claim:
    id: str
    owner: str
    fence: int
    turn_id: str
    stage: str

async def enqueue(turn_id, stage, payload):
    jid = str(uuid.uuid5(uuid.UUID(str(turn_id)), stage))
    payload = {**payload, 'turn_id':str(turn_id), 'job_id':jid}
    from opentelemetry.propagate import inject
    payload['_trace']={}
    inject(payload['_trace'])
    await execute('INSERT INTO jobs(id,turn_id,stage,payload) VALUES (%s,%s,%s,%s::jsonb) ON CONFLICT(turn_id,stage) DO NOTHING', (jid,turn_id,stage,json.dumps(payload)))
    await execute('INSERT INTO event_outbox(subject,payload,event_key) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING', ('roleplay.events.jobs.'+stage,json.dumps(payload).encode(),'job-'+jid))

async def claim_job(job_id):
    owner = str(uuid.uuid4())
    row = await execute_returning("""UPDATE jobs SET status='running',owner=%s,fence=fence+1,attempts=attempts+1,
        lease_until=now()+interval '60 seconds' WHERE id=%s AND available_at<=now()
        AND (status='pending' OR (status='running' AND lease_until<now())) RETURNING *""", (owner,job_id))
    if not row:
        return None
    return Claim(str(row['id']),owner,row['fence'],str(row['turn_id']),row['stage'])

async def assert_claim(claim):
    row = await fetch_one("""SELECT j.id FROM jobs j JOIN turns t ON t.id=j.turn_id
        WHERE j.id=%s AND j.owner=%s AND j.fence=%s AND j.status='running' AND j.lease_until>clock_timestamp()
        AND t.status IN ('validating','generating','narrating') FOR UPDATE OF j,t""", (claim.id,claim.owner,claim.fence))
    if not row:
        raise StaleJob('Worker no longer owns this turn stage')
    version = await fetch_one('SELECT c.state_version,t.state_version AS expected FROM turns t JOIN conversations c ON c.id=t.conversation_id WHERE t.id=%s FOR UPDATE OF c', (claim.turn_id,))
    if not version or version['state_version'] != version['expected']:
        raise StaleJob('Scene state version has changed')

async def heartbeat(claim):
    count = await execute("UPDATE jobs SET lease_until=now()+interval '60 seconds' WHERE id=%s AND owner=%s AND fence=%s AND status='running' AND lease_until>clock_timestamp()", (claim.id,claim.owner,claim.fence))
    if count != 1:
        raise StaleJob('Job lease expired')

async def complete_job(payload=None, blocked=None):
    claim = job_claim.get()
    if claim is None:
        return
    async with transaction():
        await assert_claim(claim)
        row = await fetch_one('SELECT * FROM turns WHERE id=%s', (claim.turn_id,))
        await execute("UPDATE jobs SET status='completed',result=%s::jsonb,completed_at=now(),owner=NULL,lease_until=NULL WHERE id=%s", (json.dumps(payload or {}),claim.id))
        next_stage = {'validate':'actor', 'actor':'director'}.get(claim.stage)
        status = 'blocked' if blocked else {'validate':'generating','actor':'narrating','director':'completed'}[claim.stage]
        job=await fetch_one('SELECT payload FROM jobs WHERE id=%s',(claim.id,))
        regenerated=claim.stage=='actor' and job['payload'].get('regenerate',False)
        if regenerated:
            next_stage=None
            status='completed'
        phase='before_reply' if claim.stage=='validate' and not blocked else 'after_turn' if status=='completed' else None
        if phase:
            from shared.utils.game_engine import GameEngine
            snapshot=await GameEngine(None).get_state(row['conversation_id'])
            await execute('INSERT INTO turn_checkpoints(turn_id,phase,snapshot) VALUES (%s,%s,%s::jsonb) ON CONFLICT DO NOTHING',(claim.turn_id,phase,json.dumps(snapshot)))
        if claim.stage=='validate':
            await execute("UPDATE messages SET metadata=COALESCE(metadata,'{}'::jsonb)||%s::jsonb WHERE id=%s",(json.dumps({'action_status':'blocked' if blocked else 'accepted','failure_reason':blocked}),row['user_message_id']))
        await execute('UPDATE turns SET status=%s,failure=%s,updated_at=now() WHERE id=%s', (status,blocked,claim.turn_id))
        if next_stage and not blocked:
            data = {'conversation_id':row['conversation_id'],'user_id':row['user_id'],'content':row['content'],
                    'message_id':row['user_message_id'],'event_id':str(row['id']),**(payload or {})}
            await enqueue(claim.turn_id,next_stage,data)
        if blocked or claim.stage=='director' or regenerated:
            packet = {'event':'action_blocked' if blocked else 'director_state_change','conversation_id':row['conversation_id'],
                      'turn_id':claim.turn_id,'payload':{'reason':blocked} if blocked else {'state':'completed','message':'Turn completed'}}
            await execute('INSERT INTO event_outbox(subject,payload) VALUES (%s,%s)', ('roleplay.chat.stream.'+str(row['conversation_id']),json.dumps(packet).encode()))

async def fail_job(claim, error):
    async with transaction():
        row = await fetch_one("SELECT attempts,turn_id FROM jobs WHERE id=%s AND owner=%s AND fence=%s AND status='running' FOR UPDATE", (claim.id,claim.owner,claim.fence))
        if not row:
            return
        dead = row['attempts'] >= 5
        delay=min(60,2**row['attempts'])+random.uniform(0,1)
        await execute("UPDATE jobs SET status=%s,last_error=%s,owner=NULL,lease_until=NULL,available_at=now()+(%s * interval '1 second') WHERE id=%s", ('dead' if dead else 'pending',type(error).__name__+': '+str(error)[:500],delay,claim.id))
        if dead:
            turn = await fetch_one("UPDATE turns SET status='failed',failure=%s,updated_at=now() WHERE id=%s RETURNING conversation_id", ('Stage failed after five attempts: '+claim.stage,claim.turn_id))
            packet = {'event':'state_change','conversation_id':turn['conversation_id'],'turn_id':claim.turn_id,
                      'payload':{'state':'error','error_detail':'Turn failed; committed actions are preserved. Retry the failed turn.'}}
            await execute('INSERT INTO event_outbox(subject,payload) VALUES (%s,%s)', ('roleplay.chat.stream.'+str(turn['conversation_id']),json.dumps(packet).encode()))
            await execute('INSERT INTO event_outbox(subject,payload) VALUES (%s,%s)', ('roleplay.events.deadletter.job',json.dumps({'job_id':claim.id,'turn_id':claim.turn_id,'stage':claim.stage,'error':str(error)[:500]}).encode()))

async def recover_jobs():
    """Re-notify unfinished jobs even if their original broker message expired."""
    async with transaction():
        rows = await fetch_all("""SELECT * FROM jobs WHERE ((status='pending' AND available_at<=now())
            OR (status='running' AND lease_until<now())) AND (last_notified_at IS NULL OR last_notified_at<now()-interval '15 seconds')
            ORDER BY created_at LIMIT 100 FOR UPDATE SKIP LOCKED""")
        for row in rows:
            await execute('INSERT INTO event_outbox(subject,payload) VALUES (%s,%s)', ('roleplay.events.jobs.'+row['stage'],json.dumps(row['payload']).encode()))
            await execute('UPDATE jobs SET last_notified_at=now() WHERE id=%s', (row['id'],))
