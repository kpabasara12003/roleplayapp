CREATE TABLE memory_blocks (
 conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
 start_id INTEGER NOT NULL, end_id INTEGER NOT NULL, summary TEXT NOT NULL,
 model_version TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(conversation_id,start_id,end_id)
);
CREATE TABLE memory_fact_revisions (
 id BIGSERIAL PRIMARY KEY, conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
 fact_key TEXT NOT NULL, content TEXT NOT NULL, kind TEXT NOT NULL,
 source_message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
 UNIQUE(conversation_id,fact_key,source_message_id)
);
CREATE TABLE lore_checkpoints (
 lore_id INTEGER PRIMARY KEY REFERENCES lorebook(id) ON DELETE CASCADE,
 updated_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE memory_reconciliation (
 collection TEXT PRIMARY KEY, cursor TEXT, updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
