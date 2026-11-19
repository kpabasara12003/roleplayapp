"""Saved playthroughs, publication, preferences and player personas."""
import json
import uuid
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,Field
from shared.db.postgres import transaction,fetch_one,fetch_all,execute,execute_returning
from shared.utils.playthroughs import owned,capture_version,effective_preferences
from shared.schemas.playthrough import Preferences,Persona,InitialState
from fastapi_server.app.api.users import get_current_user

router=APIRouter(tags=['Playthroughs'])

class Start(BaseModel):
    scenario_id:int
    ai_character_id:int
    user_character_id:int|None=None
    persona_id:int|None=None
    request_id:uuid.UUID=Field(default_factory=uuid.uuid4)
    preferences:dict=Field(default_factory=dict)

async def start(payload,user):
    async with transaction() as conn:
        await conn.execute('SELECT pg_advisory_xact_lock(%s)',(user['id'],))
        previous=await fetch_one('SELECT * FROM conversations WHERE user_id=%s AND start_request_id=%s',(user['id'],payload.request_id))
        if previous:
            if previous['start_request_payload']!=payload.model_dump(mode='json'):
                raise HTTPException(409,'Start request ID already used')
            return previous
        scene=await fetch_one('SELECT * FROM scenarios WHERE id=%s AND deleted_at IS NULL FOR SHARE',(payload.scenario_id,))
        if not scene or (scene['user_id']!=user['id'] and not scene['is_public']):
            raise HTTPException(404,'Scenario not found')
        if scene['user_id']==user['id']:
            version=await capture_version(scene['id'])
        else:
            version=await fetch_one('SELECT * FROM scenario_versions WHERE scenario_id=%s AND published ORDER BY version DESC LIMIT 1',(scene['id'],))
        if not version:
            raise HTTPException(404,'No published version')
        definition=version['definition']
        ai=next((c for c in definition['cast'] if c['id']==payload.ai_character_id and c['is_ai']),None)
        player=next((c for c in definition['cast'] if c['id']==payload.user_character_id and not c['is_ai']),None)
        if not ai or (payload.user_character_id and not player):
            raise HTTPException(422,'Choose characters from this scenario version')
        persona=player or {}
        if payload.persona_id:
            saved=await fetch_one('SELECT definition FROM player_personas WHERE id=%s AND user_id=%s',(payload.persona_id,user['id']))
            if not saved:
                raise HTTPException(404,'Persona not found')
            persona=saved['definition']
        Preferences.model_validate({**Preferences().model_dump(),**payload.preferences})
        initial=InitialState.model_validate(definition.get('initial_state',{})).model_dump()
        conv=await execute_returning('''INSERT INTO conversations(scenario_id,user_id,ai_character_id,user_character_id,current_place,"current_time",scenario_version_id,start_request_id,preferences,persona,title)
          VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s) RETURNING *''',(scene['id'],user['id'],ai['id'],payload.user_character_id,definition.get('place') or 'Unknown',definition.get('time') or 'Unknown',version['id'],payload.request_id,json.dumps(payload.preferences),json.dumps(persona,default=str),definition['title']))
        await execute('UPDATE conversations SET start_request_payload=%s::jsonb WHERE id=%s',(payload.model_dump_json(),conv['id']))
        await execute('INSERT INTO game_states(conversation_id,inventory,relationships,quest_flags) VALUES (%s,%s::jsonb,%s::jsonb,%s)',(conv['id'],json.dumps(initial['inventory']),json.dumps(initial['relationships']),initial['quest_flags']))
        from shared.utils.game_engine import GameEngine
        state=await GameEngine(None).get_state(conv['id'])
        await execute("INSERT INTO state_events(conversation_id,operation_id,state_version,snapshot,changes) VALUES (%s,%s,0,%s::jsonb,'[]')",(conv['id'],'initial-'+str(conv['id']),json.dumps(state)))
        if ai.get('greeting') or definition.get('greeting'):
            await execute("INSERT INTO messages(conversation_id,sender,content,metadata) VALUES (%s,'ai',%s,'{\"type\":\"greeting\"}')",(conv['id'],ai.get('greeting') or definition['greeting']))
        return conv

@router.post('/scenarios/{sid}/publish')
async def publish(sid:int,user:dict=Depends(get_current_user)):
    scene=await fetch_one('SELECT id FROM scenarios WHERE id=%s AND user_id=%s AND deleted_at IS NULL',(sid,user['id']))
    if not scene: raise HTTPException(404,'Scenario not found')
    version=await capture_version(sid,True)
    await execute('UPDATE scenarios SET is_public=true WHERE id=%s',(sid,))
    return version

@router.get('/catalog/scenarios')
async def catalog(limit:int=Query(30,ge=1,le=100),before:int|None=None,user:dict=Depends(get_current_user)):
    return await fetch_all('''SELECT s.id,v.definition->>'title' AS title,v.id AS version_id,v.definition FROM scenarios s
      JOIN LATERAL (SELECT id,definition FROM scenario_versions WHERE scenario_id=s.id AND published ORDER BY version DESC LIMIT 1) v ON true
      WHERE s.is_public AND s.deleted_at IS NULL AND (%s::int IS NULL OR s.id<%s) ORDER BY s.id DESC LIMIT %s''',(before,before,limit))

@router.get('/conversations')
async def library(limit:int=Query(30,ge=1,le=100),before:int|None=None,user:dict=Depends(get_current_user)):
    return await fetch_all('SELECT id,title,scenario_id,status,updated_at,parent_conversation_id FROM conversations WHERE user_id=%s AND (%s::int IS NULL OR id<%s) ORDER BY id DESC LIMIT %s',(user['id'],before,before,limit))

@router.get('/conversations/{cid}/resume')
async def resume(cid:int,user:dict=Depends(get_current_user)):
    async with transaction() as conn:
        await conn.execute('SELECT pg_advisory_xact_lock(%s)',(cid,))
        conv=await owned(cid,user['id'],True)
        from shared.utils.playthroughs import scene_for
        definition=await scene_for(cid)
        from shared.utils.game_engine import GameEngine
        messages=await fetch_all('SELECT * FROM (SELECT * FROM messages WHERE conversation_id=%s AND NOT superseded ORDER BY id DESC LIMIT 100) m ORDER BY id',(cid,))
        return {'conversation':conv,'state':await GameEngine(None).get_state(cid),'preferences':await effective_preferences(user['id'],conv['preferences'],definition.get('rules',{}).get('writing_defaults',{})),
                'messages':messages,'cursor':messages[-1]['id'] if messages else 0,
                'turn':await fetch_one('SELECT * FROM turns WHERE conversation_id=%s ORDER BY created_at DESC LIMIT 1',(cid,))}

class ConversationUpdate(BaseModel):
    title:str|None=Field(default=None,min_length=1,max_length=100)
    archived:bool|None=None
    preferences:dict|None=None

@router.patch('/conversations/{cid}')
async def update(cid:int,payload:ConversationUpdate,user:dict=Depends(get_current_user)):
    async with transaction():
        conv=await owned(cid,user['id'],True)
        if payload.preferences is not None: await effective_preferences(user['id'],payload.preferences)
        return await execute_returning('UPDATE conversations SET title=%s,status=%s,preferences=%s::jsonb WHERE id=%s RETURNING *',(payload.title or conv['title'],('archived' if payload.archived else 'active') if payload.archived is not None else conv['status'],json.dumps(payload.preferences if payload.preferences is not None else conv['preferences']),cid))

@router.get('/preferences')
async def preferences(user:dict=Depends(get_current_user)):
    return await effective_preferences(user['id'],{})

@router.put('/preferences')
async def set_preferences(payload:Preferences,user:dict=Depends(get_current_user)):
    await execute('INSERT INTO user_preferences(user_id,settings) VALUES (%s,%s::jsonb) ON CONFLICT(user_id) DO UPDATE SET settings=EXCLUDED.settings',(user['id'],payload.model_dump_json()))
    return payload

@router.post('/personas',status_code=201)
async def create_persona(payload:Persona,user:dict=Depends(get_current_user)):
    return await execute_returning('INSERT INTO player_personas(user_id,name,definition) VALUES (%s,%s,%s::jsonb) RETURNING *',(user['id'],payload.name,payload.model_dump_json()))

@router.get('/personas')
async def personas(user:dict=Depends(get_current_user)):
    return await fetch_all('SELECT * FROM player_personas WHERE user_id=%s ORDER BY id',(user['id'],))

@router.put('/personas/{persona_id}')
async def update_persona(persona_id:int,payload:Persona,user:dict=Depends(get_current_user)):
    row=await execute_returning('UPDATE player_personas SET name=%s,definition=%s::jsonb WHERE id=%s AND user_id=%s RETURNING *',(payload.name,payload.model_dump_json(),persona_id,user['id']))
    if not row: raise HTTPException(404,'Persona not found')
    return row

@router.delete('/personas/{persona_id}',status_code=204)
async def delete_persona(persona_id:int,user:dict=Depends(get_current_user)):
    if not await execute('DELETE FROM player_personas WHERE id=%s AND user_id=%s',(persona_id,user['id'])):
        raise HTTPException(404,'Persona not found')
