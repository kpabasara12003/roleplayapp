import os
import asyncio
from typing import List, Optional, Any

import httpx
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
)
from flashrank import Ranker, RerankRequest
from shared.utils.logger import get_logger

logger = get_logger(__name__)

QDRANT_URL = os.getenv("QDRANT_URL", "http://127.0.0.1:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY") or None
BGE_KEY = os.getenv("DIGITALOCEAN_BGE_KEY")
BGE_URL = os.getenv("DIGITALOCEAN_BGE_URL")

EMBED_DIM = 1024  # BGE-M3 standard vector dimensions
COLLECTIONS = {
    "conversations": "Long-term chat history memory",
    "lorebook": "Pre-defined world info",
    "characters": "Character traits for consistency",
}

_client: Optional[AsyncQdrantClient] = None
_ranker: Optional[Ranker] = None


def get_qdrant_client() -> AsyncQdrantClient:
    """Lazy-initialize the fully asynchronous Qdrant Client."""
    global _client
    if _client is None:
        kwargs: dict = {"url": QDRANT_URL}
        if QDRANT_API_KEY:
            kwargs["api_key"] = QDRANT_API_KEY
        _client = AsyncQdrantClient(**kwargs)
        logger.info("Async Qdrant client initialized on %s", QDRANT_URL)
    return _client


def get_flashrank_client() -> Ranker:
    """Lazy-initialize the lightweight flashrank cross-encoder model."""
    global _ranker
    if _ranker is None:
        # Default model: ms-marco-MiniLM-L-6-v2 (extremely fast and accurate)
        _ranker = Ranker(cache_dir=os.path.join(os.getcwd(), ".cache", "flashrank"))
        logger.info("FlashRank Cross-Encoder Ranker initialized successfully.")
    return _ranker


async def _ensure_collection_exists(collection_name: str):
    """Safely check and automatically initialize missing collections asynchronously."""
    client = get_qdrant_client()
    try:
        exists = await client.collection_exists(collection_name=collection_name)
        if not exists:
            await client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE),
            )
            logger.info("Created missing Qdrant collection: %s", collection_name)
    except Exception as e:
        logger.error("Failed to verify/create Qdrant collection %s: %s", collection_name, e)
        raise e


async def embed_texts(texts: List[str]) -> List[List[float]]:
    """
    Call DO BGE-M3 inference endpoint to generate vector embeddings.
    Includes an asynchronous exponential backoff routine to cleanly recover from 429 Rate Limits.
    """
    if not texts:
        return []
    
    if not BGE_URL or not BGE_KEY:
        raise ValueError("Missing DIGITALOCEAN_BGE_URL or DIGITALOCEAN_BGE_KEY environment config.")

    payload = {"input": texts, "model": "bge-m3"}
    headers = {
        "Authorization": f"Bearer {BGE_KEY}",
        "Content-Type": "application/json",
    }

    max_retries = 4
    backoff_factor = 2.0

    async with httpx.AsyncClient(timeout=30.0) as client:
        for attempt in range(max_retries):
            try:
                resp = await client.post(BGE_URL, headers=headers, json=payload)
                
                if resp.status_code == 429:
                    sleep_time = backoff_factor ** attempt
                    logger.warning("BGE Embedding API returned 429. Backing off for %.1fs (Attempt %d/%d)", sleep_time, attempt + 1, max_retries)
                    await asyncio.sleep(sleep_time)
                    continue
                
                resp.raise_for_status()
                data = resp.json()
                return [item["embedding"] for item in data["data"]]
                
            except httpx.HTTPError as e:
                if attempt == max_retries - 1:
                    logger.error("Persistent HTTP error executing embedding generation: %s", e)
                    raise e
                await asyncio.sleep(backoff_factor ** attempt)
    return []


async def upsert_points(collection: str, points: List[PointStruct]):
    """Insert context vectors non-blockingly into the target index."""
    await _ensure_collection_exists(collection)
    client = get_qdrant_client()
    try:
        await client.upsert(collection_name=collection, points=points, wait=True)
        logger.debug("Successfully upserted %d vector points into %s", len(points), collection)
    except Exception as e:
        logger.error("Failed to execute upsert operation inside collection %s: %s", collection, e)
        raise e


def _build_filter(filters: Optional[dict]) -> Optional[Filter]:
    """Dynamically compile dictionary filter representations into Qdrant Filter objects."""
    if filters is None:
        return None
    if isinstance(filters, Filter):
        return filters

    conditions = []
    
    # Handle targeted dictionary conditions
    for key, value in filters.items():
        if key == "must" and isinstance(value, list):
            for cond in value:
                mk = cond.get("key")
                mv = cond.get("match", {}).get("value")
                if mk and mv is not None:
                    conditions.append(FieldCondition(key=mk, match=MatchValue(value=mv)))
        elif isinstance(value, dict) and "match" in value:
            match_value = value["match"].get("value")
            if match_value is not None:
                conditions.append(FieldCondition(key=key, match=MatchValue(value=match_value)))
        elif not isinstance(value, (dict, list)):
            conditions.append(FieldCondition(key=key, match=MatchValue(value=value)))

    if conditions:
        return Filter(must=conditions)
    return None


async def search_similar(
    collection: str,
    vector: List[float],
    limit: int = 5,
    filters: Optional[dict] = None,
) -> List[dict]:
    """Execute vector similarity search over an index non-blockingly."""
    await _ensure_collection_exists(collection)
    client = get_qdrant_client()
    qf = _build_filter(filters)
    
    try:
        results = await client.search(
            collection_name=collection,
            query_vector=vector,
            limit=limit,
            query_filter=qf
        )
        return [
            {
                "id": r.id,
                "score": r.score,
                "payload": r.payload or {},
            }
            for r in results
        ]
    except Exception as e:
        logger.error("Database query exception running similarity search on %s: %s", collection, e)
        return []


def rerank_documents(query: str, documents: List[dict], top_n: int = 5) -> List[dict]:
    """
    Reranks vector search results using a local Cross-Encoder model.
    Filters out semantic noise, keeping only highly relevant contextual matches.
    """
    if not documents:
        return []
    
    try:
        ranker = get_flashrank_client()
        
        # Format the documents to match the input structure needed by FlashRank
        passages = []
        for idx, doc in enumerate(documents):
            # Fallback chains to locate the textual content to parse
            text_content = (
                doc.get("payload", {}).get("summary") or 
                doc.get("payload", {}).get("content") or 
                str(doc.get("payload", {}))
            )
            passages.append({
                "id": idx, 
                "text": text_content,
                "meta": doc # Preserve parent dict reference structure
            })
            
        rerank_request = RerankRequest(query=query, passages=passages)
        ranked_results = ranker.rerank(rerank_request)
        
        # Reassemble the payload records sorted by the new Cross-Encoder score metric
        final_docs = []
        for record in ranked_results[:top_n]:
            original_doc = record["meta"]
            original_doc["rerank_score"] = float(record["score"])
            final_docs.append(original_doc)
            
        logger.debug("Successfully reranked documents down to top_%d entries", len(final_docs))
        return final_docs
        
    except Exception as e:
        logger.error("Reranking pipeline crashed, defaulting to base vector ordering: %s", e)
        return documents[:top_n]