import asyncio
import json
import uuid
from typing import Any, Dict, List

from psycopg2.extras import Json

from backend.app.models.embedding_migration import (
    EmbeddingMigration,
    EmbeddingMigrationItem,
    MigrationStrategy,
)


def normalize_metadata(value: Any) -> Dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            value = {}

    return value if isinstance(value, dict) else {}


def build_migrated_metadata(
    metadata: Dict[str, Any],
    migration: EmbeddingMigration,
    new_embedding: List[float],
) -> Dict[str, Any]:
    metadata = metadata.copy()
    metadata["embedding_model"] = migration.target_model
    metadata["embedding_provider"] = migration.target_provider
    metadata["embedding_dimension"] = len(new_embedding)
    metadata["migrated_at"] = migration_timestamp()
    metadata["migrated_from"] = migration.source_model
    return metadata


def migration_timestamp() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


async def apply_migration_strategy(
    get_connection,
    store,
    migration: EmbeddingMigration,
    embedding_record: Dict[str, Any],
    new_embedding: List[float],
    migration_item: EmbeddingMigrationItem,
) -> None:
    def _apply_sync():
        conn = get_connection()
        cursor = None
        try:
            cursor = conn.cursor()

            if migration.strategy == MigrationStrategy.REPLACE:
                _apply_replace(
                    cursor,
                    store,
                    migration,
                    embedding_record,
                    new_embedding,
                    migration_item,
                )
            elif migration.strategy == MigrationStrategy.PRESERVE:
                _apply_preserve(
                    cursor,
                    store,
                    migration,
                    embedding_record,
                    new_embedding,
                    migration_item,
                )
            elif migration.strategy == MigrationStrategy.DEPRECATE:
                _apply_deprecate(
                    cursor,
                    store,
                    migration,
                    embedding_record,
                    new_embedding,
                    migration_item,
                )

            conn.commit()
        finally:
            try:
                if cursor is not None:
                    cursor.close()
            finally:
                conn.close()

    await asyncio.to_thread(_apply_sync)


def _apply_replace(
    cursor,
    store,
    migration: EmbeddingMigration,
    embedding_record: Dict[str, Any],
    new_embedding: List[float],
    migration_item: EmbeddingMigrationItem,
) -> None:
    metadata = build_migrated_metadata(
        normalize_metadata(embedding_record.get("metadata", {})),
        migration,
        new_embedding,
    )

    cursor.execute(
        """
        UPDATE mindscape_personal
        SET embedding = %s::vector,
            metadata = %s,
            updated_at = NOW()
        WHERE id = %s
    """,
        (new_embedding, Json(metadata), embedding_record["id"]),
    )

    migration_item.target_embedding_id = str(embedding_record["id"])
    store.update_migration_item(migration_item)


def _apply_preserve(
    cursor,
    store,
    migration: EmbeddingMigration,
    embedding_record: Dict[str, Any],
    new_embedding: List[float],
    migration_item: EmbeddingMigrationItem,
) -> None:
    new_id = str(uuid.uuid4())
    metadata = build_migrated_metadata(
        normalize_metadata(embedding_record.get("metadata", {})),
        migration,
        new_embedding,
    )
    metadata["original_id"] = str(embedding_record["id"])

    _insert_migrated_embedding(cursor, embedding_record, metadata, new_embedding, new_id)
    migration_item.target_embedding_id = new_id
    store.update_migration_item(migration_item)


def _apply_deprecate(
    cursor,
    store,
    migration: EmbeddingMigration,
    embedding_record: Dict[str, Any],
    new_embedding: List[float],
    migration_item: EmbeddingMigrationItem,
) -> None:
    old_metadata = normalize_metadata(embedding_record.get("metadata", {}))
    old_metadata["deprecated"] = True
    old_metadata["deprecated_at"] = migration_timestamp()
    old_metadata["deprecated_by"] = str(migration.id)

    cursor.execute(
        """
        UPDATE mindscape_personal
        SET metadata = %s,
            updated_at = NOW()
        WHERE id = %s
    """,
        (Json(old_metadata), embedding_record["id"]),
    )

    new_id = str(uuid.uuid4())
    new_metadata = build_migrated_metadata(old_metadata, migration, new_embedding)
    new_metadata.pop("deprecated", None)
    new_metadata.pop("deprecated_at", None)
    new_metadata.pop("deprecated_by", None)

    _insert_migrated_embedding(
        cursor,
        embedding_record,
        new_metadata,
        new_embedding,
        new_id,
    )
    migration_item.target_embedding_id = new_id
    store.update_migration_item(migration_item)


def _insert_migrated_embedding(
    cursor,
    embedding_record: Dict[str, Any],
    metadata: Dict[str, Any],
    new_embedding: List[float],
    new_id: str,
) -> None:
    cursor.execute(
        """
        INSERT INTO mindscape_personal
        (id, user_id, source_type, content, metadata, confidence, weight,
         embedding, scope, workspace_id, intent_id, importance, tags,
         created_at, updated_at, last_used_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s::vector, %s, %s, %s, %s, %s, NOW(), NOW(), NOW())
    """,
        (
            new_id,
            embedding_record.get("user_id"),
            embedding_record.get("source_type"),
            embedding_record.get("content"),
            Json(metadata),
            embedding_record.get("confidence", 1.0),
            embedding_record.get("weight", 1.0),
            new_embedding,
            embedding_record.get("scope"),
            embedding_record.get("workspace_id"),
            embedding_record.get("intent_id"),
            embedding_record.get("importance", 0.5),
            embedding_record.get("tags", []),
        ),
    )
