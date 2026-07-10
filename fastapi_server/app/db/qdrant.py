"""Thin wrapper re-exporting shared Qdrant utilities."""
from shared.db.qdrant import (
    get_qdrant_client,
    embed_texts,
    upsert_points,
    search_similar,
)

__all__ = [
    "get_qdrant_client",
    "embed_texts",
    "upsert_points",
    "search_similar",
]
