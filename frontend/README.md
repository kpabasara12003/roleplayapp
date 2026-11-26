# Roleplay AI — Frontend Client

A text-only roleplay studio, branded **fable.**, matching the backend specification in `FRONTEND_GUIDE.md` and `ROLEPLAY_API.md`.

Discovery now searches all published scenarios in PostgreSQL with database-managed genre, tone, life-stage and AI-character gender filters. See [DISCOVERY_GUIDE.md](DISCOVERY_GUIDE.md) for API contracts, creator labels and database operations. The previous loaded-page-only search described below has been replaced.

Text searches now support Hybrid, Similar themes (BGE-M3/Qdrant), or Title & keywords, including partial titles and creator names. See [SEMANTIC_SEARCH.md](SEMANTIC_SEARCH.md) for indexing, ranked pagination and failure behavior. Browse/filter behavior remains compatible.

## 1. Quick Start

### Serve the frontend
Serve the `frontend/` directory over HTTP (do not open `index.html` via `file://`):
```bash
python -m http.server 5500 --directory frontend
```
Then open [http://localhost:5500](http://localhost:5500) in your web browser.

### Backend server
Ensure the backend is running at `http://localhost:8000`:
```bash
python tools/run_stack.py
```
*(Requires PostgreSQL, NATS, Valkey, and Qdrant).*

---

## 2. Architecture & Design

Built as a zero-build React client with vendored dependencies, running natively in modern browsers without needing an npm build or bundler step:
- **Design System:** Warm paper, deep green, lime accents and serif story typography, with a coordinated dark palette. The Appearance control offers Light, Dark and System; the choice persists on this browser.
- **Vendored Core:** React 18 & ReactDOM are served locally from `vendor/`. Scripts load only from this origin; there is no CDN fallback.
- **Source/runtime:** Most `.tsx`/`.ts` files contain plain JavaScript and have identical served `.js` copies. `api/client.ts` and `components/ConfirmDialog.tsx` now have real TypeScript types; their `.js` files are generated. `theme.js` runs before CSS to avoid flashing the wrong theme; `validation.js` loads before the screens.
- **State Store (`src/store/`):**
  - `session.js`: Encapsulated localStorage session, API key, user credentials, and active navigation persistence.
  - `conversationStore.js`: Normalized conversation store indexing messages by ID, pending submissions by request ID, stream chunks by `turn:generation:attempt`, turn status, and live game mechanics.
- **API & Real-time Layer (`src/api/`):**
  - `client.js`: HTTP client preserving error status codes (401, 404, 409, 422 with field validation, 429), configurable base URL, and authenticated requests.
  - `ws.js`: WebSocket manager requesting single-use tickets (`/chat/ticket/{id}`), handling reconnects with exponential backoff & jitter, checkpoint sequence tracking (`stream_sequence_id`), and live event parsing.
- **Components (`src/components/`):**
  - `Modal.js`: Accessible modal with Escape key handling and focus trap.
  - `ConfirmDialog.js`: Confirmation modal for destructive actions.
  - `Toast.js`: Non-blocking auto-dismissing toast notifications.
  - `ErrorBanner.js`: Field-level and structured error banner with dismiss.
  - `LoadingSpinner.js`, `EmptyState.js`: Consistent loading indicators and zero-state placeholders.

---

## 3. Implemented Screens

1. **Authentication (`src/screens/AuthScreen.js`):**
   - User registration (`POST /users/register`) and login (`POST /users/login`).
   - Secure session key handling; clears stale state upon user switch or logout.
   - Configurable server backend URL directly in the UI.

2. **Public Catalog (`src/screens/Catalog.js`):**
   - Browse published scenarios (`GET /catalog/scenarios`).
   - Published definition cast picker with AI character selection.
   - Start playthrough modal (`POST /chat/start`) with stable UUID `request_id`, response length preferences, and persona selection.

3. **Saved Stories (`src/screens/SavedStories.js`):**
   - Paginated conversations list (`GET /conversations?limit=30&before={id}`).
   - Direct resume without calling `/chat/start`.
   - Rename story (`PATCH /conversations/{id}` with title).
   - Archive and restore story (`PATCH /conversations/{id}` with `archived: true/false`).
   - Visual badges for story status and branch parent linking.

4. **Chat & Real-time Playthrough (`src/screens/ChatScreen.js`):**
   - Live streaming bubble appending tokens with chunk attempt deduplication (`turn:gen:attempt`).
   - Safe roleplay text formatting (spoken dialogue in pearl, `*actions*` in lavender-gray italics, `**bold**`).
   - Composer lock during turn generation; prevents duplicate submissions.
   - Real-time connection status pill with retry backoff countdown.
   - **Game-State Panel:**
     - Authoritative inventory list (name, description, quantity).
     - Character relationship status and affinity bar (-100 to +100).
     - Authoritative quests, runtime progress, quest flags, and story clock (`runtime.clock_minutes`).
   - **Story Branching Controls:**
     - **Regenerate:** Actor-only fork from before-reply checkpoint (`POST /conversations/{id}/regenerate`).
     - **Edit:** Fork before selected player action with replacement prose (`POST /conversations/{id}/edit`).
     - **Fork:** Fork story at turn state or initial checkpoint (`POST /conversations/{id}/fork`).
     - **Retry:** Resumes eligible failed turns (`POST /chat/turn/{turn_id}/retry`).

5. **Creator Workspace (`src/screens/MyScenarios.js` & `ScenarioEditor.js`):**
   - Scenario drafting (`GET`, `POST`, `PATCH`, `DELETE /scenarios`).
   - Cast editor (`GET`, `POST /characters`, `PATCH`, `DELETE /characters/{id}`).
   - Lore repository (`GET`, `POST /scenarios/{id}/lore`, `PUT`, `DELETE /scenarios/{id}/lore/{lore_id}`).
   - Structured and advanced JSON rule & initial-state editor with validation.
   - Publish action (`POST /scenarios/{id}/publish`) creating an immutable catalog version.

6. **Personalization (`src/screens/Preferences.js` & `PersonasScreen.js`):**
   - User writing preferences (`GET`, `PUT /preferences`): language, response length, perspective, pacing, formatting, and intensity.
   - Reusable fictional personas CRUD (`GET`, `POST /personas`, `PUT`, `DELETE /personas/{id}`).

7. **Memory & Notes (`src/screens/MemoryScreen.js`):**
   - View conversation facts and notes (`GET /conversations/{id}/memories`).
   - Fact correction, pin, forget (`suppressed`), and character visibility (`PATCH /conversations/{id}/memories/{fact_id}`) sending the complete control state.
   - Personal player notes (`POST /conversations/{id}/memories/notes` and `DELETE /conversations/{id}/memories/notes/{note_id}`).

---

## 4. Verification & Testing

The two typed sources are checked with `tsc -p frontend/tsconfig.json`. Regenerate their browser copies from the repository root using `node tools/sync_frontend_types.cjs <path-to-installed-typescript.js>`; add `--check` to verify without writing. The installed VS Code TypeScript extension includes this compiler library, so no browser bundler or new runtime dependency is required. Do not copy TypeScript annotations directly into the served `.js` files. Other source/runtime pairs remain identical copies.

- **Focused checks:** Run `node --test frontend/tests/*.test.cjs` for transport, state ordering, authoring validation, theme persistence, entry loading and server/session isolation. These are bounded checks, not exhaustive endpoint or security coverage.
- **Offline Reliability:** React 18 and ReactDOM vendored locally in `vendor/` to allow completely offline execution.
