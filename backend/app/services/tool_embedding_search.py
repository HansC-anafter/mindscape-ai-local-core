"""Search helpers for ToolEmbeddingService."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, List, Optional, Tuple

from backend.app.services.tool_embedding_service_core import (
    RAG_ERROR,
    RAG_HIT,
    RAG_MISS,
    ToolMatch,
    filter_mapping_rows_by_score,
    fuse_ranked_tool_matches,
    tuple_row_to_tool_match,
    vector_to_pg_literal,
)

logger = logging.getLogger(__name__)


async def search(
    service: Any,
    query: str,
    top_k: int = 15,
    min_score: float = 0.3,
) -> Tuple[List[ToolMatch], str]:
    """Search tool embeddings by cosine similarity."""
    query_embedding, model_name = await service._generate_embedding(query)
    if query_embedding is None or model_name is None:
        return [], RAG_ERROR

    embedding_str = vector_to_pg_literal(query_embedding)

    try:
        conn = service._get_connection()
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

    matches = filter_mapping_rows_by_score(rows, min_score=min_score)

    if matches:
        logger.info(
            f"Tool RAG: {len(matches)} matches for query "
            f"(top: {matches[0].tool_id} @ {matches[0].similarity:.3f})"
        )
        return matches, RAG_HIT

    logger.info("Tool RAG: 0 matches above threshold")
    return [], RAG_MISS


async def get_indexed_models(service: Any) -> List[str]:
    """Return all distinct embedding_model values that have rows."""
    try:
        conn = service._get_connection()
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


async def search_single_model(
    service: Any,
    query_embedding: List[float],
    model_name: str,
    top_k: int,
    min_score: float = 0.0,
) -> List[ToolMatch]:
    """Vector search restricted to one embedding_model."""
    embedding_str = vector_to_pg_literal(query_embedding)
    try:
        conn = service._get_connection()
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

    return filter_mapping_rows_by_score(rows, min_score=min_score)


async def search_bm25(
    service: Any,
    query: str,
    top_k: int = 15,
) -> List[ToolMatch]:
    """BM25 lexical search using PostgreSQL tsvector."""
    try:
        conn = service._get_connection()
        try:
            with conn.cursor() as cur:
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
                return [tuple_row_to_tool_match(row) for row in rows]
        finally:
            conn.close()
    except Exception as exc:
        logger.debug("BM25 search failed (non-fatal): %s", exc)
        return []


async def search_rrf(
    service: Any,
    query: str,
    top_k: int = 15,
    min_score: float = 0.3,
    rrf_k: int = 60,
) -> Tuple[List[ToolMatch], str]:
    """Multi-model Reciprocal Rank Fusion search."""
    query_embedding, model_name = await service._generate_embedding(query)
    if query_embedding is None or model_name is None:
        return [], RAG_ERROR

    indexed_models = await service.get_indexed_models()

    if len(indexed_models) <= 1:
        return await service.search(query, top_k=top_k, min_score=min_score)

    async def _embed_for_model(m: str) -> Tuple[str, Optional[List[float]]]:
        if m == model_name:
            return m, query_embedding
        emb, _ = await service._generate_embedding_for_model(query, m)
        return m, emb

    embed_tasks = [_embed_for_model(m) for m in indexed_models]
    embed_results = await asyncio.gather(*embed_tasks)

    search_tasks = []
    search_model_names = []
    for m, emb in embed_results:
        if emb is not None:
            search_tasks.append(service._search_single_model(emb, m, top_k * 2))
            search_model_names.append(m)

    if not search_tasks:
        return [], RAG_ERROR

    per_model_results: List[List[ToolMatch]] = list(
        await asyncio.gather(*search_tasks)
    )

    bm25_results: List[ToolMatch] = []
    try:
        bm25_results = await service.search_bm25(query, top_k=top_k * 2)
    except Exception as exc:
        logger.debug("BM25 path skipped in RRF: %s", exc)

    matches = fuse_ranked_tool_matches(
        per_model_results=per_model_results,
        bm25_results=bm25_results,
        top_k=top_k,
        min_score=min_score,
        rrf_k=rrf_k,
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

    logger.info("Tool RRF: 0 matches above threshold")
    return [], RAG_MISS


async def search_by_affordance(
    service: Any,
    consumes_types: List[str],
) -> List[ToolMatch]:
    """Search for playbooks that consume any of the specified asset types."""
    if not consumes_types:
        return []

    try:
        conn = service._get_connection()
        try:
            with conn.cursor() as cur:
                query_parts = []
                params = []
                for t in consumes_types:
                    query_parts.append("affordance->'consumes' @> %s::jsonb")
                    params.append(json.dumps([t]))

                where_clause = " OR ".join(query_parts)

                cur.execute(
                    f"""
                    SELECT DISTINCT tool_id, display_name, description, category, capability_code
                    FROM tool_embeddings
                    WHERE category = 'playbook'
                      AND ({where_clause})
                    """,
                    tuple(params),
                )
                rows = cur.fetchall()
                matches = [
                    tuple_row_to_tool_match(row, similarity=1.0) for row in rows
                ]
                logger.info(
                    "Structured search found %d playbooks for consumes_types=%s",
                    len(matches),
                    consumes_types,
                )
                return matches
        finally:
            conn.close()
    except Exception as exc:
        logger.error("Failed to search_by_affordance: %s", exc)
        return []
