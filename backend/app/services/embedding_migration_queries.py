import asyncio
from typing import Any, Dict, List, Optional, Tuple

from psycopg2.extras import RealDictCursor

from backend.app.models.embedding_migration import EmbeddingMigration


def build_embedding_filter(
    source_model: str,
    source_provider: str,
    workspace_id: Optional[str] = None,
    intent_id: Optional[str] = None,
    scope: Optional[str] = None,
) -> Tuple[str, List[str]]:
    where_clauses = [
        "metadata->>'embedding_model' = %s",
        "metadata->>'embedding_provider' = %s",
    ]
    params = [source_model, source_provider]

    if workspace_id:
        where_clauses.append("workspace_id = %s")
        params.append(workspace_id)

    if intent_id:
        where_clauses.append("intent_id = %s")
        params.append(intent_id)

    if scope:
        where_clauses.append("scope = %s")
        params.append(scope)

    return "WHERE " + " AND ".join(where_clauses), params


async def count_embeddings_to_migrate(
    get_connection,
    source_model: str,
    source_provider: str,
    workspace_id: Optional[str] = None,
    intent_id: Optional[str] = None,
    scope: Optional[str] = None,
) -> int:
    def _count_sync():
        conn = get_connection()
        cursor = None
        try:
            cursor = conn.cursor()
            where_sql, params = build_embedding_filter(
                source_model=source_model,
                source_provider=source_provider,
                workspace_id=workspace_id,
                intent_id=intent_id,
                scope=scope,
            )
            cursor.execute(
                f"""
                    SELECT COUNT(*) as count
                    FROM mindscape_personal
                    {where_sql}
                """,
                params,
            )
            result = cursor.fetchone()
            return result[0] if result else 0
        finally:
            try:
                if cursor is not None:
                    cursor.close()
            finally:
                conn.close()

    return await asyncio.to_thread(_count_sync)


async def fetch_embeddings_to_migrate(
    get_connection,
    migration: EmbeddingMigration,
) -> List[Dict[str, Any]]:
    def _fetch_sync():
        conn = get_connection()
        cursor = None
        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            where_sql, params = build_embedding_filter(
                source_model=migration.source_model,
                source_provider=migration.source_provider,
                workspace_id=migration.workspace_id,
                intent_id=migration.intent_id,
                scope=migration.scope,
            )
            cursor.execute(
                f"""
                    SELECT *
                    FROM mindscape_personal
                    {where_sql}
                    ORDER BY created_at
                """,
                params,
            )
            results = cursor.fetchall()
            return [dict(row) for row in results]
        finally:
            try:
                if cursor is not None:
                    cursor.close()
            finally:
                conn.close()

    return await asyncio.to_thread(_fetch_sync)
