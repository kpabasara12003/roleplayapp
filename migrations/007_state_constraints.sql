ALTER TABLE game_states ADD CONSTRAINT inventory_array CHECK(jsonb_typeof(inventory)='array');
ALTER TABLE game_states ADD CONSTRAINT relationships_object CHECK(jsonb_typeof(relationships)='object');
ALTER TABLE game_states ADD CONSTRAINT runtime_object CHECK(jsonb_typeof(runtime)='object');
ALTER TABLE game_states ADD CONSTRAINT supported_state_schema CHECK(schema_version=1);
