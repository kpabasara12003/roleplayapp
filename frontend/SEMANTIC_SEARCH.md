# Scenario search: meaning, keywords, or both

Implemented 21 November 2026. Discover defaults to **Hybrid** when text is entered. **Similar themes** uses semantic retrieval alone; **Title & keywords** uses PostgreSQL alone. Without search text, the existing latest-first catalog and filters are used. Search modes and all metadata filters can be combined.

Users can write “a mysterious railway journey with strange passengers and hidden secrets.” A real check with the configured BGE-M3 endpoint ranked **The Last Train to Bellweather** first. Exact ranking depends on published content; matches are similarities, not guarantees or percentages.

## Data and architecture

- Existing BGE-M3 provider produces 1024-dimensional dense embeddings. A vector represents the meaning of the public premise and selected cast traits; it is not a copy of conversation history. See the [BGE-M3 model card](https://huggingface.co/BAAI/bge-m3).
- A separate Qdrant collection, `catalog_bge_m3_v1`, stores immutable publication-version vectors and filter payloads. Private chats, player notes, memories and full lore are excluded from embedding documents. Documents are bounded to 6,000 characters.
- PostgreSQL supplies full-text lexical matches plus literal partial-title and creator-username `ILIKE` matches. LIKE wildcard input is escaped. Exact titles receive lexical priority. No fake authors or generated scenario records are used.
- Hybrid combines ranked SQL and vector results using reciprocal rank fusion (RRF), rather than adding incompatible scores. This follows the [rank-fusion approach described by Qdrant](https://qdrant.tech/documentation/search/hybrid-queries/); SQL provides the lexical branch here, not a sparse-vector model or BM25 claim.
- All retrieved IDs are rechecked in PostgreSQL for latest publication, visibility and metadata filters, including each pagination request. Stale/private/archived vectors cannot be returned. Creator names shown on cards come from the owning account.

## Indexing and recovery

Migration `011_semantic_catalog.sql` adds durable per-publication checkpoints. The existing outbox service polls for public publications, indexes four at a time and retries failed versions after two minutes without blocking other publications. Existing public publications are automatically backfilled. Cleanup scans bounded batches of Qdrant points, removes obsolete/private/deleted publications and clears corresponding checkpoints so a re-exposed version can be indexed again.

Keyword publication visibility is immediate; semantic indexing is eventually consistent (normally the next 10-second polling cycle, plus embedding time and queue depth). Existing authoring data is unchanged. A separate model/dimension must use a new collection name and rebuild checkpoints; do not mix embedding spaces in one collection.

The current `DIGITALOCEAN_BGE_URL`, `DIGITALOCEAN_BGE_KEY`, `QDRANT_URL`, optional `QDRANT_API_KEY`, and `VALKEY_URL` are reused. No additional tools, services or ML packages are required. Restart with `python tools/run_stack.py` after applying `python -m shared.db.migrate`.

Operational progress:

```sql
SELECT count(*) FILTER (WHERE indexed_at IS NOT NULL) AS indexed,
       count(*) FILTER (WHERE indexed_at IS NULL) AS retrying
FROM catalog_vector_checkpoints;
```

Unseen new publications have no checkpoint yet. Indexer failures log exception types without provider response bodies or credentials. Publication success does not depend on embedding availability.

## API and pagination

Authenticated `GET /catalog/search` accepts:

- `q`: up to 200 characters; required on the initial ranked request.
- `search_type`: `hybrid` (default), `semantic`, or `keyword`.
- Existing `genre`, `tone`, `life_stage`, `gender`, `mode` filters and `limit` (1–100, default 24).
- `cursor`: the returned cursor for subsequent pages; reuse the same authenticated account. Cursor requests use the stored query snapshot and filters rather than reranking or embedding again.

Response: `{items, next_cursor, search_mode_used, warning}`. Items retain catalog fields and add `creator`. Valkey stores a five-minute user-bound ranking snapshot containing IDs and filters, with a maximum of 200 final matches from candidate lists of at most 200 per retrieval branch. This is a bounded relevance window, not a complete enumeration of arbitrarily large catalogs. Expired cursors return 410; Retry starts a fresh search. Browse `/catalog/scenarios` keeps its descending-ID `before` pagination.

Semantic work has a 12-second deadline. Hybrid falls back to SQL with an explicit warning when vectors/embeddings fail. Semantic-only requests return 503 in that case. Unavailable Valkey search-session storage returns 503. A newly published scenario can be temporarily absent from semantic results until indexed; keyword search remains the immediate route.

## Verification

Regression tests cover fusion, document privacy/size, SQL candidate revalidation, explicit fallback, expired/malformed/user-bound cursors and visibility checks on subsequent pages. Live HTTP checks exercised conceptual retrieval, partial title, partial creator name, hybrid retrieval and distinct ranked pages. The schema snapshot includes migration 011; database verification rolls its temporary schema back.
