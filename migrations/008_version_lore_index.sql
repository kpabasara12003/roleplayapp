CREATE TABLE version_lore_checkpoints (
 version_id bigint PRIMARY KEY REFERENCES scenario_versions(id) ON DELETE CASCADE,
 next_offset integer NOT NULL DEFAULT 0 CHECK(next_offset>=0)
);
