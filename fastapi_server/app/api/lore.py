from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,Field,ConfigDict,StringConstraints
from typing import Annotated
from shared.db.postgres import fetch_one,fetch_all,execute_returning,execute,transaction
from fastapi_server.app.api.users import get_current_user

router=APIRouter(prefix='/scenarios',tags=['Lore'])
class LoreEntry(BaseModel):
    model_config=ConfigDict(extra='forbid')
    keyword: Annotated[str,StringConstraints(strip_whitespace=True,min_length=1,max_length=50)]
    description: Annotated[str,StringConstraints(strip_whitespace=True,min_length=1,max_length=12000)]
    category: str|None=Field(default=None,max_length=50)

async def owned(sid,user):
    if not await fetch_one('SELECT id FROM scenarios WHERE id=%s AND user_id=%s AND deleted_at IS NULL',(sid,user['id'])):
        raise HTTPException(status_code=404,detail='Scenario not found')

@router.get('/{scenario_id}/lore')
async def list_lore(scenario_id:int,user:dict=Depends(get_current_user)):
    await owned(scenario_id,user)
    return await fetch_all('SELECT * FROM lorebook WHERE scenario_id=%s ORDER BY id',(scenario_id,))

@router.post('/{scenario_id}/lore',status_code=201)
async def create_lore(scenario_id:int,payload:LoreEntry,user:dict=Depends(get_current_user)):
    await owned(scenario_id,user)
    return await execute_returning('INSERT INTO lorebook(scenario_id,keyword,description,category) VALUES (%s,%s,%s,%s) RETURNING *',(scenario_id,payload.keyword,payload.description,payload.category))

@router.put('/{scenario_id}/lore/{lore_id}')
async def update_lore(scenario_id:int,lore_id:int,payload:LoreEntry,user:dict=Depends(get_current_user)):
    await owned(scenario_id,user)
    row=await execute_returning('UPDATE lorebook SET keyword=%s,description=%s,category=%s WHERE id=%s AND scenario_id=%s RETURNING *',(payload.keyword,payload.description,payload.category,lore_id,scenario_id))
    if not row:
        raise HTTPException(status_code=404,detail='Lore not found')
    return row

@router.delete('/{scenario_id}/lore/{lore_id}',status_code=204)
async def delete_lore(scenario_id:int,lore_id:int,user:dict=Depends(get_current_user)):
    await owned(scenario_id,user)
    import json
    from fastapi_server.app.api.chat import nats_publisher
    async with transaction() as conn:
        await conn.execute('SELECT pg_advisory_xact_lock(%s)',(2000000000+scenario_id,))
        if not await execute('DELETE FROM lorebook WHERE id=%s AND scenario_id=%s',(lore_id,scenario_id)):
            raise HTTPException(status_code=404,detail='Lore not found')
        await nats_publisher.publish('roleplay.events.scenario_deleted',json.dumps({'scenario_id':scenario_id,'lore_ids':[lore_id],'conversation_ids':[]}).encode())
