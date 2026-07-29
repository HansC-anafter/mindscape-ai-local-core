"""Schema and status helpers for ToolEmbeddingService."""

from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

_REQUIRED_COLUMNS = {
    "id",
    "tool_id",
    "display_name",
    "description",
    "category",
    "capability_code",
    "embedding",
    "embedding_model",
    "embedding_dim",
    "affordance",
    "created_at",
    "updated_at",
    "text_vector",
}


async def ensure_table(service: Any) -> None:
    """Verify the migration-owned Tool RAG schema without runtime DDL."""
    try:
        conn = service._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'tool_embeddings'
                    """
                )
                observed = {str(row[0]) for row in cur.fetchall()}
                missing = sorted(_REQUIRED_COLUMNS - observed)
                if missing:
                    raise RuntimeError(
                        "tool_embeddings_schema_not_migrated:"
                        + ",".join(missing)
                    )
                cur.execute(
                    """
                    SELECT to_regclass(
                        'public.idx_tool_embeddings_text'
                    ) IS NOT NULL
                    """
                )
                if cur.fetchone() != (True,):
                    raise RuntimeError(
                        "tool_embeddings_text_index_not_migrated"
                    )
            logger.info("tool_embeddings migration-owned schema verified")
        finally:
            conn.close()
    except Exception as e:
        logger.error("Failed to verify tool_embeddings schema: %s", e)
        raise


async def remove_tool(service: Any, tool_id: str) -> bool:
    """Remove a tool's embeddings across all indexed models."""
    try:
        conn = service._get_connection()
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


async def remove_tools_by_capability(service: Any, capability_code: str) -> int:
    """Remove all tool embeddings for a capability pack."""
    try:
        conn = service._get_connection()
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


async def has_existing_index(service: Any, *, min_rows: int = 1) -> bool:
    """Return whether the embedding table already has a usable corpus."""
    try:
        conn = service._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM tool_embeddings LIMIT %s",
                    (max(1, min_rows),),
                )
                rows = cur.fetchall()
        finally:
            conn.close()
    except Exception as e:
        logger.warning("Failed to read tool embedding row count: %s", e)
        return False

    return len(rows) >= min_rows


async def get_capability_embedding_status(
    service: Any, capability_code: str
) -> Dict[str, Any]:
    """Return current embedding coverage for one capability code."""
    try:
        conn = service._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT count(*) AS row_count, max(updated_at) AS latest_updated_at
                    FROM tool_embeddings
                    WHERE capability_code = %s
                    """,
                    (capability_code,),
                )
                row = cur.fetchone()
        finally:
            conn.close()
    except Exception as e:
        logger.warning(
            "Failed to read embedding status for capability %s: %s",
            capability_code,
            e,
        )
        return {"row_count": 0, "latest_updated_at": None}

    return {
        "row_count": int(row[0] or 0),
        "latest_updated_at": row[1],
    }
