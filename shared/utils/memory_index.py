"""Recoverable semantic memory and vector reconciliation, scoped to owners."""
import asyncio
import json
import uuid
from qdrant_client.models import PointStruct,Filter,FieldCondition,MatchValue,FilterSelector
from shared.db.postgres import fetch_one,fetch_all,execute,transaction
from shared.db.qdrant import embed_texts,upsert_points,get_qdrant_client
from shared.utils.memory import extract_memory

def point_id(*parts):
    return str(uuid.uuid5(uuid.NAMESPACE_URL,'roleplay:'+':'.join(map(str,parts))))

async def index_conversation(cid, block_size=10):
    checkpoint=await fetch_one('SELECT last_message_id FROM memory_checkpoints WHERE conversation_id=%s',(cid,))
    after=checkpoint['last_message_id'] if checkpoint else 0
    rows=await fetch_all("""SELECT m.id,m.sender,m.content FROM messages m WHERE m.conversation_id=%s AND m.id>%s AND NOT m.superseded
      AND COALESCE(m.metadata->>'action_status','accepted') NOT IN ('pending','blocked')
      AND NOT EXISTS(SELECT 1 FROM turns t WHERE t.conversation_id=m.conversation_id AND t.status IN ('validating','generating','narrating'))
      AND NOT EXISTS(SELECT 1 FROM memory_facts f WHERE f.conversation_id=m.conversation_id AND f.suppressed AND f.source_message_id=m.id)
      ORDER BY m.id LIMIT %s""",(cid,after,block_size))
    if len(rows)<block_size:
        return
    scene=await fetch_one('SELECT scenario_id,user_id FROM conversations WHERE id=%s',(cid,))
    if not scene:
        return
    start,end=rows[0]['id'],rows[-1]['id']
    stored=await fetch_one('SELECT summary FROM memory_blocks WHERE conversation_id=%s AND start_id=%s AND end_id=%s',(cid,start,end))
    block,model=(None,None)
    if not stored:
        block,model=await extract_memory(rows)
    summary=stored['summary'] if stored else block.summary
    raw='\n'.join(f"[{r['id']}] {r['sender']}: {r['content']}" for r in rows)
    chunks=[raw[i:i+2500] for i in range(0,len(raw),2500)]
    texts=[summary]+chunks
    vectors=await embed_texts(texts)
    from shared.utils.index_lock import index_lock
    async with index_lock(scene['scenario_id']):
        # Locks align deletion and checkpoint advancement, including across replicas.
        if not await fetch_one('SELECT id FROM conversations WHERE id=%s FOR KEY SHARE',(cid,)):
            return
        current=await fetch_one('SELECT last_message_id FROM memory_checkpoints WHERE conversation_id=%s FOR UPDATE',(cid,))
        if current and current['last_message_id']>=end:
            return
        async with transaction():
            await execute('INSERT INTO memory_blocks(conversation_id,start_id,end_id,summary,model_version) VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',(cid,start,end,summary,model or 'previous'))
            if block:
                for fact in block.facts:
                    key='_'.join(fact.key.casefold().split())
                    args=(cid,key,fact.content,fact.kind,fact.source_message_id)
                    await execute('INSERT INTO memory_fact_revisions(conversation_id,fact_key,content,kind,source_message_id) VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',args)
                    await execute('INSERT INTO memory_facts(conversation_id,fact_key,content,kind,source_message_id) VALUES (%s,%s,%s,%s,%s) ON CONFLICT(conversation_id,fact_key) DO UPDATE SET content=EXCLUDED.content,kind=EXCLUDED.kind,source_message_id=EXCLUDED.source_message_id,updated_at=now() WHERE NOT memory_facts.manual AND NOT memory_facts.suppressed AND memory_facts.source_message_id<EXCLUDED.source_message_id',args)
        points=[PointStruct(id=point_id(cid,start,end,i),vector=vector,payload={'conversation_id':cid,'scenario_id':scene['scenario_id'],'user_id':scene['user_id'],'content':text,'kind':'summary' if i==0 else 'episode','start_id':start,'end_id':end,'embedding_version':'bge-m3:1024:v1'}) for i,(text,vector) in enumerate(zip(texts,vectors))]
        await upsert_points('conversations',points)
        await execute('INSERT INTO memory_checkpoints(conversation_id,last_message_id) VALUES (%s,%s) ON CONFLICT(conversation_id) DO UPDATE SET last_message_id=GREATEST(memory_checkpoints.last_message_id,EXCLUDED.last_message_id)',(cid,end))

async def index_lore():
    rows=await fetch_all('SELECT l.*,s.user_id FROM lorebook l JOIN scenarios s ON s.id=l.scenario_id LEFT JOIN lore_checkpoints c ON c.lore_id=l.id WHERE c.lore_id IS NULL OR c.updated_at<l.updated_at ORDER BY l.id LIMIT 10')
    for row in rows:
        text=row['keyword']+': '+row['description']
        vector=(await embed_texts([text]))[0]
        from shared.utils.index_lock import index_lock
        async with index_lock(row['scenario_id']):
            current=await fetch_one('SELECT updated_at FROM lorebook WHERE id=%s',(row['id'],))
            if not current or current['updated_at']!=row['updated_at']:
                continue
            await upsert_points('lorebook',[PointStruct(id=point_id('lore',row['id']),vector=vector,payload={'lore_id':row['id'],'scenario_id':row['scenario_id'],'user_id':row['user_id'],'content':text,'kind':'lore'})])
            await execute('INSERT INTO lore_checkpoints(lore_id,updated_at) VALUES (%s,%s) ON CONFLICT(lore_id) DO UPDATE SET updated_at=EXCLUDED.updated_at',(row['id'],row['updated_at']))

async def reconcile_vectors(limit=100):
    client=get_qdrant_client()
    for collection,key,table in [('conversations','conversation_id','conversations'),('lorebook','lore_id','lorebook')]:
        if not await client.collection_exists(collection):
            continue
        progress=await fetch_one('SELECT cursor FROM memory_reconciliation WHERE collection=%s',(collection,))
        offset=progress['cursor'] if progress else None
        points,next_offset=await client.scroll(collection,limit=limit,offset=offset,with_payload=True,with_vectors=False)
        for point in points:
            if (point.payload or {}).get('kind')=='version_lore':
                if not await fetch_one('SELECT id FROM scenario_versions WHERE id=%s',((point.payload or {})['scenario_version_id'],)):
                    await client.delete(collection,points_selector=[point.id],wait=True)
                continue
            entity=(point.payload or {}).get(key)
            if entity is not None and not await fetch_one(f'SELECT id FROM {table} WHERE id=%s',(entity,)):
                await client.delete(collection,points_selector=[point.id],wait=True)
        await execute('INSERT INTO memory_reconciliation(collection,cursor) VALUES (%s,%s) ON CONFLICT(collection) DO UPDATE SET cursor=EXCLUDED.cursor,updated_at=now()',(collection,str(next_offset) if next_offset is not None else None))

async def index_versions(version_id=None):
    """Immutable version lore, independently retryable in bounded batches."""
    row=await fetch_one('''SELECT v.id,v.scenario_id,v.definition,COALESCE(c.next_offset,0) AS offset FROM scenario_versions v
      LEFT JOIN version_lore_checkpoints c ON c.version_id=v.id
      WHERE COALESCE(c.next_offset,0)<jsonb_array_length(v.definition->'lore') AND (%s::bigint IS NULL OR v.id=%s) ORDER BY v.id LIMIT 1''',(version_id,version_id))
    if not row:return
    entries=row['definition']['lore'][row['offset']:row['offset']+10]
    vectors=await embed_texts([entry['keyword']+': '+entry['description'] for entry in entries])
    from shared.utils.index_lock import index_lock
    async with index_lock(row['scenario_id']):
        if not await fetch_one('SELECT id FROM scenario_versions WHERE id=%s',(row['id'],)):return
        points=[PointStruct(id=point_id('version',row['id'],entry['id']),vector=vector,payload={'scenario_version_id':row['id'],'scenario_id':row['scenario_id'],'version_lore_id':entry['id'],'content':entry['keyword']+': '+entry['description'],'kind':'version_lore'}) for entry,vector in zip(entries,vectors)]
        await upsert_points('lorebook',points)
        await execute('INSERT INTO version_lore_checkpoints(version_id,next_offset) VALUES (%s,%s) ON CONFLICT(version_id) DO UPDATE SET next_offset=GREATEST(version_lore_checkpoints.next_offset,EXCLUDED.next_offset)',(row['id'],row['offset']+len(entries)))
