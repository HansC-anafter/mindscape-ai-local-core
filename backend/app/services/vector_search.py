"""
Vector Search Service
Provides semantic search across pgvector tables
"""

import logging
from typing import List, Dict, Any, Optional
import psycopg2

from backend.app.database.config import get_vector_postgres_config
from backend.app.services.vector_search_db import (
    search_vectors,
    update_last_used_at_records,
)
from backend.app.services.vector_search_embeddings import VectorEmbeddingGenerator

logger = logging.getLogger(__name__)


class VectorSearchService:
    """Semantic search service using pgvector"""

    def __init__(self, postgres_config=None):
        self.postgres_config = postgres_config or self._get_postgres_config()
        self.embedding_generator = VectorEmbeddingGenerator()

    def _get_postgres_config(self):
        """Get PostgreSQL config from environment"""
        return get_vector_postgres_config()

    def _get_connection(self):
        """Get PostgreSQL connection"""
        return psycopg2.connect(**self.postgres_config)

    async def check_connection(self) -> bool:
        """Check if Vector DB connection is available"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
            conn.close()
            return True
        except Exception as e:
            logger.warning(f"Vector DB connection check failed: {e}")
            return False

    async def _generate_embedding(self, text: str) -> Optional[List[float]]:
        """Generate embedding for query text using configured model

        Priority:
        1. Ollama (local) - preferred for local development
        2. OpenAI - fallback if Ollama unavailable
        """
        return await self.embedding_generator.generate_embedding(text)

    async def _generate_embedding_with_model(
        self, text: str, *, is_query: bool = True
    ) -> tuple[Optional[List[float]], Optional[str]]:
        """Generate embedding and return both embedding and model name.

        Prefers bge-m3 when available (best multilingual quality);
        falls back to nomic-embed-text, then OpenAI.

        Args:
            text: Text to embed.
            is_query: True for search, False for indexing (controls nomic prefix).

        Returns:
            Tuple of (embedding, model_name) or (None, None) if failed
        """
        return await self.embedding_generator.generate_embedding_with_model(
            text, is_query=is_query
        )

    def _get_ollama_url(self) -> Optional[str]:
        """Return a reachable Ollama base URL, or None.

        Tries the env-var first, then common Docker hostnames in order.
        Uses a synchronous check so it can be called from sync context.
        """
        return self.embedding_generator.get_ollama_url()

    async def _generate_ollama_embedding(
        self, text: str, model: Optional[str] = None, *, is_query: bool = True
    ) -> Optional[List[float]]:
        """Generate embedding using Ollama local model.

        Args:
            text: Text to embed.
            model: Exact model name to use. Defaults to OLLAMA_EMBED_MODEL
                   env var or bge-m3 (preferred for multilingual quality).
            is_query: True for search queries, False for indexing documents.
                      Controls nomic task prefix (search_query: / search_document:).
        """
        return await self.embedding_generator.generate_ollama_embedding(
            text, model=model, is_query=is_query
        )

    async def _generate_openai_embedding(self, text: str) -> Optional[List[float]]:
        """Generate embedding using OpenAI API (fallback)"""
        return await self.embedding_generator.generate_openai_embedding(text)

    async def vector_search(
        self,
        table: str,
        query_embedding: List[float],
        filters: Dict[str, Any] = None,
        top_k: int = 5,
        require_model_match: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Generic vector search across any table

        Args:
            table: Table name (memory_embeddings, playbook_knowledge, external_docs)
            query_embedding: Query vector
            filters: Additional filters (e.g., {"playbook_code": "xxx"})
            top_k: Number of results
            require_model_match: If True, only search embeddings created with the same model

        Returns:
            List of matching records with similarity scores
        """
        return await search_vectors(
            get_connection=self._get_connection,
            table=table,
            query_embedding=query_embedding,
            filters=filters,
            top_k=top_k,
            require_model_match=require_model_match,
        )

    async def search_playbook_sop(
        self, playbook_code: str, query: str, top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Search for relevant Playbook SOP chunks

        Args:
            playbook_code: Playbook identifier
            query: User query
            top_k: Number of results

        Returns:
            List of relevant SOP chunks
        """
        query_embedding = await self._generate_embedding(query)
        if not query_embedding:
            return []

        return await self.vector_search(
            table="playbook_knowledge",
            query_embedding=query_embedding,
            filters={"playbook_code": playbook_code},
            top_k=top_k,
        )

    async def search_personal_context(
        self, user_id: str, query: str, top_k: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Search user's personal semantic memory (L2).

        ADR-001 v2: queries memory_embeddings (L2) instead of mindscape_personal.
        Falls back to mindscape_personal if memory_embeddings is empty.

        Args:
            user_id: User identifier
            query: User query
            top_k: Number of results

        Returns:
            List of relevant personal context
        """
        query_embedding = await self._generate_embedding(query)
        if not query_embedding:
            return []

        # Primary: L2 memory_embeddings
        results = await self.vector_search(
            table="memory_embeddings",
            query_embedding=query_embedding,
            filters={"user_id": user_id},
            top_k=top_k,
        )

        # Fallback: legacy mindscape_personal (frozen, read-only)
        if not results:
            results = await self.vector_search(
                table="mindscape_personal",
                query_embedding=query_embedding,
                filters={"user_id": user_id},
                top_k=top_k,
            )

        return results

    async def execute_playbook_with_context(
        self, playbook_code: str, user_query: str, user_id: str = "default_user"
    ) -> Dict[str, Any]:
        """
        Execute playbook with combined context from SOP and personal memory

        Searches both playbook SOP knowledge and user's personal context to provide
        comprehensive context for AI agent execution.

        Args:
            playbook_code: Playbook identifier
            user_query: User's query or task description
            user_id: User identifier

        Returns:
            Combined context for AI with formatted text
        """
        playbook_chunks = await self.search_playbook_sop(
            playbook_code=playbook_code, query=user_query, top_k=5
        )

        personal_context = await self.search_personal_context(
            user_id=user_id, query=user_query, top_k=3
        )

        context = {
            "playbook_sop": [
                {
                    "content": chunk["content"],
                    "section_type": chunk["section_type"],
                    "similarity": chunk["similarity"],
                }
                for chunk in playbook_chunks
            ],
            "personal_context": [
                {
                    "content": ctx["content"],
                    "source_type": ctx["source_type"],
                    "similarity": ctx["similarity"],
                }
                for ctx in personal_context
            ],
        }

        context_text = self._format_context_for_llm(context)

        return {
            "context": context,
            "context_text": context_text,
            "playbook_code": playbook_code,
        }

    def _format_context_for_llm(self, context: Dict[str, Any]) -> str:
        """Format context for LLM consumption"""
        parts = []

        if context["playbook_sop"]:
            parts.append("## Playbook SOP:")
            for i, chunk in enumerate(context["playbook_sop"], 1):
                parts.append(
                    f"\n### {chunk['section_type'].title()} (similarity: {chunk['similarity']:.2f})"
                )
                parts.append(chunk["content"])

        if context["personal_context"]:
            parts.append("\n\n## Your Personal Context:")
            for i, ctx in enumerate(context["personal_context"], 1):
                parts.append(
                    f"\n### {ctx['source_type']} (similarity: {ctx['similarity']:.2f})"
                )
                parts.append(ctx["content"])

        return "\n".join(parts)

    async def search_external_docs(
        self,
        query: str,
        source_apps: List[str] = None,
        user_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        access_context: Any = None,
        top_k: int = 10,
        require_model_match: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Scenario 2: Search external knowledge (RAG)

        Args:
            query: Search query
            source_apps: Filter by source apps (wordpress, notion, etc.)
            user_id: User identifier
            top_k: Number of results
            require_model_match: If True, only search embeddings from same model

        Returns:
            List of relevant external documents
        """
        del require_model_match
        if access_context is None or not workspace_id:
            raise ValueError(
                "authorization_aware_external_docs_context_required"
            )
        if user_id and user_id != access_context.subject_user_id:
            raise ValueError("external_docs_subject_mismatch")
        from backend.app.services.knowledge_retrieval import (
            AuthorizationAwareKnowledgeRetrievalFacade,
            KnowledgeRetrievalRequest,
        )

        result = await AuthorizationAwareKnowledgeRetrievalFacade(
            vector_service=self,
        ).search(
            KnowledgeRetrievalRequest(
                query=query,
                access_context=access_context,
                scope_type="workspace",
                scope_id=workspace_id,
                top_k=max(1, min(top_k, 20)),
                source_apps=tuple(source_apps or ()),
            )
        )
        return [
            {
                "id": hit.citation.get("chunk_id") or hit.source_id,
                "user_id": access_context.subject_user_id,
                "source_app": hit.source_app,
                "source_id": hit.source_id,
                "content": hit.content,
                "metadata": dict(hit.metadata),
                "similarity": hit.score,
                "knowledge_resource_id": hit.knowledge_resource_id,
                "projection_revision_id": hit.projection_revision_id,
            }
            for hit in result.hits
        ]

    async def multi_scope_search(
        self,
        query: str,
        user_id: str,
        workspace_id: Optional[str] = None,
        intent_id: Optional[str] = None,
        scopes: List[str] = None,
        top_k_per_scope: Dict[str, int] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Multi-scope hierarchical memory search

        Args:
            query: Search query text
            user_id: User identifier
            workspace_id: Optional workspace ID
            intent_id: Optional intent ID
            scopes: List of scopes to search ('global', 'workspace', 'intent')
            top_k_per_scope: Dict mapping scope to top_k (e.g., {'global': 3, 'workspace': 8})

        Returns:
            Dict mapping scope to list of results
        """
        if scopes is None:
            scopes = ["global", "workspace", "intent"]

        if top_k_per_scope is None:
            top_k_per_scope = {"global": 3, "workspace": 8, "intent": 8}

        query_embedding = await self._generate_embedding(query)
        if not query_embedding:
            return {scope: [] for scope in scopes}

        results = {}

        for scope in scopes:
            filters = {"user_id": user_id, "scope": scope}

            if scope == "workspace" and workspace_id:
                filters["workspace_id"] = workspace_id
            elif scope == "intent" and intent_id:
                filters["intent_id"] = intent_id
                if workspace_id:
                    filters["workspace_id"] = workspace_id

            top_k = top_k_per_scope.get(scope, 5)

            scope_results = await self.vector_search(
                table="memory_embeddings",
                query_embedding=query_embedding,
                filters=filters,
                top_k=top_k * 2,  # Get more results for composite scoring
            )

            # Apply composite scoring
            scored_results = await self._calculate_composite_scores(
                scope_results, query_embedding
            )

            # Return top_k after scoring
            results[scope] = scored_results[:top_k]

        return results

    async def _calculate_composite_scores(
        self, results: List[Dict[str, Any]], query_embedding: List[float]
    ) -> List[Dict[str, Any]]:
        """
        Calculate composite scores using multiple factors

        Score = α * cosine_similarity + β * recency_score + γ * importance

        Args:
            results: List of search results
            query_embedding: Query embedding vector

        Returns:
            List of results sorted by composite score
        """
        from datetime import datetime, timezone
        import math

        # Weight factors (can be configured)
        alpha = 0.6  # cosine similarity weight
        beta = 0.2  # recency weight
        gamma = 0.2  # importance weight

        scored_results = []

        for result in results:
            # Cosine similarity (already calculated in vector_search)
            similarity = result.get("similarity", 0.0)

            # Recency score (based on last_used_at)
            recency_score = 0.5  # default
            if "last_used_at" in result and result["last_used_at"]:
                try:
                    if isinstance(result["last_used_at"], str):
                        last_used = datetime.fromisoformat(
                            result["last_used_at"].replace("Z", "+00:00")
                        )
                    else:
                        last_used = result["last_used_at"]

                    if last_used.tzinfo is None:
                        last_used = last_used.replace(tzinfo=timezone.utc)

                    now = datetime.now(timezone.utc)
                    days_ago = (now - last_used).days

                    # Exponential decay: more recent = higher score
                    # Score decays to 0.1 after 30 days
                    recency_score = max(0.1, math.exp(-days_ago / 30.0))
                except Exception as e:
                    logger.debug(f"Failed to calculate recency score: {e}")

            # Importance score
            importance = result.get("importance", 0.5)
            if importance is None:
                importance = 0.5

            # Composite score
            composite_score = (
                alpha * similarity + beta * recency_score + gamma * importance
            )

            result["composite_score"] = composite_score
            result["recency_score"] = recency_score
            scored_results.append(result)

        # Sort by composite score (descending)
        scored_results.sort(key=lambda x: x["composite_score"], reverse=True)

        return scored_results

    async def update_last_used_at(
        self, record_ids: List[str], table: str = "memory_embeddings"
    ):
        """
        Update last_used_at timestamp for records

        Args:
            record_ids: List of record IDs to update
            table: Table name
        """
        await update_last_used_at_records(
            get_connection=self._get_connection,
            record_ids=record_ids,
            table=table,
        )

    async def save_to_external_docs(self, doc: Dict[str, Any]) -> bool:
        """
        Save document to external_docs table for RAG

        Args:
            doc: Document dictionary with:
                - user_id: User identifier
                - source_app: Source application (e.g., 'content-vault', 'wordpress', 'local_folder')
                - title: Document title (used as source_id for local_folder)
                - content: Document content
                - embedding: Embedding vector
                - metadata: Optional metadata dictionary

        Returns:
            True if successful, False otherwise
        """
        del doc
        raise ValueError(
            "direct_external_docs_write_retired_use_projection_facade"
        )
