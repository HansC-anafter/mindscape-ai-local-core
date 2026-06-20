"""
Vector database query and write helpers.
"""

from typing import Any, Callable, Dict, List, Optional
import json
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
    conn = get_connection()
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
    """
    Search external_docs with optional source and model filters.

    Args:
        get_connection: Existing VectorSearchService connection factory
        query_embedding: Query vector
        model_name: Embedding model used by the query vector
        source_apps: Optional source application filter
        user_id: User identifier
        top_k: Number of records to return
        require_model_match: Whether to filter by embedding model

    Returns:
        Matching external document records.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        where_clauses = ["user_id = %s"]
        params = [user_id]

        if source_apps:
            where_clauses.append("source_app = ANY(%s)")
            params.append(source_apps)

        if require_model_match and model_name:
            where_clauses.append("metadata->>'embedding_model' = %s")
            params.append(model_name)

        where_sql = f"WHERE {' AND '.join(where_clauses)}"

        query_sql = f"""
            SELECT
                *,
                1 - (embedding <=> %s::vector) as similarity
            FROM external_docs
            {where_sql}
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """

        params = [str(query_embedding)] + params + [str(query_embedding), top_k]
        cursor.execute(query_sql, params)

        results = cursor.fetchall()
        return [dict(row) for row in results]

    finally:
        conn.close()


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
        conn.close()


async def save_external_doc(
    get_connection: ConnectionFactory,
    doc: Dict[str, Any],
) -> bool:
    """
    Save or update a document in external_docs.

    Args:
        get_connection: Existing VectorSearchService connection factory
        doc: Document dictionary

    Returns:
        True when the write commits successfully.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()

        user_id = doc.get("user_id", "default_user")
        source_app = doc.get("source_app", "unknown")
        title = doc.get("title", "Untitled")
        content = doc.get("content", "")
        embedding = doc.get("embedding")
        metadata = doc.get("metadata", {})
        source_id = doc.get("source_id", title)

        if not embedding:
            logger.warning("No embedding provided for document")
            return False

        query = """
            INSERT INTO external_docs (
                user_id,
                source_app,
                source_id,
                title,
                content,
                embedding,
                metadata,
                created_at,
                updated_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s::vector, %s, NOW(), NOW()
            )
            ON CONFLICT (user_id, source_app, source_id)
            DO UPDATE SET
                title = EXCLUDED.title,
                content = EXCLUDED.content,
                embedding = EXCLUDED.embedding,
                metadata = EXCLUDED.metadata,
                updated_at = NOW()
            RETURNING id
        """

        cursor.execute(
            query,
            (
                user_id,
                source_app,
                source_id,
                title,
                content,
                str(embedding),
                json.dumps(metadata),
            ),
        )

        result = cursor.fetchone()
        conn.commit()

        logger.debug(
            "Saved document to external_docs: %s (id: %s)",
            title,
            result[0] if result else "unknown",
        )
        return True

    except Exception as e:
        logger.error("Failed to save document to external_docs: %s", e)
        conn.rollback()
        return False
    finally:
        conn.close()
