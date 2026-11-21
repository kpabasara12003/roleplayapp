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
async def retrieve(query,conversation_id,scenario_id,user_id,character_name=None):
    vector=(await embed_texts([query]))[0]
    suppressed=await fetch_all('SELECT id FROM memory_facts WHERE conversation_id=%s AND (suppressed OR manual OR known_by IS NOT NULL) LIMIT 1',(conversation_id,))
    episodes=[] if suppressed else await search_similar('conversations',vector,limit=8,filters={'conversation_id':conversation_id})
    # Lore comes from the pinned version, not the creator's currently editable index.
    from shared.utils.playthroughs import scene_for
    scene=await scene_for(conversation_id)
    lore=await search_similar('lorebook',vector,limit=8,filters={'scenario_version_id':scene['_version_id'],'kind':'version_lore'}) if scene.get('lore') and scene.get('_version_id') else []
    for doc in lore:
        doc['id']='lore-'+str(doc['payload']['version_lore_id'])
    words=set(query.casefold().split())
    lexical=sorted(scene.get('lore',[]),key=lambda r:len(words & set((r['keyword']+' '+r['description']).casefold().split())),reverse=True)[:8]
    facts=await fetch_all("SELECT id,content,kind,source_message_id,pinned FROM memory_facts WHERE conversation_id=%s AND NOT suppressed AND (known_by IS NULL OR %s=ANY(known_by)) ORDER BY pinned DESC,source_message_id DESC LIMIT 20",(conversation_id,character_name))
    notes=await fetch_all('SELECT id,content FROM memory_notes WHERE conversation_id=%s AND pinned ORDER BY id DESC LIMIT 10',(conversation_id,))
    lexical_docs=[{'id':'lore-'+str(r['id']),'payload':{'content':r['keyword']+': '+r['description'],'kind':'lore'}} for r in lexical]
    fact_docs=[{'id':'fact-'+str(r['id']),'payload':{**r,'content':r['content']+' [source message '+str(r['source_message_id'])+']'}} for r in facts]
    ranked=await asyncio.to_thread(rerank_documents,query=query,documents=fuse([episodes,lore,lexical_docs,fact_docs]),top_n=5)
    pinned=[{'id':'pin-'+str(r['id']),'payload':{'content':r['content'],'kind':'pinned'}} for r in facts if r['pinned']]
    return pinned+[{'id':'note-'+str(r['id']),'payload':{'content':r['content'],'kind':'note'}} for r in notes]+ranked
