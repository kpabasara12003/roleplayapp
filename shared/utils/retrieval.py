"""Scoped dense + lexical retrieval with reciprocal-rank fusion."""
from shared.utils.observability import traced
from shared.db.postgres import fetch_all
from shared.db.qdrant import embed_texts,search_similar,rerank_documents
import asyncio

def fuse(groups,limit=12):
    results={}
    for group in groups:
        for rank,doc in enumerate(group,1):
            key=str(doc['id'])
            if key not in results:
                results[key]={**doc,'fusion_score':0.0}
            results[key]['fusion_score']+=1/(60+rank)
    return sorted(results.values(),key=lambda d:d['fusion_score'],reverse=True)[:limit]

@traced('retrieval.hybrid')
async def retrieve(query,conversation_id,scenario_id,user_id):
    vector=(await embed_texts([query]))[0]
    episodes,lore=await asyncio.gather(
        search_similar('conversations',vector,limit=8,filters={'conversation_id':conversation_id}),
        search_similar('lorebook',vector,limit=8,filters={'scenario_id':scenario_id,'user_id':user_id,'kind':'lore'}))
    for doc in lore:
        doc['id']='lore-'+str(doc['payload'].get('lore_id',doc['id']))
    lexical=await fetch_all("SELECT l.id,l.keyword,l.description FROM lorebook l JOIN scenarios s ON s.id=l.scenario_id WHERE l.scenario_id=%s AND s.user_id=%s AND to_tsvector('simple',l.keyword||' '||l.description) @@ plainto_tsquery('simple',%s) ORDER BY l.id LIMIT 8",(scenario_id,user_id,query))
    facts=await fetch_all("SELECT id,content,kind,source_message_id FROM memory_facts WHERE conversation_id=%s ORDER BY (to_tsvector('simple',content) @@ plainto_tsquery('simple',%s)) DESC,source_message_id DESC LIMIT 8",(conversation_id,query))
    lexical_docs=[{'id':'lore-'+str(r['id']),'payload':{'content':r['keyword']+': '+r['description'],'kind':'lore'}} for r in lexical]
    fact_docs=[{'id':'fact-'+str(r['id']),'payload':{**r,'content':r['content']+' [source message '+str(r['source_message_id'])+']'}} for r in facts]
    return await asyncio.to_thread(rerank_documents,query=query,documents=fuse([episodes,lore,lexical_docs,fact_docs]),top_n=5)
