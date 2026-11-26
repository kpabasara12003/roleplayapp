ALTER TABLE scenario_versions DROP CONSTRAINT scenario_versions_scenario_id_fkey;
ALTER TABLE scenario_versions ADD CONSTRAINT scenario_versions_scenario_id_fkey FOREIGN KEY(scenario_id) REFERENCES scenarios(id) ON DELETE CASCADE;
-- Character identities belong to the pinned cast; deleting a draft character cannot delete a saved persona.
ALTER TABLE conversations DROP CONSTRAINT conversations_ai_character_id_fkey;
ALTER TABLE conversations DROP CONSTRAINT conversations_user_character_id_fkey;
INSERT INTO state_events(conversation_id,operation_id,state_version,snapshot,changes)
 SELECT c.id,'upgrade-baseline-'||c.id,c.state_version,jsonb_build_object(
 'state_version',c.state_version,'inventory',COALESCE(g.inventory,'[]'::jsonb),
 'relationships',COALESCE(g.relationships,'{}'::jsonb),'quest_flags',COALESCE(to_jsonb(g.quest_flags),'[]'::jsonb),
 'runtime',COALESCE(g.runtime,'{}'::jsonb),'place',c.current_place,'time',c."current_time"),'[]'::jsonb
 FROM conversations c LEFT JOIN game_states g ON g.conversation_id=c.id
 ON CONFLICT(conversation_id,state_version) DO NOTHING;
