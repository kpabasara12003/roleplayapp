ALTER TABLE scenarios ADD COLUMN deleted_at timestamptz;
ALTER TABLE scenarios ADD COLUMN initial_state jsonb NOT NULL DEFAULT '{}';
CREATE TABLE scenario_versions (
 id bigserial PRIMARY KEY, scenario_id integer NOT NULL REFERENCES scenarios(id),
 version integer NOT NULL, definition jsonb NOT NULL, published boolean NOT NULL DEFAULT false,
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(scenario_id,version)
);
ALTER TABLE conversations ADD COLUMN scenario_version_id bigint REFERENCES scenario_versions(id);
ALTER TABLE conversations ADD COLUMN title text;
ALTER TABLE conversations ADD COLUMN start_request_id uuid;
ALTER TABLE conversations ADD COLUMN preferences jsonb NOT NULL DEFAULT '{}';
ALTER TABLE conversations ADD COLUMN persona jsonb NOT NULL DEFAULT '{}';
ALTER TABLE conversations ADD COLUMN parent_conversation_id integer REFERENCES conversations(id) ON DELETE SET NULL;
ALTER TABLE conversations ADD COLUMN fork_message_id integer;
CREATE UNIQUE INDEX conversation_start_request ON conversations(user_id,start_request_id);
CREATE INDEX conversation_library ON conversations(user_id,updated_at DESC,id DESC);
CREATE TABLE user_preferences (user_id integer PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE, settings jsonb NOT NULL DEFAULT '{}');
CREATE TABLE player_personas (id bigserial PRIMARY KEY,user_id integer NOT NULL REFERENCES users(id) ON DELETE CASCADE,name text NOT NULL,definition jsonb NOT NULL);
ALTER TABLE game_states ADD COLUMN schema_version integer NOT NULL DEFAULT 1;
ALTER TABLE game_states ADD COLUMN runtime jsonb NOT NULL DEFAULT '{"executed_rules":[],"quest_progress":{},"characters":{},"clock_minutes":0}';
CREATE TRIGGER update_game_states_updated_at BEFORE UPDATE ON game_states FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TABLE state_events (
 id bigserial PRIMARY KEY, conversation_id integer NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
 turn_id uuid REFERENCES turns(id) ON DELETE SET NULL, operation_id text NOT NULL UNIQUE,
 state_version bigint NOT NULL, snapshot jsonb NOT NULL, changes jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(conversation_id,state_version)
);
ALTER TABLE memory_facts ADD COLUMN pinned boolean NOT NULL DEFAULT false;
ALTER TABLE memory_facts ADD COLUMN suppressed boolean NOT NULL DEFAULT false;
ALTER TABLE memory_facts ADD COLUMN manual boolean NOT NULL DEFAULT false;
ALTER TABLE memory_facts ADD COLUMN known_by text[];
CREATE TABLE memory_notes (id bigserial PRIMARY KEY,conversation_id integer NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,content text NOT NULL,pinned boolean NOT NULL DEFAULT true);
ALTER TABLE messages ADD COLUMN revision_of integer REFERENCES messages(id) ON DELETE SET NULL;
ALTER TABLE messages ADD COLUMN superseded boolean NOT NULL DEFAULT false;
DROP TABLE conversation_turns;
-- Pin all pre-upgrade playthroughs before any creator can edit a draft.
INSERT INTO scenario_versions(scenario_id,version,definition,published)
 SELECT s.id,1,to_jsonb(s)||jsonb_build_object(
 'cast',COALESCE((SELECT jsonb_agg(to_jsonb(c) ORDER BY c.id) FROM characters c WHERE c.scenario_id=s.id),'[]'::jsonb),
 'lore',COALESCE((SELECT jsonb_agg(to_jsonb(l) ORDER BY l.id) FROM lorebook l WHERE l.scenario_id=s.id),'[]'::jsonb)),COALESCE(s.is_public,false) FROM scenarios s;
UPDATE conversations c SET scenario_version_id=v.id,title=v.definition->>'title' FROM scenario_versions v WHERE v.scenario_id=c.scenario_id;
