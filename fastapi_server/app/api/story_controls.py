"""Explicit memory control and isolated story forks. Regeneration never repeats mechanics."""
import json
import uuid
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,Field
from shared.db.postgres import transaction,fetch_one,fetch_all,execute,execute_returning
from shared.utils.playthroughs import owned
from fastapi_server.app.api.users import get_current_user

router=APIRouter(prefix='/conversations',tags=['Story controls'])

class Note(BaseModel):
    content:str=Field(min_length=1,max_length=2000)
    pinned:bool=True

@router.get('/{cid}/memories')
async def memories(cid:int,user:dict=Depends(get_current_user)):
    await owned(cid,user['id'])
    return {'facts':await fetch_all('SELECT * FROM memory_facts WHERE conversation_id=%s ORDER BY id',(cid,)),
            'notes':await fetch_all('SELECT * FROM memory_notes WHERE conversation_id=%s ORDER BY id',(cid,))}

@router.post('/{cid}/memories/notes',status_code=201)
async def note(cid:int,payload:Note,user:dict=Depends(get_current_user)):
    await owned(cid,user['id'])
    return await execute_returning('INSERT INTO memory_notes(conversation_id,content,pinned) VALUES (%s,%s,%s) RETURNING *',(cid,payload.content,payload.pinned))

class FactUpdate(BaseModel):
    content:str|None=Field(default=None,min_length=1,max_length=1000)
    pinned:bool=False
    forgotten:bool=False
    known_by:list[str]|None=Field(default=None,max_length=100)

@router.patch('/{cid}/memories/{fact_id}')
async def change_fact(cid:int,fact_id:int,payload:FactUpdate,user:dict=Depends(get_current_user)):
    await owned(cid,user['id'])
    row=await execute_returning('''UPDATE memory_facts SET content=COALESCE(%s,content),pinned=%s,suppressed=%s,known_by=%s,
       manual=true,updated_at=now() WHERE id=%s AND conversation_id=%s RETURNING *''',(payload.content,payload.pinned,payload.forgotten,payload.known_by,fact_id,cid))
    if not row: raise HTTPException(404,'Memory not found')
    return row

@router.delete('/{cid}/memories/notes/{note_id}',status_code=204)
async def remove_note(cid:int,note_id:int,user:dict=Depends(get_current_user)):
    await owned(cid,user['id'])
    await execute('DELETE FROM memory_notes WHERE id=%s AND conversation_id=%s',(note_id,cid))

class Fork(BaseModel):
    request_id:uuid.UUID=Field(default_factory=uuid.uuid4)
    initial:bool=False
    turn_id:uuid.UUID|None=None
    title:str=Field(default='Story fork',min_length=1,max_length=100)

async def fork_at(cid,payload,user,omit_reply=False):
    async with transaction() as conn:
        await conn.execute('SELECT pg_advisory_xact_lock(%s)',(cid,))
        source=await owned(cid,user['id'],True)
        previous=await fetch_one('SELECT * FROM conversations WHERE user_id=%s AND start_request_id=%s',(user['id'],payload.request_id))
        if previous:
            if previous['parent_conversation_id']!=cid or previous['start_request_payload']!={'fork':payload.model_dump(mode='json'),'omit_reply':omit_reply}: raise HTTPException(409,'Fork request ID already used')
            return previous,await fetch_one('SELECT * FROM turns WHERE id=%s',(payload.turn_id,)) if payload.turn_id else await fetch_one("SELECT * FROM turns WHERE conversation_id=%s AND status='completed' ORDER BY created_at DESC LIMIT 1",(cid,))
        if await fetch_one("SELECT id FROM turns WHERE conversation_id=%s AND status IN ('validating','generating','narrating')",(cid,)):
            raise HTTPException(409,'Wait for the current turn before branching')
        turn=None if payload.initial else await fetch_one("SELECT * FROM turns WHERE conversation_id=%s AND status='completed' AND (%s::uuid IS NULL OR id=%s) ORDER BY created_at DESC LIMIT 1",(cid,payload.turn_id,payload.turn_id))
        if payload.turn_id and not turn: raise HTTPException(404,'Completed turn not found')
        version=turn['state_version'] if turn else 0
        event=await fetch_one('SELECT snapshot FROM state_events WHERE conversation_id=%s AND state_version<=%s ORDER BY state_version DESC LIMIT 1',(cid,version))
        if not event: raise HTTPException(409,'No checkpoint for this turn; play a turn before branching')
        greeting=await fetch_one("SELECT max(id) AS id FROM messages WHERE conversation_id=%s AND metadata->>'type'='greeting'",(cid,))
        cutoff=turn['user_message_id'] if turn else (greeting['id'] or 0)
        if turn and not omit_reply:
            last=await fetch_one('SELECT max(id) AS id FROM messages WHERE conversation_id=%s AND event_id=ANY(%s)',(cid,['actor-'+str(turn['id']),'director-'+str(turn['id'])]))
            cutoff=max(cutoff,last['id'] or 0)
        state=event['snapshot']
        new=await execute_returning('''INSERT INTO conversations(scenario_id,user_id,ai_character_id,user_character_id,current_place,"current_time",scenario_version_id,title,preferences,persona,parent_conversation_id,fork_message_id)
          VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s) RETURNING *''',(source['scenario_id'],user['id'],source['ai_character_id'],source['user_character_id'],state['place'],state['time'],source['scenario_version_id'],payload.title,json.dumps(source['preferences']),json.dumps(source['persona']),cid,cutoff))
        await execute('UPDATE conversations SET start_request_id=%s WHERE id=%s',(payload.request_id,new['id']))
        await execute('UPDATE conversations SET start_request_payload=%s::jsonb WHERE id=%s',(json.dumps({'fork':payload.model_dump(mode='json'),'omit_reply':omit_reply}),new['id']))
        await execute('INSERT INTO game_states(conversation_id,inventory,relationships,quest_flags,runtime) VALUES (%s,%s::jsonb,%s::jsonb,%s,%s::jsonb)',(new['id'],json.dumps(state['inventory']),json.dumps(state['relationships']),state['quest_flags'],json.dumps(state.get('runtime',{}))))
        state={**state,'state_version':0}
        await execute("INSERT INTO state_events(conversation_id,operation_id,state_version,snapshot,changes) VALUES (%s,%s,0,%s::jsonb,'[]')",(new['id'],'initial-'+str(new['id']),json.dumps(state)))
        await execute('''INSERT INTO messages(conversation_id,sender,content,metadata) SELECT %s,sender,content,COALESCE(metadata,'{}'::jsonb)||jsonb_build_object('fork_source_id',id) FROM messages
          WHERE conversation_id=%s AND id<=%s AND NOT superseded AND COALESCE(metadata->>'action_status','accepted') NOT IN ('pending','blocked') ORDER BY id''',(new['id'],cid,cutoff))
        await execute('''INSERT INTO memory_facts(conversation_id,fact_key,content,kind,source_message_id,pinned,suppressed,manual,known_by)
          SELECT %s,f.fact_key,f.content,f.kind,m.id,f.pinned,f.suppressed,f.manual,f.known_by FROM memory_facts f JOIN messages m ON m.conversation_id=%s AND (m.metadata->>'fork_source_id')::int=f.source_message_id
          WHERE f.conversation_id=%s AND (f.manual OR f.pinned OR f.suppressed)''',(new['id'],new['id'],cid))
        return new,turn

@router.post('/{cid}/fork',status_code=201)
async def fork(cid:int,payload:Fork,user:dict=Depends(get_current_user)):
    new,_=await fork_at(cid,payload,user)
    return new

@router.post('/{cid}/regenerate',status_code=202)
async def regenerate(cid:int,payload:Fork,user:dict=Depends(get_current_user)):
    async with transaction():
        new,old=await fork_at(cid,payload,user,True)
        if not old: raise HTTPException(409,'No reply to regenerate')
        existing=await fetch_one('SELECT id FROM turns WHERE conversation_id=%s ORDER BY created_at DESC LIMIT 1',(new['id'],))
        if existing: return {'conversation':new,'turn_id':existing['id']}
        msg=await fetch_one("SELECT id FROM messages WHERE conversation_id=%s AND sender='user' ORDER BY id DESC LIMIT 1",(new['id'],))
        turn_id=uuid.uuid4()
        await execute("INSERT INTO turns(id,conversation_id,request_id,user_message_id,content,user_id,status,state_version) VALUES (%s,%s,%s,%s,%s,%s,'generating',0)",(turn_id,new['id'],uuid.uuid4(),msg['id'],old['content'],user['id']))
        from shared.utils.turns import enqueue
        await enqueue(turn_id,'actor',{'turn_id':str(turn_id),'event_id':str(turn_id),'conversation_id':new['id'],'user_id':user['id'],'message_id':msg['id'],'content':old['content'],'regenerate':True})
        return {'conversation':new,'turn_id':turn_id}

class Edit(BaseModel):
    turn_id:uuid.UUID
    content:str=Field(min_length=1,max_length=16000)
    request_id:uuid.UUID=Field(default_factory=uuid.uuid4)

@router.post('/{cid}/edit',status_code=202)
async def edit(cid:int,payload:Edit,user:dict=Depends(get_current_user)):
    # Branch at the last completed turn preceding the edited input.
    await owned(cid,user['id'])
    target=await fetch_one('SELECT * FROM turns WHERE id=%s AND conversation_id=%s',(payload.turn_id,cid))
    if not target: raise HTTPException(404,'Turn not found')
    previous=await fetch_one("SELECT id FROM turns WHERE conversation_id=%s AND status='completed' AND created_at<%s ORDER BY created_at DESC LIMIT 1",(cid,target['created_at']))
    async with transaction():
        new,_=await fork_at(cid,Fork(request_id=payload.request_id,turn_id=previous['id'] if previous else None,initial=not previous,title='Edited story'),user)
        from fastapi_server.app.api.chat import send_message,ChatMessageRequest
        accepted=await send_message(ChatMessageRequest(conversation_id=new['id'],content=payload.content,request_id=payload.request_id),user)
        return {'conversation':new,'accepted':accepted}
