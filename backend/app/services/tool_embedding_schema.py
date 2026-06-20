"""Schema and status helpers for ToolEmbeddingService."""

from __future__ import annotations

import logging
from typing import Any, Dict

from backend.app.services.tool_embedding_service_core import CREATE_TABLE_SQL

logger = logging.getLogger(__name__)


async def ensure_table(service: Any) -> None:
    """Create the tool_embeddings table and lightweight migrations."""
    try:
        conn = service._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(CREATE_TABLE_SQL)
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
                cur.execute(
                    """
                    ALTER TABLE tool_embeddings ADD COLUMN IF NOT EXISTS affordance JSONB DEFAULT '{}';
                    """
                )
            conn.commit()
            logger.info("tool_embeddings table ensured (with BM25 tsvector)")
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Failed to create tool_embeddings table: {e}")
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
