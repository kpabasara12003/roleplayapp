"""Database-side search over the latest published version, never the draft."""
import json
from fastapi import HTTPException
from shared.db.postgres import fetch_all

async def filter_options():
    return await fetch_all('SELECT kind,slug,label,description,requires_adult_cast FROM catalog_terms WHERE active ORDER BY kind,position,label,slug')

async def search_catalog(*,limit=30,before=None,q='',genre=None,tone=None,life_stage=None,gender=None,mode=None,version_ids=None,ranked=False):
    if version_ids is not None and not version_ids:return []
    terms=await filter_options()
    for kind,value in [('genre',genre),('tone',tone),('life_stage',life_stage),('gender',gender)]:
        if value and not any(t['kind']==kind and t['slug']==value for t in terms):
            raise HTTPException(422,f'Unknown {kind} filter. Refresh available filters.')
    clauses=['s.is_public','s.deleted_at IS NULL', '''NOT EXISTS (
      SELECT 1 FROM scenario_versions newer
      WHERE newer.scenario_id=v.scenario_id AND newer.published AND newer.version>v.version
    )''']
    params=[]
    if before is not None:
        clauses.append('s.id<%s');params.append(before)
    if version_ids is not None:
        clauses.append('v.id=ANY(%s)');params.append(version_ids)
    q=q.strip()
    if q:
        literal=q.replace('\\','\\\\').replace('%',r'\%').replace('_',r'\_')
        clauses.append("(v.search_document @@ websearch_to_tsquery('simple',%s) OR v.definition->>'title' ILIKE %s OR u.username ILIKE %s)")
        params.extend([q,'%'+literal+'%','%'+literal+'%'])
    metadata={}
    if genre:metadata['genres']=[genre]
    if tone:metadata['tones']=[tone]
    if life_stage and life_stage!='any':metadata['life_stage']=life_stage
    if metadata:
        clauses.append("v.definition->'discovery' @> %s::jsonb");params.append(json.dumps(metadata))
    if mode:
        clauses.append("COALESCE(v.definition->'rules'->>'mode','freeform')=%s");params.append(mode)
    if gender:
        clauses.append('''EXISTS (
          SELECT 1 FROM jsonb_array_elements(v.definition->'cast') c
          JOIN catalog_terms t ON t.kind='gender' AND t.slug=%s AND t.active
          WHERE c->>'is_ai'='true' AND lower(btrim(coalesce(c->>'gender','')))=ANY(t.aliases)
        )''');params.append(gender)
    ordering='s.id DESC'
    if q and ranked:
        ordering="CASE WHEN lower(v.definition->>'title')=lower(%s) THEN 0 ELSE 1 END,ts_rank_cd(v.search_document,websearch_to_tsquery('simple',%s)) DESC,s.id DESC"
        params.extend([q,q])
    params.append(limit)
    return await fetch_all('''SELECT s.id,u.username AS creator,v.definition->>'title' AS title,v.id AS version_id,v.definition
      FROM scenarios s JOIN users u ON u.id=s.user_id JOIN scenario_versions v ON v.scenario_id=s.id AND v.published
      WHERE '''+' AND '.join(clauses)+' ORDER BY '+ordering+' LIMIT %s',tuple(params))
