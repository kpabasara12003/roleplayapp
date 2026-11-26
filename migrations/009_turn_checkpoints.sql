CREATE TABLE turn_checkpoints (
 turn_id uuid NOT NULL REFERENCES turns(id) ON DELETE CASCADE,
 phase text NOT NULL CHECK(phase IN ('before_reply','after_turn')),
 snapshot jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(turn_id,phase)
);
-- Only reconstruct pre-reply state when a validation-stage event proves it.
INSERT INTO turn_checkpoints(turn_id,phase,snapshot)
 SELECT DISTINCT ON(t.id) t.id,'before_reply',e.snapshot FROM turns t
 JOIN jobs j ON j.turn_id=t.id AND j.stage='validate' AND j.status='completed'
 JOIN state_events e ON e.turn_id=t.id AND e.operation_id LIKE j.id::text||':%'
 ORDER BY t.id,e.state_version;
INSERT INTO turn_checkpoints(turn_id,phase,snapshot)
 SELECT t.id,'after_turn',e.snapshot FROM turns t
 JOIN LATERAL (SELECT snapshot FROM state_events WHERE conversation_id=t.conversation_id AND state_version<=t.state_version ORDER BY state_version DESC LIMIT 1) e ON true
 WHERE t.status='completed';
