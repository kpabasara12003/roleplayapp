# Persistent roleplay API

All endpoints use the existing `X-API-Key` authentication. Scenario editing remains creator-only. Conversations and personal memories remain player-only. Images and object storage are excluded.

## Author and publish

Create a scenario and its cast using the existing endpoints. `initial_state` accepts the exact inventory, relationship and quest-flag structures from the product specification. Character names must be unique within a version; item IDs are permanent identities and display names may change. `rules.items` maps stable IDs to item definitions.

`POST /scenarios/{id}/publish` captures an immutable cast/lore/rules/initial-state version. Other users find it at `GET /catalog/scenarios`. Setting `is_public` alone does not publish a draft. A new publication produces a new version. Existing playthroughs keep their pinned version. Scenario deletion archives the template and preserves saved playthroughs.

`POST /chat/start` takes `scenario_id`, `ai_character_id`, optional `user_character_id` or `persona_id`, optional `preferences`, and a stable UUID `request_id`. Reusing that ID with a changed payload returns 409. State, greeting and initial checkpoint are created atomically.

## Commands and mechanics

The Director returns explicit `command_ids`. Python checks prerequisites and applies authored mutations. Legacy `triggers` are interpretation hints only; substring matches never grant items or execute commands.

```json
{
  "mode": "structured",
  "items": {"iron_key":{"id":"iron_key","name":"Iron Key","description":"Opens the cellar","quantity":1}},
  "transitions": [{"id":"take_key","description":"Pick up the key on the table","once":true,"mutations":[{"type":"ITEM_ADDED","target":"iron_key","description":"Picked up key","value_change":1}]}],
  "quests":{"journey":["departed","arrived"]},
  "quest_objectives":{"gather":{"herbs":3}},
  "writing_defaults":{"response_length":"medium","pacing":"slow"}
}
```

Additional authorized mutations: `FLAG_CLEARED`, `QUEST_ADVANCED` (quest ID), `QUEST_PROGRESS` (`quest_id:objective_id`, positive increment), `QUEST_FAILED`, `CLOCK_ADVANCED` (1–1440 story minutes), and `CHARACTER_UPDATED` with typed `character_state` (motive, activity, location, known_facts, promises). No wall-clock progression occurs while away.

Quest lifecycle also supports `QUEST_STARTED` and `QUEST_RESTARTED`. First progress can implicitly activate an inactive quest. Only active quests may fail; failed/completed quests reject further progress until an explicit authored restart resets stages/objectives. Combined quests require both final stage and all objective targets before completing.

Runtime contains `executed_rules`, `quest_progress`, `characters` and `clock_minutes`. Internal execution markers are separate from player flags. Scenario `relationship_thresholds` control status labels. Repeated normalized actions cannot farm affinity within the retained 100-action history. Item/relationship JSON response shapes remain unchanged.

`freeform` permits narrative improvisation while persistent mechanics remain command-controlled. Set `track_relationships:false` with no transitions to skip model validation for freeform dialogue. Director world selection already skips model inference when no event is eligible.

## Save and resume

- `GET /conversations?before=<id>&limit=30`: player library, stable ID pagination.
- `GET /conversations/{id}/resume`: consistent conversation/state/recent-history/preferences/latest-turn snapshot, with a message-ID cursor. The cursor is for SQL history, not a JetStream sequence.
- `PATCH /conversations/{id}`: title, archived boolean, preference overrides.
- Existing history pagination retrieves older messages. Existing turn status/retry endpoints recover failed work.
- Resume does not depend on broker replay retention. Reconnect the existing WebSocket for live events; reconcile against saved messages/state after connection to cover the snapshot-to-subscription interval.

Tokens are provisional. `reply_completed` means Actor prose is saved; durable `director_state_change` with state `completed` means the full turn is complete. State notifications include flags, runtime and state version.

## Preferences and personas

GET/PUT `/preferences` manages language, response_length (short/medium/long), perspective (first/third), pacing (slow/balanced/fast), formatting (asterisks/plain), intensity (gentle/balanced/dramatic).

Precedence: conversation override → user settings → pinned scenario writing defaults → application defaults.

GET/POST `/personas`, PUT/DELETE `/personas/{id}` manage name, background, personality and appearance text. A playthrough snapshots its selected persona; editing a reusable persona does not rewrite ongoing stories.

## Memory and branches

- GET `/conversations/{id}/memories` lists facts and personal notes.
- POST `/conversations/{id}/memories/notes` adds bounded content and a pinned flag; DELETE the note by ID.
- PATCH `/conversations/{id}/memories/{fact_id}` sets corrected content, pinned, forgotten and known_by character names. This endpoint replaces those control settings. Automatic extraction cannot overwrite manual corrections or forgotten facts.
- Restricting, correcting or forgetting facts disables raw episodic retrieval for that conversation, preventing old vector content from overriding those controls. This is a deliberate recall/consistency tradeoff. Raw source messages remain in history; forgetting is a generation-context control, not data erasure.
- POST `/conversations/{id}/fork`: completed `turn_id` or `initial:true`, title and stable request_id.
- POST `/conversations/{id}/regenerate`: same body; produces a new playthrough with an Actor-only generation job. It preserves mechanics and does not re-run Director events. The original story remains accessible.

Regeneration uses an explicit `before_reply` checkpoint, after player-action effects but before Director world effects. Ordinary completed-turn forks use `after_turn`. Historic turns without a provable before-reply checkpoint return 409 for regeneration rather than using an incorrect state.
- POST `/conversations/{id}/edit`: turn_id, replacement content and stable request_id. Forks before that action, then validates the replacement normally.

Branch memories are indexed from their own copied history. Controlled source facts are remapped; future messages and parent vectors are excluded. Historic pre-upgrade checkpoints cannot be reconstructed before the upgrade baseline.

## Telemetry and verification

Run `docker compose -f compose.telemetry.yaml up -d`; Collector health is `http://127.0.0.1:13133/`. Set root `.env` `OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318`, install `pip install -e '.[telemetry]'`, and restart services. Collector receives traces and metrics and exports summaries to Docker logs. It is not a trace-history UI.

`MODEL_CONTEXT_TOKENS` must match the configured model. Known tokenizers use tiktoken; unknown models use a conservative UTF-8 byte bound. Essential state and the latest input are never silently truncated; oversized essential context fails explicitly.

Run the integration suite with `RUN_BACKEND_INTEGRATION=1`. `tools/verify_playthroughs.py` runs real provider calls and removes its own fixtures. Narrative quality evaluation should additionally cover character consistency, player agency, knowledge boundaries, long absence, repeated actions, and preference adherence; deterministic tests do not certify prose quality.

Authenticated `GET /catalog/filters` returns PostgreSQL-managed taxonomy terms. `GET /catalog/scenarios` accepts `q`, `genre`, `tone`, `life_stage`, `gender`, `mode`, `limit` and `before`. Search and all filters operate on the latest public published version. Scenario input/output now includes `discovery: {genres: [], tones: [], life_stage: "any"}`; labels become public with the next publication. See `frontend/DISCOVERY_GUIDE.md` for exact behavior, category validation and database operations. Migration 010 is additive.
