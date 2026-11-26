CREATE TABLE catalog_vector_checkpoints (
 version_id bigint PRIMARY KEY REFERENCES scenario_versions(id) ON DELETE CASCADE,
 indexed_at timestamptz,
 retry_at timestamptz NOT NULL DEFAULT now(),
 attempts integer NOT NULL DEFAULT 0
);
