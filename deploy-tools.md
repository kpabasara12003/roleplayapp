# Local Development Infrastructure

Docker Compose stack for local backend development, messaging, vector storage, caching, and OpenTelemetry ingestion.

## Services & Endpoints

| Service | Container Name | Port(s) | Endpoint / Dashboard | Persistence Volume |
| :--- | :--- | :--- | :--- | :--- |
| **NATS / JetStream** | `nats-jetstream` | `4222`, `8222` | `nats://localhost:4222` / `http://localhost:8222` | `nats_data` |
| **OpenTelemetry Collector** | `otel-collector` | `4318`, `13133` | `http://localhost:4318` / `http://localhost:13133` | Stateless |
| **Valkey** | `valkey-dev` | `6379` | `redis://localhost:6379` | `valkey_data` |
| **Valkey Admin** | `valkey-admin` | `8081` | `http://localhost:8081` | Stateless |
| **Qdrant** | `qdrant-dev` | `6333`, `6334` | `http://localhost:6333/dashboard` | `qdrant_storage` |

## Usage

### Start All Services
```bash
docker compose up -d
```

### Stop Services (Preserves All Data)
Stopping or removing containers leaves `nats_data`, `valkey_data`, and `qdrant_storage` intact on disk:
```bash
docker compose stop
# or
docker compose down
```

### Wipe All Persistent Data
Only run with `-v` if you intentionally want to reset JetStream streams, Valkey keys, and Qdrant collections:
```bash
docker compose down -v
```

## Verification

1. **Container Status:**
   ```bash
   docker compose ps
   ```
   All 5 containers should report `Up` or `running`.

2. **NATS JetStream:**
   Open `http://localhost:8222/jsz` in a browser to verify JetStream is active.

3. **OpenTelemetry Health Check:**
   Open `http://localhost:13133` in a browser or run `curl http://localhost:13133` to verify `Server available`.

4. **Valkey & Admin UI:**
   Open `http://localhost:8081` to inspect `valkey-dev` keys.

5. **Qdrant Dashboard:**
   Open `http://localhost:6333/dashboard` to inspect collections and verify persisted vectors survive `docker compose down` and `docker compose up -d`.

6. **Update .env file**