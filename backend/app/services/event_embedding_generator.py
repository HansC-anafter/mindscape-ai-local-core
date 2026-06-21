"""
Event Embedding Generator Service

Automatically generates embeddings for mind events with text content.
Stores embeddings in memory_embeddings table for semantic search (L2).
Legacy: previously wrote to mindscape_personal, now frozen (ADR-001 v2).
"""

from backend.app.services.event_embedding_generator_core import (
    EventEmbeddingGenerator,
    _utc_now,
)

__all__ = ["EventEmbeddingGenerator", "_utc_now"]
