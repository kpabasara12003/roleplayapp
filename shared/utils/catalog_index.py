"""Retryable public-publication index, isolated from private chat memory."""
import asyncio
from qdrant_client.models import PointStruct
from shared.db.postgres import fetch_all,execute
from shared.db.qdrant import embed_texts,upsert_points,get_qdrant_client
from shared.utils.logger import get_logger

COLLECTION='catalog_bge_m3_v1'
logger=get_logger(__name__)

def document(definition,author):
    cast=definition.get('cast',[])
    parts=[definition.get('title',''), 'Creator: '+author,definition.get('introduction') or '',
           definition.get('place') or '',definition.get('time') or '']
    meta=definition.get('discovery',{})
    parts+=['Genres: '+', '.join(meta.get('genres',[])), 'Tone: '+', '.join(meta.get('tones',[]))]
    # Public premise and cast traits only; no player memories, private notes or full lore.
    parts += [f"{c.get('name','')}: {(c.get('personality') or '')[:600]} {(c.get('role_description') or '')[:400]}" for c in cast[:12]]
    return '\n'.join(parts)[:6000]

async def index_catalog_batch():
    rows=await fetch_all('''SELECT v.id,v.scenario_id,v.definition,u.username FROM scenario_versions v
      JOIN scenarios s ON s.id=v.scenario_id JOIN users u ON u.id=s.user_id
      LEFT JOIN catalog_vector_checkpoints c ON c.version_id=v.id
      WHERE s.is_public AND s.deleted_at IS NULL AND v.published
      AND NOT EXISTS(SELECT 1 FROM scenario_versions n WHERE n.scenario_id=v.scenario_id AND n.published AND n.version>v.version)
      AND c.indexed_at IS NULL AND (c.retry_at IS NULL OR c.retry_at<=now()) ORDER BY v.id LIMIT 4''')
    for row in rows:
        try:
            definition=row['definition'];meta=definition.get('discovery',{})
            vector=(await embed_texts([document(definition,row['username'])]))[0]
            await upsert_points(COLLECTION,[PointStruct(id=row['id'],vector=vector,payload={
                'scenario_version_id':row['id'],'scenario_id':row['scenario_id'],
                'genres':meta.get('genres',[]),'tones':meta.get('tones',[]),'life_stage':meta.get('life_stage','any'),
                'mode':definition.get('rules',{}).get('mode','freeform'),
                'genders':list({(c.get('gender') or '').strip().lower() for c in definition.get('cast',[]) if c.get('is_ai')})})])
            await execute('''INSERT INTO catalog_vector_checkpoints(version_id,indexed_at) VALUES (%s,now())
              ON CONFLICT(version_id) DO UPDATE SET indexed_at=now(),attempts=0''',(row['id'],))
        except Exception as error:
            # Store no provider bodies/credentials; failed items do not block the queue.
            logger.warning('Catalog indexing version %s failed (%s)',row['id'],type(error).__name__)
            await execute('''INSERT INTO catalog_vector_checkpoints(version_id,retry_at,attempts) VALUES (%s,now()+interval '2 minutes',1)
              ON CONFLICT(version_id) DO UPDATE SET retry_at=now()+interval '2 minutes',attempts=catalog_vector_checkpoints.attempts+1''',(row['id'],))

_cleanup_cursor=None
async def cleanup_catalog():
    global _cleanup_cursor
    client=get_qdrant_client()
    if not await client.collection_exists(COLLECTION):return
    points,next_offset=await client.scroll(COLLECTION,limit=100,offset=_cleanup_cursor,with_payload=False,with_vectors=False)
    ids=[int(p.id) for p in points]
    if ids:
        current=await fetch_all('''SELECT v.id FROM scenario_versions v JOIN scenarios s ON s.id=v.scenario_id
          WHERE v.id=ANY(%s) AND v.published AND s.is_public AND s.deleted_at IS NULL
          AND NOT EXISTS(SELECT 1 FROM scenario_versions n WHERE n.scenario_id=v.scenario_id AND n.published AND n.version>v.version)''',(ids,))
        keep={r['id'] for r in current};remove=[vid for vid in ids if vid not in keep]
        if remove:
            await client.delete(COLLECTION,points_selector=remove,wait=True)
            await execute('DELETE FROM catalog_vector_checkpoints WHERE version_id=ANY(%s)',(remove,))
    _cleanup_cursor=next_offset

async def catalog_index_loop():
    while True:
        try:
            await index_catalog_batch()
            await cleanup_catalog()
        except Exception as error:logger.warning('Catalog index loop failed (%s)',type(error).__name__)
        await asyncio.sleep(10)
