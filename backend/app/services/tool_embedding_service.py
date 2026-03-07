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
        """Get current embedding model name, matching what _generate_embedding() will use.

        Priority: frontend ollama_embed_model setting → OLLAMA_EMBED_MODEL env var
                  → bge-m3 (if Ollama has it) → nomic-embed-text → OpenAI model.
        """
        import os
        import requests

        # 1. Frontend-managed setting (takes absolute priority)
        try:
            from backend.app.services.system_settings_store import SystemSettingsStore

            store = SystemSettingsStore()
            fe_setting = store.get_setting("ollama_embed_model")
            if fe_setting and fe_setting.value and str(fe_setting.value).strip():
                return str(fe_setting.value).strip()
        except Exception:
            pass

        # 2. Env var override
        preferred = os.getenv("OLLAMA_EMBED_MODEL", "").strip()

        # 3. Probe Ollama (same resolution order as VectorSearchService._get_ollama_url)
        ollama_candidates = []
        env_host = os.getenv("OLLAMA_HOST", "").strip()
        if env_host:
            ollama_candidates.append(env_host)
        ollama_candidates += [
            "http://host.docker.internal:11434",
            "http://ollama:11434",
        ]

        for base_url in ollama_candidates:
            try:
                resp = requests.get(f"{base_url}/api/tags", timeout=2)
                if resp.status_code == 200:
                    if preferred:
                        return preferred
                    # Auto-select: bge-m3 preferred
                    model_names = [
                        m["name"].split(":")[0] for m in resp.json().get("models", [])
                    ]
                    if "bge-m3" in model_names:
                        return "bge-m3"
                    if "nomic-embed-text" in model_names:
                        return "nomic-embed-text"
                    break  # Ollama reachable but no known embed model
            except Exception:
                continue

        # 4. Fallback: OpenAI model from settings
        try:
            from backend.app.services.system_settings_store import SystemSettingsStore

            store = SystemSettingsStore()
            setting = store.get_setting("embedding_model")
            if setting and setting.value:
                return str(setting.value)
        except Exception:
            pass
        return "text-embedding-3-small"

    # Nomic v1.5 models requiring task prefix
    _NOMIC_MODELS = {"nomic-embed-text", "nomic-embed-text-v1.5"}

    async def _generate_embedding(
        self, text: str, *, is_query: bool = True
    ) -> Tuple[Optional[List[float]], Optional[str]]:
        """Generate embedding using VectorSearchService infrastructure.

        Args:
            text: Text to embed.
            is_query: True for search queries, False for indexing.

        Returns:
            Tuple of (embedding_vector, model_name) or (None, None) on failure
        """
        try:
            from app.services.vector_search import VectorSearchService

            vs = VectorSearchService(postgres_config=self.postgres_config)
            embedding, model_name = await vs._generate_embedding_with_model(
                text, is_query=is_query
            )
            return embedding, model_name
        except Exception as e:
            logger.warning(f"Embedding generation failed: {e}")
            return None, None

    async def _generate_embedding_for_model(
        self, text: str, model_name: str, *, is_query: bool = True
    ) -> Tuple[Optional[List[float]], Optional[str]]:
        """Generate embedding using a specific Ollama model.

        Used by RRF multi-model indexing and search to obtain embeddings in
        different vector spaces without altering the primary model preference.

        Args:
            text: Text to embed.
            model_name: Ollama model name.
            is_query: True for search, False for indexing (controls nomic prefix).

        Returns:
            Tuple of (embedding_vector, model_name) or (None, None) on failure.
        """
        import os

        # Nomic task prefix (independent httpx path, same logic as VectorSearchService)
        prompt_text = text
        base_model = model_name.split(":")[0].lower()
        if base_model in self._NOMIC_MODELS:
            prefix = "search_query" if is_query else "search_document"
            prompt_text = f"{prefix}: {text}"

        try:
            import httpx

            ollama_url = (
                os.getenv("OLLAMA_HOST", "").strip()
                or "http://host.docker.internal:11434"
            )
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{ollama_url}/api/embeddings",
                    json={"model": model_name, "prompt": prompt_text},
                )
                if resp.status_code == 200:
                    emb = resp.json().get("embedding")
                    if emb:
                        return emb, model_name
                # Fallback: try ollama service name
                if ollama_url == "http://host.docker.internal:11434":
                    resp2 = await client.post(
                        "http://ollama:11434/api/embeddings",
                        json={"model": model_name, "prompt": prompt_text},
                    )
                    if resp2.status_code == 200:
                        emb2 = resp2.json().get("embedding")
                        if emb2:
                            return emb2, model_name
        except Exception as e:
            logger.debug(f"_generate_embedding_for_model({model_name}) failed: {e}")
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
                    # BM25 migration: add tsvector column + GIN index for lexical search
                    cur.execute(
                        """
                        DO $$
                        BEGIN
                            IF NOT EXISTS (
                                SELECT 1 FROM information_schema.columns
                                WHERE table_name = 'tool_embeddings'
                                  AND column_name = 'text_vector'
                            ) THEN
                                ALTER TABLE tool_embeddings
                                  ADD COLUMN text_vector tsvector
                                    GENERATED ALWAYS AS (
                                      to_tsvector('simple',
                                        coalesce(display_name, '') || ' ' || description
                                      )
                                    ) STORED;
                                CREATE INDEX IF NOT EXISTS idx_tool_embeddings_text
                                  ON tool_embeddings USING gin(text_vector);
                            END IF;
                        END $$;
                    """
                    )
                conn.commit()
                logger.info("tool_embeddings table ensured (with BM25 tsvector)")
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
        embedding, model_name = await self._generate_embedding(
            embed_text, is_query=False
        )
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
        """Startup hook: index all tools for every available embed model.

        On cold start this discovers all Ollama embed models, checks whether
        each one has a complete set of tool rows, and re-indexes any that are
        stale or missing.  Single-model environments behave identically to
        before (index_all_tools fallback).

        Returns total number of newly indexed (tool, model) rows; 0 if already
        up to date.
        """
        import os
        import requests as req

        # --- Discover available Ollama embed models ---
        EMBED_KEYWORDS = ("embed", "bge", "nomic", "e5", "gte")
        ollama_candidates = []
        env_host = os.getenv("OLLAMA_HOST", "").strip()
        if env_host:
            ollama_candidates.append(env_host)
        ollama_candidates += [
            "http://host.docker.internal:11434",
            "http://ollama:11434",
        ]

        ollama_models: List[str] = []
        for base_url in ollama_candidates:
            try:
                resp = req.get(f"{base_url}/api/tags", timeout=2)
                if resp.status_code == 200:
                    for m in resp.json().get("models", []):
                        name = m["name"].split(":")[0]
                        if any(kw in name.lower() for kw in EMBED_KEYWORDS):
                            if name not in ollama_models:
                                ollama_models.append(name)
                    break
            except Exception:
                continue

        # Fallback: at least use the primary model
        primary = self._get_current_model()
        if not ollama_models:
            ollama_models = [primary]

        # --- Get expected tool count ---
        try:
            from app.services.tool_list_service import ToolListService

            expected = len(ToolListService().get_all_tools())
        except Exception:
            expected = 0

        if expected == 0:
            logger.warning("ensure_indexed: no tools found, skipping")
            return 0

        # --- Check which models need indexing ---
        stale_models: List[str] = []
        try:
            conn = self._get_connection()
            try:
                with conn.cursor() as cur:
                    for model in ollama_models:
                        cur.execute(
                            "SELECT count(*) FROM tool_embeddings WHERE embedding_model = %s",
                            (model,),
                        )
                        row_count = cur.fetchone()[0]
                        if row_count < expected:
                            logger.info(
                                f"ensure_indexed: model {model} stale "
                                f"({row_count}/{expected}), will re-index"
                            )
                            stale_models.append(model)
                        else:
                            logger.info(
                                f"ensure_indexed: model {model} up to date "
                                f"({row_count} rows)"
                            )
            finally:
                conn.close()
        except Exception as e:
            logger.warning(
                f"ensure_indexed: DB check failed ({e}), forcing full re-index"
            )
            stale_models = ollama_models

        if not stale_models:
            return 0

        # --- Index only stale models ---
        total = 0
        for model in stale_models:
            count = await self._index_all_tools_for_model(model)
            logger.info(f"ensure_indexed: [{model}] indexed {count} tools")
            total += count

        # If we had stale models and expected tools, but indexed 0, it means
        # the Ollama embedding path completely failed (e.g., Ollama is unavailable).
        # We raise here so callers can gracefully fallback to base index_all_tools().
        if stale_models and expected > 0 and total == 0:
            raise RuntimeError("Ollama multi-model indexing failed completely")

        return total

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

    async def get_indexed_models(self) -> List[str]:
        """Return all distinct embedding_model values that have rows in tool_embeddings."""
        try:
            conn = self._get_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT DISTINCT embedding_model FROM tool_embeddings ORDER BY embedding_model"
                    )
                    return [row[0] for row in cur.fetchall()]
            finally:
                conn.close()
        except Exception as e:
            logger.warning(f"get_indexed_models failed: {e}")
            return []

    async def _search_single_model(
        self,
        query_embedding: List[float],
        model_name: str,
        top_k: int,
        min_score: float = 0.0,
    ) -> List[ToolMatch]:
        """Vector search restricted to one embedding_model. Returns raw results (no threshold filter)."""
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
            logger.warning(f"_search_single_model({model_name}) failed: {e}")
            return []

        return [
            ToolMatch(
                tool_id=row["tool_id"],
                display_name=row["display_name"] or "",
                description=row["description"],
                category=row["category"] or "",
                capability_code=row["capability_code"],
                similarity=float(row["similarity"]),
            )
            for row in rows
            if float(row["similarity"]) >= min_score
        ]

    async def search_bm25(
        self,
        query: str,
        top_k: int = 15,
    ) -> List[ToolMatch]:
        """BM25 lexical search using PostgreSQL tsvector.

        Returns ranked ToolMatch list (no threshold filter — caller does fusion).
        Uses 'simple' config for brand names / abbreviations that vector search misses.
        """
        try:
            conn = self._get_connection()
            try:
                with conn.cursor() as cur:
                    # plainto_tsquery handles multi-word queries safely
                    cur.execute(
                        """
                        SELECT tool_id, display_name, description, category,
                               capability_code,
                               ts_rank(text_vector, plainto_tsquery('simple', %s)) AS rank
                        FROM tool_embeddings
                        WHERE text_vector @@ plainto_tsquery('simple', %s)
                        ORDER BY rank DESC
                        LIMIT %s
                        """,
                        (query, query, top_k),
                    )
                    rows = cur.fetchall()
                    return [
                        ToolMatch(
                            tool_id=row[0],
                            display_name=row[1] or row[0],
                            description=row[2],
                            category=row[3] or "",
                            capability_code=row[4],
                            similarity=float(row[5]),
                        )
                        for row in rows
                    ]
            finally:
                conn.close()
        except Exception as exc:
            logger.debug("BM25 search failed (non-fatal): %s", exc)
            return []

    async def search_rrf(
        self,
        query: str,
        top_k: int = 15,
        min_score: float = 0.3,
        rrf_k: int = 60,
    ) -> Tuple[List[ToolMatch], str]:
        """Multi-model Reciprocal Rank Fusion search.

        Queries every model that has indexed rows in tool_embeddings in parallel,
        fuses their ranked lists with RRF (score = Σ 1/(k + rank_i), k default 60),
        and returns the top-K tools sorted by fused score.

        Falls back to single-model search() when:
        - Only one model is indexed (no fusion benefit)
        - Embedding generation fails

        Returns:
            (matches, rag_status)  — same contract as search()
        """
        import asyncio

        # 1. Generate query embedding with the primary model
        query_embedding, model_name = await self._generate_embedding(query)
        if query_embedding is None or model_name is None:
            return [], RAG_ERROR

        # 2. Identify which models have indexed data
        indexed_models = await self.get_indexed_models()

        # If only one model (or none), fall back to single-model search
        if len(indexed_models) <= 1:
            return await self.search(query, top_k=top_k, min_score=min_score)

        # 3. For each indexed model, we need a compatible embedding
        #    - For the primary model we already have the embedding
        #    - For others we must re-embed (different model = different vector space)
        #    NOTE: We attempt per-model embedding via VectorSearchService if the model
        #    differs; on failure we skip that model gracefully.
        async def _embed_for_model(m: str) -> Tuple[str, Optional[List[float]]]:
            if m == model_name:
                return m, query_embedding
            emb, _ = await self._generate_embedding_for_model(query, m)
            return m, emb

        embed_tasks = [_embed_for_model(m) for m in indexed_models]
        embed_results = await asyncio.gather(*embed_tasks)

        # 4. Parallel per-model similarity search
        search_tasks = []
        search_model_names = []
        for m, emb in embed_results:
            if emb is not None:
                search_tasks.append(self._search_single_model(emb, m, top_k * 2))
                search_model_names.append(m)

        if not search_tasks:
            return [], RAG_ERROR

        per_model_results: List[List[ToolMatch]] = list(
            await asyncio.gather(*search_tasks)
        )

        # 4b. BM25 lexical search (third path — catches abbreviations/brand names)
        bm25_results: List[ToolMatch] = []
        try:
            bm25_results = await self.search_bm25(query, top_k=top_k * 2)
        except Exception as exc:
            logger.debug("BM25 path skipped in RRF: %s", exc)

        # 5. Reciprocal Rank Fusion (vector models + BM25)
        rrf_scores: dict[str, float] = {}
        tool_meta: dict[str, ToolMatch] = {}  # keeps last-seen metadata
        best_sim: dict[str, float] = {}  # track best single-model similarity

        for ranked_list in per_model_results:
            for rank, match in enumerate(ranked_list):
                tid = match.tool_id
                rrf_scores[tid] = rrf_scores.get(tid, 0.0) + 1.0 / (rrf_k + rank + 1)
                tool_meta[tid] = match
                best_sim[tid] = max(best_sim.get(tid, 0.0), match.similarity)

        # BM25 contributes to RRF on equal footing
        for rank, match in enumerate(bm25_results):
            tid = match.tool_id
            rrf_scores[tid] = rrf_scores.get(tid, 0.0) + 1.0 / (rrf_k + rank + 1)
            if tid not in tool_meta:
                tool_meta[tid] = match
                best_sim[tid] = 0.0  # BM25-only matches have no vector sim
            # BM25 match boosts confidence — don't apply min_score penalty
            best_sim[tid] = max(best_sim.get(tid, 0.0), min_score)

        # 6. Sort by RRF score and apply min_score filter on best single-model sim
        sorted_ids = sorted(rrf_scores, key=lambda t: rrf_scores[t], reverse=True)
        matches: List[ToolMatch] = []
        for tid in sorted_ids[:top_k]:
            if best_sim.get(tid, 0.0) >= min_score:
                meta = tool_meta[tid]
                matches.append(
                    ToolMatch(
                        tool_id=meta.tool_id,
                        display_name=meta.display_name,
                        description=meta.description,
                        category=meta.category,
                        capability_code=meta.capability_code,
                        similarity=rrf_scores[tid],  # RRF-fused score
                    )
                )

        n_paths = len(search_model_names) + (1 if bm25_results else 0)
        if matches:
            logger.info(
                "Tool RRF (%d paths, %d vector + %d bm25): %d matches (top: %s @ rrf=%.4f)",
                n_paths,
                len(search_model_names),
                len(bm25_results),
                len(matches),
                matches[0].tool_id,
                matches[0].similarity,
            )
            return matches, RAG_HIT
        else:
            logger.info("Tool RRF: 0 matches above threshold")
            return [], RAG_MISS

    # ------------------------------------------------------------------ #
    #  Multi-model index path
    # ------------------------------------------------------------------ #

    async def index_all_tools_multimodel(self) -> int:
        """Re-index all tools for every Ollama embed model currently available.

        Each (tool_id, model) pair is upserted independently (UNIQUE constraint).
        Returns the total number of (tool, model) rows successfully indexed.
        """
        import os
        import requests as req

        # Discover available Ollama embed models (same probe logic as _get_current_model)
        EMBED_MODEL_KEYWORDS = ("embed", "bge", "nomic", "e5", "gte")
        ollama_candidates = []
        env_host = os.getenv("OLLAMA_HOST", "").strip()
        if env_host:
            ollama_candidates.append(env_host)
        ollama_candidates += [
            "http://host.docker.internal:11434",
            "http://ollama:11434",
        ]

        embed_models: List[str] = []
        for base_url in ollama_candidates:
            try:
                resp = req.get(f"{base_url}/api/tags", timeout=2)
                if resp.status_code == 200:
                    for m in resp.json().get("models", []):
                        name = m["name"].split(":")[0]
                        if any(kw in name.lower() for kw in EMBED_MODEL_KEYWORDS):
                            if name not in embed_models:
                                embed_models.append(name)
                    break
            except Exception:
                continue

        if not embed_models:
            logger.info(
                "index_all_tools_multimodel: no Ollama embed models found, using single-model path"
            )
            return await self.index_all_tools()

        logger.info(f"index_all_tools_multimodel: indexing for models {embed_models}")

        total = 0
        for model in embed_models:
            # Temporarily override the effective model for this indexing run
            # by using a lightweight helper that forces the model in VectorSearchService
            count = await self._index_all_tools_for_model(model)
            logger.info(f"  [{model}] indexed {count} tools")
            total += count

        return total

    async def _index_all_tools_for_model(self, model_name: str) -> int:
        """Index all tools using a specific embedding model."""
        try:
            from app.services.tool_list_service import ToolListService

            all_tools = ToolListService().get_all_tools()
        except Exception as e:
            logger.error(f"Failed to get tool list: {e}")
            return 0

        count = 0
        for tool in all_tools:
            cap_code = None
            if tool.source == "capability" and "." in tool.tool_id:
                cap_code = tool.tool_id.split(".")[0]

            embed_text = f"{tool.name}: {tool.description}"
            emb, used_model = await self._generate_embedding_for_model(
                embed_text, model_name, is_query=False
            )
            if emb is None:
                logger.warning(f"  Embed failed for {tool.tool_id} ({model_name})")
                continue

            embedding_str = "[" + ",".join(str(v) for v in emb) + "]"
            embedding_dim = len(emb)
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
                                tool.tool_id,
                                tool.name,
                                tool.description,
                                tool.category,
                                cap_code,
                                embedding_str,
                                used_model,
                                embedding_dim,
                            ),
                        )
                    conn.commit()
                    count += 1
                finally:
                    conn.close()
            except Exception as e:
                logger.error(
                    f"  DB write failed for {tool.tool_id} ({model_name}): {e}"
                )

        return count

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
