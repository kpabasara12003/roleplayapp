ALTER TABLE scenarios ADD COLUMN discovery jsonb NOT NULL DEFAULT '{"genres":[],"tones":[],"life_stage":"any"}';
ALTER TABLE scenarios ADD CONSTRAINT scenario_discovery_object CHECK(jsonb_typeof(discovery)='object');
-- Index immutable publications, so unsaved/private draft edits cannot affect discovery.
ALTER TABLE scenario_versions ADD COLUMN search_document tsvector GENERATED ALWAYS AS (
  to_tsvector('simple'::regconfig,
    coalesce(definition->>'title','') || ' ' ||
    coalesce(definition->>'introduction','') || ' ' ||
    coalesce(definition->>'place','') || ' ' ||
    coalesce(jsonb_path_query_array(definition,'$.cast[*].name')::text,''))
) STORED;
CREATE INDEX scenario_version_search ON scenario_versions USING gin(search_document) WHERE published;
CREATE INDEX scenario_version_discovery ON scenario_versions USING gin((definition->'discovery')) WHERE published;
CREATE TABLE catalog_terms (
 kind text NOT NULL CHECK(kind IN ('genre','tone','life_stage','gender')),
 slug text NOT NULL CHECK(slug ~ '^[a-z][a-z0-9_]{0,49}$'),
 label text NOT NULL CHECK(length(label) BETWEEN 1 AND 80),
 description text NOT NULL DEFAULT '',
 aliases text[] NOT NULL DEFAULT '{}',
 position integer NOT NULL DEFAULT 0,
 active boolean NOT NULL DEFAULT true,
 requires_adult_cast boolean NOT NULL DEFAULT false,
 PRIMARY KEY(kind,slug)
);
INSERT INTO catalog_terms(kind,slug,label,position,requires_adult_cast) VALUES
 ('genre','romance','Romance',10,true),('genre','fantasy','Fantasy',20,false),
 ('genre','slice_of_life','Slice of life',30,false),('genre','mystery','Mystery',40,false),
 ('genre','adventure','Adventure',50,false),('genre','sci_fi','Science fiction',60,false),
 ('genre','drama','Drama',70,false),('genre','comedy','Comedy',80,false),('genre','historical','Historical',90,false),
 ('tone','cozy','Cozy',10,false),('tone','slow_burn','Slow burn',20,false),
 ('tone','lighthearted','Lighthearted',30,false),('tone','dramatic','Dramatic',40,false),('tone','suspenseful','Suspenseful',50,false),
 ('life_stage','any','Any life stage',0,false),
 ('life_stage','youthful','Youthful themes',10,false),
 ('life_stage','young_adult','Young adults (18+)',20,true),('life_stage','adult','Adult life',30,true);
INSERT INTO catalog_terms(kind,slug,label,aliases,position) VALUES
 ('gender','female','Female',ARRAY['female','woman','women'],10),
 ('gender','male','Male',ARRAY['male','man','men'],20),
 ('gender','nonbinary','Nonbinary',ARRAY['nonbinary','non-binary','non binary','enby'],30),
 ('gender','unspecified','Not specified',ARRAY[''],40);
UPDATE catalog_terms SET description='University life, first jobs and first love with adult characters.' WHERE kind='life_stage' AND slug='young_adult';
