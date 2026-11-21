"""Dense BGE-M3 retrieval + SQL lexical retrieval, fused by reciprocal rank."""
import asyncio
import json
import uuid
from fastapi import HTTPException
from qdrant_client.models import Filter,FieldCondition,MatchValue,MatchAny
from fastapi_server.app.services.catalog import search_catalog,filter_options
from shared.db.postgres import fetch_one
from shared.db.qdrant import embed_texts,get_qdrant_client,_ensure_collection_exists
from shared.utils.catalog_index import COLLECTION
from shared.utils.providers import valkey
from redis.exceptions import RedisError

async def session_io(awaitable):
    try:
        async with asyncio.timeout(3):return await awaitable
    except (RedisError,TimeoutError,OSError):
        raise HTTPException(503,'Search session storage is unavailable. Please try again.')

def fuse(lexical,semantic):
    scores={}
    for ranking in (lexical,semantic):
        for rank,vid in enumerate(dict.fromkeys(ranking),1):scores[vid]=scores.get(vid,0)+1/(60+rank)
    return sorted(scores,key=lambda vid:(-scores[vid],-vid))

async def vector_candidates(q,filters):
    conditions=[]
    for param,key in [('genre','genres'),('tone','tones'),('life_stage','life_stage'),('mode','mode')]:
        value=filters.get(param)
        if value and not(param=='life_stage' and value=='any'):
            conditions.append(FieldCondition(key=key,match=MatchValue(value=value)))
    if filters.get('gender'):
        row=await fetch_one("SELECT aliases FROM catalog_terms WHERE kind='gender' AND slug=%s AND active",(filters['gender'],))
        if not row:raise HTTPException(422,'Unknown gender filter')
        conditions.append(FieldCondition(key='genders',match=MatchAny(any=row['aliases'])))
    vector=(await embed_texts([q]))[0]
    await _ensure_collection_exists(COLLECTION)
    result=await get_qdrant_client().query_points(collection_name=COLLECTION,query=vector,
        query_filter=Filter(must=conditions) if conditions else None,limit=200,with_payload=False)
    return [int(p.id) for p in result.points]

async def ranked_search(user_id,*,q='',search_type='hybrid',limit=24,cursor=None,**filters):
    cache=valkey()
    warning=None
    if cursor:
        try:
            token,offset=cursor.split(':');uuid.UUID(hex=token);offset=int(offset)
            if offset<0:raise ValueError()
        except (ValueError,AttributeError):raise HTTPException(422,'Invalid search cursor')
        raw=await session_io(cache.get(f'rp:catalog-search:{user_id}:{token}'))
        if not raw:raise HTTPException(410,'Search expired. Run the search again.')
        snapshot=json.loads(raw);filters=snapshot['filters'];ordered=snapshot['ids'];used=snapshot['used'];warning=snapshot['warning']
    else:
        if not q.strip():raise HTTPException(422,'Describe a scenario or enter a title or creator name.')
        # Always validate filters through SQL, including semantic-only requests.
        lexical=await search_catalog(q=q if search_type!='semantic' else '',limit=200,ranked=True,**filters)
        lexical_ids=[r['version_id'] for r in lexical] if search_type!='semantic' else []
        semantic=[];used=search_type
        if search_type!='keyword':
            try:
                async with asyncio.timeout(12):semantic=await vector_candidates(q,filters)
            except HTTPException:raise
            except Exception:
                if search_type=='semantic':raise HTTPException(503,'Semantic search is temporarily unavailable. Try Keyword search.')
                used='keyword';warning='Semantic search is unavailable; showing keyword matches.'
        ordered=(lexical_ids if search_type=='keyword' else semantic if search_type=='semantic' else fuse(lexical_ids,semantic))
        verified=await search_catalog(limit=400,version_ids=ordered,**filters)
        allowed={r['version_id'] for r in verified}
        ordered=[vid for vid in ordered if vid in allowed][:200]
        token=uuid.uuid4().hex;offset=0
        await session_io(cache.set(f'rp:catalog-search:{user_id}:{token}',json.dumps({'ids':ordered,'filters':filters,'used':used,'warning':warning}),ex=300))
    # Recheck every page against SQL: visibility/publication can change after ranking.
    verified=await search_catalog(limit=200,version_ids=ordered[offset:],**filters)
    by_id={r['version_id']:r for r in verified}
    items=[];position=offset
    while position<len(ordered) and len(items)<limit:
        row=by_id.get(ordered[position]);position+=1
        if row:items.append(row)
    return {'items':items,'next_cursor':f'{token}:{position}' if position<len(ordered) else None,
            'search_mode_used':used,'warning':warning}
