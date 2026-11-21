# Multi-Agent Roleplay Backend

FastAPI/WebSocket gateway with three roleplay agents, PostgreSQL-backed turn workflows, NATS/JetStream event delivery, Qdrant retrieval, and Valkey provider admission/cache.

## Start on Windows / PowerShell

From the repository root, activate a Python 3.14 virtual environment, then:

```powershell
python -m pip install -e .
python tools/run_stack.py
```

Or run `bash run.sh` using Git Bash, WSL, or Linux. The supervisor applies versioned SQL migrations and starts the gateway, three agents, and an independent outbox/recovery worker. Ctrl+C stops the stack. Service logs are under `logs/`.

For a fresh/empty database, apply the complete `database.sql` snapshot once; it includes all tables and migration-version records. Existing databases use only the incremental migration CLI, which the launchers run automatically. Do not apply the fresh-install snapshot over existing tables. Set root `.env` from `.env.example`. PostgreSQL, NATS with JetStream, Qdrant, and Valkey must already be running; the LLM and BGE-M3 endpoints must be configured.

Valkey is accessed through `redis://127.0.0.1:6379/0`, not HTTP. No new external workflow engine is required.

## Architecture

```text
Client -> Gateway -> saved turn + validation job
                         |
                    Director validation -> Python rule authorization
                         |
                    Actor generation -> persisted reply
                         |
                    Director world event -> completed turn

All stage handoffs: SQL transaction + outbox -> NATS pull consumers
Independent outbox worker: delivery retry + expired-job recovery
Chronicler: semantic memory, authored lore, indexing, vector cleanup
Valkey: shared provider limits, concurrency slots, circuit breaker, embedding cache
```

PostgreSQL owns conversations, state versions, turn status, job ownership/fences, source messages, and memory checkpoints. Qdrant is a derived retrieval index. Models propose changes; configured Python rules authorize mechanical effects. Stale or duplicate workers cannot commit the same turn stage.

The gateway accepts input asynchronously. Clients supply a stable `request_id` UUID and can inspect `/chat/turn/{turn_id}` or resume a failed stage with `/chat/turn/{turn_id}/retry`. WebSocket access uses single-use tickets from `/chat/ticket/{conversation_id}`. The supplied frontend implements ticket authentication and sends request IDs.

Author scenario mechanics using `rules.transitions` and `rules.world_events`; unconfigured scenarios allow dialogue but do not allow model-invented inventory or quest changes. Author lore through `/scenarios/{id}/lore`.

## Verify

```powershell
python -m unittest discover -s tests -v
$env:RUN_BACKEND_INTEGRATION='1'
python -m unittest discover -s tests -v
python tools/smoke_check.py
```

`/health` reports process liveness; `/ready` checks worker/dependency availability; `/diagnostics` reports backlogs and stage latency. OpenTelemetry spans/metrics are exported locally under `logs/telemetry/`, with optional OTLP support.

Regenerate the full schema with `python tools/export_database_schema.py`; validate it in a rolled-back temporary schema with `python tools/check_database_schema.py`.

Valkey Admin at `http://localhost:8080/` runs inside Docker: connect to `host.docker.internal`, port `6379`, database `0`. The local development server has no username/password or TLS. The Python app on Windows continues using `redis://127.0.0.1:6379/0`.

See [IMPLEMENTATION_NOTES.md](IMPLEMENTATION_NOTES.md) for workflow behavior and configuration. [AUDIT_REPORT.md](AUDIT_REPORT.md) contains the completed audit status, validation results, and cleanup summary.


## Persistent scenarios and saved stories

See [ROLEPLAY_API.md](ROLEPLAY_API.md) for publication, public playthroughs, resume, player personas/preferences, quests, state history, memory controls and isolated story forks. [BACKEND_UPGRADE.md](BACKEND_UPGRADE.md) tracks the implemented scope and verification. This upgrade adds backend APIs; the existing test frontend does not yet provide dedicated screens for every new endpoint.

Start the telemetry collector with `docker compose -f compose.telemetry.yaml up -d`. Install `pip install -e '.[telemetry]'` and set `OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318` in root `.env`. Health is at `http://127.0.0.1:13133/`; view received traces/metrics with `docker compose -f compose.telemetry.yaml logs --tail 30`.

Stop a supervised stack gracefully with `python tools/run_stack.py --stop`. Run `python tools/verify_playthroughs.py` for live upgrade checks and `python tools/evaluate_roleplay.py` for reviewable narrative samples; both use real model calls, and the former removes only its own fixtures.
