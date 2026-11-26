ALTER TABLE conversations ADD COLUMN start_request_payload jsonb NOT NULL DEFAULT '{}';
