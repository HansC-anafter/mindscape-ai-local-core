"""Tool embedding service facade.

Indexes and searches tool embeddings in pgvector for RAG-based tool discovery.
The resource-touching implementation lives in helper modules so this facade
remains the single caller-facing path.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backend.app.database.config import get_vector_postgres_config
from backend.app.services.tool_embedding_generation import (
    generate_embedding as _generate_embedding,
    generate_embedding_for_model as _generate_embedding_for_model,
)
from backend.app.services.tool_embedding_indexing import (
    collect_indexable_entries as _collect_indexable_entries,
    ensure_indexed as _ensure_indexed,
    index_all_tools as _index_all_tools,
    index_all_tools_for_model as _index_all_tools_for_model,
    index_all_tools_multimodel as _index_all_tools_multimodel,
    index_tool as _index_tool,
    reindex_all as _reindex_all,
)
from backend.app.services.tool_embedding_schema import (
    ensure_table as _ensure_table,
    get_capability_embedding_status as _get_capability_embedding_status,
    has_existing_index as _has_existing_index,
    remove_tool as _remove_tool,
    remove_tools_by_capability as _remove_tools_by_capability,
)
from backend.app.services.tool_embedding_search import (
    get_indexed_models as _get_indexed_models,
    search as _search,
    search_bm25 as _search_bm25,
    search_by_affordance as _search_by_affordance,
    search_rrf as _search_rrf,
    search_single_model as _search_single_model,
)
from backend.app.services.tool_embedding_service_core import (
    IndexableEntry,
    RAG_ERROR,
    RAG_HIT,
    RAG_MISS,
    ToolMatch,
    get_capability_manifest_context,
    get_current_embedding_model,
)

__all__ = [
    "IndexableEntry",
    "RAG_ERROR",
    "RAG_HIT",
    "RAG_MISS",
    "ToolEmbeddingService",
    "ToolMatch",
]


class ToolEmbeddingService:
    """Index and search tool embeddings in pgvector."""

    _manifest_cache: dict[str, Optional[str]] = {}

    def __init__(self, postgres_config: Optional[Dict[str, Any]] = None):
        self.postgres_config = postgres_config or get_vector_postgres_config()

    def _get_connection(self):
        """Get PostgreSQL connection to vector DB."""
        import psycopg2

        return psycopg2.connect(**self.postgres_config)

    def _get_current_model(self) -> str:
        """Get current embedding model name."""
        return get_current_embedding_model()

    async def _generate_embedding(
        self, text: str, *, is_query: bool = True
    ) -> Tuple[Optional[List[float]], Optional[str]]:
        """Generate an embedding using the existing VectorSearchService path."""
        return await _generate_embedding(self, text, is_query=is_query)

    async def _generate_embedding_for_model(
        self, text: str, model_name: str, *, is_query: bool = True
    ) -> Tuple[Optional[List[float]], Optional[str]]:
        """Generate an embedding using a specific Ollama model."""
        return await _generate_embedding_for_model(
            self, text, model_name, is_query=is_query
        )

    async def ensure_table(self) -> None:
        """Verify the migration-owned tool_embeddings schema."""
        await _ensure_table(self)

    def _get_capability_manifest_context(self, capability_code: str) -> Optional[str]:
        """Read cached capability manifest metadata for embedding enrichment."""
        return get_capability_manifest_context(
            cache=self._manifest_cache,
            capability_code=capability_code,
            services_dir=Path(__file__).resolve().parent,
        )

    async def index_tool(
        self,
        tool_id: str,
        display_name: str,
        description: str,
        category: str,
        capability_code: Optional[str] = None,
        affordance: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Embed and upsert a single tool."""
        return await _index_tool(
            self,
            tool_id=tool_id,
            display_name=display_name,
            description=description,
            category=category,
            capability_code=capability_code,
            affordance=affordance,
        )

    async def _collect_indexable_entries(
        self, *, include_playbooks: bool = True
    ) -> List[IndexableEntry]:
        """Return the shared tool/playbook corpus used for embedding indexing."""
        return await _collect_indexable_entries(
            self, include_playbooks=include_playbooks
        )

    async def index_all_tools(self, *, include_playbooks: bool = True) -> int:
        """Index all tools from ToolListService."""
        return await _index_all_tools(self, include_playbooks=include_playbooks)

    async def ensure_indexed(self, *, include_playbooks: bool = True) -> int:
        """Startup hook: index stale embedding models."""
        return await _ensure_indexed(self, include_playbooks=include_playbooks)

    async def remove_tool(self, tool_id: str) -> bool:
        """Remove a tool's embeddings across all models."""
        return await _remove_tool(self, tool_id)

    async def remove_tools_by_capability(self, capability_code: str) -> int:
        """Remove all tool embeddings for a capability pack."""
        return await _remove_tools_by_capability(self, capability_code)

    async def has_existing_index(self, *, min_rows: int = 1) -> bool:
        """Return whether the embedding table already has a usable corpus."""
        return await _has_existing_index(self, min_rows=min_rows)

    async def get_capability_embedding_status(
        self, capability_code: str
    ) -> Dict[str, Any]:
        """Return current embedding coverage for one capability code."""
        return await _get_capability_embedding_status(self, capability_code)

    async def search(
        self,
        query: str,
        top_k: int = 15,
        min_score: float = 0.3,
    ) -> Tuple[List[ToolMatch], str]:
        """Search tool embeddings by cosine similarity."""
        return await _search(self, query, top_k=top_k, min_score=min_score)

    async def get_indexed_models(self) -> List[str]:
        """Return all distinct indexed embedding models."""
        return await _get_indexed_models(self)

    async def _search_single_model(
        self,
        query_embedding: List[float],
        model_name: str,
        top_k: int,
        min_score: float = 0.0,
    ) -> List[ToolMatch]:
        """Vector search restricted to one embedding model."""
        return await _search_single_model(
            self,
            query_embedding,
            model_name,
            top_k,
            min_score=min_score,
        )

    async def search_bm25(
        self,
        query: str,
        top_k: int = 15,
    ) -> List[ToolMatch]:
        """BM25 lexical search using PostgreSQL tsvector."""
        return await _search_bm25(self, query, top_k=top_k)

    async def search_rrf(
        self,
        query: str,
        top_k: int = 15,
        min_score: float = 0.3,
        rrf_k: int = 60,
    ) -> Tuple[List[ToolMatch], str]:
        """Multi-model Reciprocal Rank Fusion search."""
        return await _search_rrf(
            self,
            query,
            top_k=top_k,
            min_score=min_score,
            rrf_k=rrf_k,
        )

    async def search_by_affordance(
        self,
        consumes_types: List[str],
    ) -> List[ToolMatch]:
        """Search playbooks that consume any of the specified asset types."""
        return await _search_by_affordance(self, consumes_types)

    async def index_all_tools_multimodel(
        self, *, include_playbooks: bool = True
    ) -> int:
        """Re-index all tools for every available Ollama embed model."""
        return await _index_all_tools_multimodel(
            self, include_playbooks=include_playbooks
        )

    async def _index_all_tools_for_model(
        self, model_name: str, *, include_playbooks: bool = True
    ) -> int:
        """Index all tools and playbooks using a specific embedding model."""
        return await _index_all_tools_for_model(
            self, model_name, include_playbooks=include_playbooks
        )

    async def reindex_all(self) -> int:
        """Re-embed all tools with the current model."""
        return await _reindex_all(self)
