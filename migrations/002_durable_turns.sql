ALTER TABLE conversations ADD COLUMN IF NOT EXISTS state_version BIGINT NOT NULL DEFAULT 0;
CREATE TABLE turns (
 id UUID PRIMARY KEY, conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
 request_id UUID NOT NULL, user_message_id INTEGER REFERENCES messages(id) ON DELETE SET NULL,
 content TEXT NOT NULL, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 status TEXT NOT NULL CHECK(status IN ('validating','generating','narrating','completed','blocked','failed')),
 state_version BIGINT NOT NULL, failure TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 UNIQUE(conversation_id,request_id)
);
CREATE UNIQUE INDEX one_active_turn ON turns(conversation_id) WHERE status IN ('validating','generating','narrating');
CREATE TABLE jobs (
 id UUID PRIMARY KEY, turn_id UUID NOT NULL REFERENCES turns(id) ON DELETE CASCADE,
 stage TEXT NOT NULL CHECK(stage IN ('validate','actor','director')),
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','running','completed','dead')),
 payload JSONB NOT NULL, owner UUID, fence BIGINT NOT NULL DEFAULT 0, attempts INTEGER NOT NULL DEFAULT 0,
 lease_until TIMESTAMPTZ, available_at TIMESTAMPTZ NOT NULL DEFAULT now(), last_notified_at TIMESTAMPTZ,
 last_error TEXT, result JSONB, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), completed_at TIMESTAMPTZ,
 UNIQUE(turn_id,stage)
);
CREATE INDEX jobs_recovery ON jobs(status,available_at,lease_until);
ALTER TABLE event_outbox ADD COLUMN IF NOT EXISTS event_key TEXT;
CREATE UNIQUE INDEX outbox_event_key ON event_outbox(event_key) WHERE event_key IS NOT NULL;
CREATE TABLE memory_facts (
 id BIGSERIAL PRIMARY KEY, conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
 fact_key TEXT NOT NULL, content TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('fact','promise','goal','relationship')),
 source_message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
 updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), UNIQUE(conversation_id,fact_key)
);
ALTER TABLE memory_checkpoints ADD COLUMN IF NOT EXISTS generation BIGINT NOT NULL DEFAULT 0;
ALTER TABLE scenarios ADD COLUMN IF NOT EXISTS rules JSONB NOT NULL DEFAULT '{"items":{},"flags":[],"locations":[],"times":[],"world_events":[]}'::jsonb;
