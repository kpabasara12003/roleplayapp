"""Version-pinned authored content and consistent playthrough snapshots."""
import json
from fastapi import HTTPException
from shared.db.postgres import fetch_one,fetch_all,execute,execute_returning,transaction
from shared.schemas.playthrough import Preferences,InitialState

async def capture_version(sid, publish=False):
    async with transaction():
        scene=await fetch_one('SELECT * FROM scenarios WHERE id=%s AND deleted_at IS NULL FOR UPDATE',(sid,))
        if not scene:
            raise HTTPException(404,'Scenario not found')
        cast=await fetch_all('SELECT * FROM characters WHERE scenario_id=%s ORDER BY id',(sid,))
        if len({c['name'].casefold() for c in cast}) != len(cast):
            raise HTTPException(422,'Character names must be unique within a scenario version')
        initial=InitialState.model_validate(scene['initial_state']).model_dump()
        if not set(initial['relationships']).issubset({c['name'] for c in cast}):
            raise HTTPException(422,'Initial relationships must reference the cast')
        lore=await fetch_all('SELECT * FROM lorebook WHERE scenario_id=%s ORDER BY id',(sid,))
        definition={**scene,'cast':cast,'lore':lore,'initial_state':initial}
        return await execute_returning('INSERT INTO scenario_versions(scenario_id,version,definition,published) SELECT %s,COALESCE(max(version),0)+1,%s::jsonb,%s FROM scenario_versions WHERE scenario_id=%s RETURNING *',(sid,json.dumps(definition,default=str),publish,sid))

async def scene_for(cid):
    row=await fetch_one('SELECT v.id AS version_id,v.definition,c.scenario_id FROM conversations c LEFT JOIN scenario_versions v ON v.id=c.scenario_version_id WHERE c.id=%s',(cid,))
    if not row:
        raise HTTPException(404,'Conversation not found')
    if row['definition']:
        return {**row['definition'],'_version_id':row['version_id']}
    # Backfill existing conversations once, before they are next played.
    version=await capture_version(row['scenario_id'])
    await execute('UPDATE conversations SET scenario_version_id=%s WHERE id=%s AND scenario_version_id IS NULL',(version['id'],cid))
    return {**version['definition'],'_version_id':version['id']}

async def effective_preferences(user_id, overrides, defaults=None):
    row=await fetch_one('SELECT settings FROM user_preferences WHERE user_id=%s',(user_id,))
    return Preferences.model_validate({**(defaults or {}),**(row['settings'] if row else {}),**overrides}).model_dump()

async def owned(cid,uid,lock=False):
    row=await fetch_one('SELECT * FROM conversations WHERE id=%s AND user_id=%s'+(' FOR UPDATE' if lock else ''),(cid,uid))
    if not row:
        raise HTTPException(404,'Conversation not found')
    return row
