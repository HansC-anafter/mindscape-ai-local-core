"""
Tool Embedding Service
Indexes and searches tool embeddings in pgvector for RAG-based tool discovery.

Uses VectorSearchService for embedding generation (Ollama-first, OpenAI-fallback)
and stores embeddings in the vector DB (mindscape_vectors).
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

from app.database.config import get_vector_postgres_config

logger = logging.getLogger(__name__)


# Return type for search results
@dataclass
class ToolMatch:
    """A tool matched by embedding similarity search"""

    tool_id: str
    display_name: str
    description: str
    category: str
    capability_code: Optional[str]
    similarity: float


# Rag status constants
RAG_HIT = "hit"  # Search succeeded, found >= 1 match
RAG_MISS = "miss"  # Search succeeded, 0 matches above threshold
RAG_ERROR = "error"  # Embedding generation or DB query failed


_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS tool_embeddings (
    id              SERIAL PRIMARY KEY,
    tool_id         TEXT NOT NULL,
    display_name    TEXT,
    description     TEXT NOT NULL,
    category        TEXT,
    capability_code TEXT,
    embedding       vector,
    embedding_model TEXT NOT NULL,
    embedding_dim   INTEGER NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now(),
    UNIQUE (tool_id, embedding_model)
);
"""


class ToolEmbeddingService:
    """Index and search tool embeddings in pgvector (vector DB)"""

    def __init__(self, postgres_config: Optional[Dict[str, Any]] = None):
        self.postgres_config = postgres_config or get_vector_postgres_config()

    def _get_connection(self):
        """Get PostgreSQL connection to vector DB"""
        import psycopg2

        return psycopg2.connect(**self.postgres_config)

    def _get_current_model(self) -> str:
        """Get current embedding model name.

        Must match the actual model name recorded by _generate_embedding_with_model():
        priority is Ollama first, then OpenAI.
        """
        import os

        # Check Ollama availability first (matches embedding generation priority)
        ollama_host = os.getenv("OLLAMA_HOST", "http://ollama:11434")
        try:
            import requests

            resp = requests.get(f"{ollama_host}/api/tags", timeout=2)
            if resp.status_code == 200:
                return os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
        except Exception:
            pass

        # Fallback: OpenAI model from settings
        try:
            from backend.app.services.system_settings_store import SystemSettingsStore

            store = SystemSettingsStore()
            setting = store.get_setting("embedding_model")
            if setting and setting.value:
                return str(setting.value)
        except Exception:
            pass
        return "text-embedding-3-small"

    async def _generate_embedding(
        self, text: str
    ) -> Tuple[Optional[List[float]], Optional[str]]:
        """Generate embedding using VectorSearchService infrastructure.

        Returns:
            Tuple of (embedding_vector, model_name) or (None, None) on failure
        """
        try:
            from app.services.vector_search import VectorSearchService

            vs = VectorSearchService(postgres_config=self.postgres_config)
            embedding, model_name = await vs._generate_embedding_with_model(text)
            return embedding, model_name
        except Exception as e:
            logger.warning(f"Embedding generation failed: {e}")
            return None, None

    # ------------------------------------------------------------------ #
    #  Write path
    # ------------------------------------------------------------------ #

    async def ensure_table(self) -> None:
        """Create tool_embeddings table if not exists"""
        try:
            conn = self._get_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute(_CREATE_TABLE_SQL)
                conn.commit()
                logger.info("tool_embeddings table ensured")
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Failed to create tool_embeddings table: {e}")
            raise

    async def index_tool(
        self,
        tool_id: str,
        display_name: str,
        description: str,
        category: str,
        capability_code: Optional[str] = None,
    ) -> bool:
        """Embed and upsert a single tool.

        Returns True on success, False on failure.
        """
        embed_text = f"{display_name}: {description}"
        embedding, model_name = await self._generate_embedding(embed_text)
        if embedding is None or model_name is None:
            logger.warning(f"Skipping tool {tool_id}: embedding failed")
            return False

        embedding_dim = len(embedding)
        embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"

        try:
            conn = self._get_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO tool_embeddings
                            (tool_id, display_name, description, category,
                             capability_code, embedding, embedding_model,
                             embedding_dim, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s::vector, %s, %s, now())
                        ON CONFLICT (tool_id, embedding_model)
                        DO UPDATE SET
                            display_name = EXCLUDED.display_name,
                            description = EXCLUDED.description,
                            category = EXCLUDED.category,
                            capability_code = EXCLUDED.capability_code,
                            embedding = EXCLUDED.embedding,
                            embedding_dim = EXCLUDED.embedding_dim,
                            updated_at = now()
                        """,
                        (
                            tool_id,
                            display_name,
                            description,
                            category,
                            capability_code,
                            embedding_str,
                            model_name,
                            embedding_dim,
                        ),
                    )
                conn.commit()
                return True
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Failed to index tool {tool_id}: {e}")
            return False

    async def index_all_tools(self) -> int:
        """Index all tools from ToolListService. Idempotent (upsert).

        Returns number of successfully indexed tools.
        """
        try:
            from app.services.tool_list_service import ToolListService

            svc = ToolListService()
            all_tools = svc.get_all_tools()
        except Exception as e:
            logger.error(f"Failed to get tool list: {e}")
            return 0

        count = 0
        for tool in all_tools:
            # Derive capability_code from tool_id (format: "capability.tool_name")
            cap_code = None
            if tool.source == "capability" and "." in tool.tool_id:
                cap_code = tool.tool_id.split(".")[0]

            ok = await self.index_tool(
                tool_id=tool.tool_id,
                display_name=tool.name,
                description=tool.description,
                category=tool.category,
                capability_code=cap_code,
            )
            if ok:
                count += 1

        logger.info(f"Indexed {count}/{len(all_tools)} tools")
        return count

    async def ensure_indexed(self) -> int:
        """Startup hook: index all tools if table is empty or stale.

        Returns number of indexed tools (0 if already up to date).
        """
        current_model = self._get_current_model()

        try:
            conn = self._get_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT count(*) FROM tool_embeddings WHERE embedding_model = %s",
                        (current_model,),
                    )
                    row_count = cur.fetchone()[0]
            finally:
                conn.close()
        except Exception as e:
            logger.warning(f"Cannot check tool_embeddings count: {e}")
            row_count = 0

        # Get expected tool count
        try:
            from app.services.tool_list_service import ToolListService

            expected = len(ToolListService().get_all_tools())
        except Exception:
            expected = 0

        if row_count >= expected and expected > 0:
            logger.info(
                f"Tool embeddings up to date: {row_count} rows for model {current_model}"
            )
            return 0

        logger.info(f"Tool embeddings stale ({row_count}/{expected}), re-indexing...")
        return await self.index_all_tools()

    async def remove_tool(self, tool_id: str) -> bool:
        """Remove a tool's embeddings (all models).

        Returns True on success.
        """
        try:
            conn = self._get_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM tool_embeddings WHERE tool_id = %s",
                        (tool_id,),
                    )
                    deleted = cur.rowcount
                conn.commit()
                logger.info(f"Removed {deleted} embedding(s) for tool {tool_id}")
                return True
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Failed to remove tool {tool_id}: {e}")
            return False

    async def remove_tools_by_capability(self, capability_code: str) -> int:
        """Remove all tool embeddings for a capability pack.

        Returns number of deleted rows.
        """
        try:
            conn = self._get_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM tool_embeddings WHERE capability_code = %s",
                        (capability_code,),
                    )
                    deleted = cur.rowcount
                conn.commit()
                logger.info(
                    f"Removed {deleted} embedding(s) for capability {capability_code}"
                )
                return deleted
            finally:
                conn.close()
        except Exception as e:
            logger.error(
                f"Failed to remove embeddings for capability {capability_code}: {e}"
            )
            return 0

    # ------------------------------------------------------------------ #
    #  Read path
    # ------------------------------------------------------------------ #

    async def search(
        self,
        query: str,
        top_k: int = 15,
        min_score: float = 0.3,
    ) -> Tuple[List[ToolMatch], str]:
        """Search tool embeddings by cosine similarity.

        Returns:
            (matches, rag_status) where rag_status is one of:
            - "hit":   found >= 1 match above min_score
            - "miss":  search succeeded but 0 matches above min_score
            - "error": embedding generation or DB query failed
        """
        # Generate query embedding
        query_embedding, model_name = await self._generate_embedding(query)
        if query_embedding is None or model_name is None:
            return [], RAG_ERROR

        embedding_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

        try:
            conn = self._get_connection()
            try:
                from psycopg2.extras import RealDictCursor

                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        """
                        SELECT
                            tool_id,
                            display_name,
                            description,
                            category,
                            capability_code,
                            1 - (embedding <=> %s::vector) AS similarity
                        FROM tool_embeddings
                        WHERE embedding_model = %s
                        ORDER BY embedding <=> %s::vector
                        LIMIT %s
                        """,
                        (embedding_str, model_name, embedding_str, top_k),
                    )
                    rows = cur.fetchall()
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Tool embedding search failed: {e}")
            return [], RAG_ERROR

        # Filter by min_score
        matches = []
        for row in rows:
            sim = float(row["similarity"])
            if sim >= min_score:
                matches.append(
                    ToolMatch(
                        tool_id=row["tool_id"],
                        display_name=row["display_name"] or "",
                        description=row["description"],
                        category=row["category"] or "",
                        capability_code=row["capability_code"],
                        similarity=sim,
                    )
                )

        if matches:
            logger.info(
                f"Tool RAG: {len(matches)} matches for query "
                f"(top: {matches[0].tool_id} @ {matches[0].similarity:.3f})"
            )
            return matches, RAG_HIT
        else:
            logger.info("Tool RAG: 0 matches above threshold")
            return [], RAG_MISS

    # ------------------------------------------------------------------ #
    #  Migration
    # ------------------------------------------------------------------ #

    async def reindex_all(self) -> int:
        """Re-embed all tools with current model. Drops old model rows.

        Returns number of indexed tools.
        """
        current_model = self._get_current_model()

        # Delete all rows for current model (will be re-created)
        try:
            conn = self._get_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM tool_embeddings WHERE embedding_model = %s",
                        (current_model,),
                    )
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Failed to clear embeddings for reindex: {e}")
            return 0

        return await self.index_all_tools()
