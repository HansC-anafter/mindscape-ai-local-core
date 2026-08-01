"""
Vector database query and write helpers.
"""

from typing import Any, Callable, Dict, List, Optional
import logging

from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)

ConnectionFactory = Callable[[], Any]


async def search_vectors(
    get_connection: ConnectionFactory,
    table: str,
    query_embedding: List[float],
    filters: Optional[Dict[str, Any]] = None,
    top_k: int = 5,
    require_model_match: bool = True,
) -> List[Dict[str, Any]]:
    """
    Run the generic pgvector similarity query.

    Args:
        get_connection: Existing VectorSearchService connection factory
        table: Table name
        query_embedding: Query vector
        filters: Additional equality filters
        top_k: Number of records to return
        require_model_match: Whether to filter by configured embedding model

    Returns:
        Matching records with similarity scores.
    """
    if table == "external_docs":
        raise ValueError(
            "external_docs_requires_authorization_aware_retrieval"
        )
    conn = get_connection()
    cursor = None
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        current_model_name = None
        if require_model_match and table in (
            "mindscape_personal",
            "memory_embeddings",
        ):
            from backend.app.services.system_settings_store import (
                SystemSettingsStore,
            )

            settings_store = SystemSettingsStore()
            embedding_setting = settings_store.get_setting("embedding_model")
            if embedding_setting:
                current_model_name = str(embedding_setting.value)

        where_clauses = []
        params = []

        if filters:
            for key, value in filters.items():
                where_clauses.append(f"{key} = %s")
                params.append(value)

        if (
            require_model_match
            and current_model_name
            and table in ("mindscape_personal", "memory_embeddings")
        ):
            where_clauses.append("metadata->>'embedding_model' = %s")
            params.append(current_model_name)

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        query = f"""
            SELECT
                *,
                1 - (embedding <=> %s::vector) as similarity
            FROM {table}
            {where_sql}
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """

        params = [str(query_embedding)] + params + [str(query_embedding), top_k]
        cursor.execute(query, params)

        results = cursor.fetchall()
        return [dict(row) for row in results]

    finally:
        try:
            if cursor is not None:
                cursor.close()
        finally:
            conn.close()


async def search_external_docs_records(
    get_connection: ConnectionFactory,
    query_embedding: List[float],
    model_name: Optional[str],
    source_apps: Optional[List[str]] = None,
    user_id: str = "default_user",
    top_k: int = 10,
    require_model_match: bool = True,
) -> List[Dict[str, Any]]:
    del (
        get_connection,
        query_embedding,
        model_name,
        source_apps,
        user_id,
        top_k,
        require_model_match,
    )
    raise ValueError(
        "external_docs_requires_authorization_aware_retrieval"
    )


async def update_last_used_at_records(
    get_connection: ConnectionFactory,
    record_ids: List[str],
    table: str = "memory_embeddings",
) -> None:
    """
    Update last_used_at for matching records.

    Args:
        get_connection: Existing VectorSearchService connection factory
        record_ids: List of record IDs to update
        table: Table name
    """
    if not record_ids:
        return

    conn = get_connection()
    cursor = None
    try:
        cursor = conn.cursor()

        placeholders = ",".join(["%s"] * len(record_ids))
        query = f"""
            UPDATE {table}
            SET last_used_at = NOW()
            WHERE id::text = ANY(ARRAY[{placeholders}])
        """

        cursor.execute(query, record_ids)
        conn.commit()

        logger.debug("Updated last_used_at for %d records in %s", len(record_ids), table)

    finally:
        try:
            if cursor is not None:
                cursor.close()
        finally:
            conn.close()


async def save_external_doc(
    get_connection: ConnectionFactory,
    doc: Dict[str, Any],
) -> bool:
    del get_connection, doc
    raise ValueError(
        "direct_external_docs_write_retired_use_projection_facade"
    )
