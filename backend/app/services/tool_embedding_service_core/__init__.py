"""Core helpers for ToolEmbeddingService."""

from .constants import (
    CREATE_TABLE_SQL,
    NOMIC_MODELS,
    RAG_ERROR,
    RAG_HIT,
    RAG_MISS,
)
from .errors import MultiModelIndexingError
from .manifest_context import get_capability_manifest_context
from .model_selection import discover_embed_models, get_current_embedding_model
from .types import IndexableEntry, ToolMatch
from .utils import (
    build_embed_text,
    filter_mapping_rows_by_score,
    fuse_ranked_tool_matches,
    mapping_row_to_tool_match,
    tuple_row_to_tool_match,
    vector_to_pg_literal,
)

__all__ = [
    "CREATE_TABLE_SQL",
    "IndexableEntry",
    "MultiModelIndexingError",
    "NOMIC_MODELS",
    "RAG_ERROR",
    "RAG_HIT",
    "RAG_MISS",
    "ToolMatch",
    "build_embed_text",
    "discover_embed_models",
    "filter_mapping_rows_by_score",
    "fuse_ranked_tool_matches",
    "get_capability_manifest_context",
    "get_current_embedding_model",
    "mapping_row_to_tool_match",
    "tuple_row_to_tool_match",
    "vector_to_pg_literal",
]
