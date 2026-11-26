ALTER TABLE messages ADD COLUMN IF NOT EXISTS event_id TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS api_key_hashed BOOLEAN NOT NULL DEFAULT FALSE;
CREATE TABLE IF NOT EXISTS websocket_tickets (
    digest TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS request_limits (
    key TEXT NOT NULL,
    bucket BIGINT NOT NULL,
    count INTEGER NOT NULL,
    PRIMARY KEY(key,bucket)
);
DELETE FROM request_limits WHERE bucket < floor(extract(epoch from now())/60)-60;
CREATE UNIQUE INDEX IF NOT EXISTS messages_event_id_unique ON messages(event_id);
CREATE INDEX IF NOT EXISTS messages_conversation_order ON messages(conversation_id,id);
CREATE TABLE IF NOT EXISTS event_outbox (
    id BIGSERIAL PRIMARY KEY,
    subject TEXT NOT NULL,
    payload BYTEA NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS conversation_turns (
    conversation_id INTEGER PRIMARY KEY REFERENCES conversations(id) ON DELETE CASCADE,
    turn_id TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS memory_checkpoints (
    conversation_id INTEGER PRIMARY KEY REFERENCES conversations(id) ON DELETE CASCADE,
    last_message_id INTEGER NOT NULL DEFAULT 0
);
