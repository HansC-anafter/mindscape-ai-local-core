"""
Embedding Migration Store

Manages embedding migration tasks storage in PostgreSQL database.
"""

import json
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
from uuid import UUID
import logging

from sqlalchemy import text

from app.services.stores.postgres_base import PostgresStoreBase
from backend.app.models.embedding_migration import (
    EmbeddingMigration,
    EmbeddingMigrationItem,
    MigrationStatus,
    ItemStatus,
)

logger = logging.getLogger(__name__)


class EmbeddingMigrationStore(PostgresStoreBase):
    """Postgres-based embedding migration store"""

    def __init__(self, db_path: Optional[str] = None, db_role: str = "core"):
        super().__init__(db_role=db_role)
        self.db_path = db_path

    def create_migration(self, migration: EmbeddingMigration) -> EmbeddingMigration:
        """Create a new migration task"""
        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO embedding_migrations
                    (id, source_model, target_model, source_provider, target_provider,
                     user_id, workspace_id, intent_id, scope, strategy,
                     total_count, processed_count, failed_count, status,
                     started_at, completed_at, error_message, metadata,
                     created_at, updated_at)
                    VALUES
                    (:id, :source_model, :target_model, :source_provider, :target_provider,
                     :user_id, :workspace_id, :intent_id, :scope, :strategy,
                     :total_count, :processed_count, :failed_count, :status,
                     :started_at, :completed_at, :error_message, :metadata,
                     :created_at, :updated_at)
                """
                ),
                {
                    "id": str(migration.id),
                    "source_model": migration.source_model,
                    "target_model": migration.target_model,
                    "source_provider": migration.source_provider,
                    "target_provider": migration.target_provider,
                    "user_id": migration.user_id,
                    "workspace_id": migration.workspace_id,
                    "intent_id": migration.intent_id,
                    "scope": migration.scope,
                    "strategy": migration.strategy,
                    "total_count": migration.total_count,
                    "processed_count": migration.processed_count,
                    "failed_count": migration.failed_count,
                    "status": migration.status,
                    "started_at": migration.started_at,
                    "completed_at": migration.completed_at,
                    "error_message": migration.error_message,
                    "metadata": json.dumps(migration.metadata) if migration.metadata else None,
                    "created_at": migration.created_at,
                    "updated_at": migration.updated_at,
                },
            )
            return migration

    def get_migration(self, migration_id: UUID) -> Optional[EmbeddingMigration]:
        """Get migration task by ID"""
        with self.get_connection() as conn:
            row = conn.execute(
                text("SELECT * FROM embedding_migrations WHERE id = :id"),
                {"id": str(migration_id)},
            ).fetchone()
            if not row:
                return None
            return self._row_to_migration(row)

    def list_migrations(
        self,
        user_id: Optional[str] = None,
        status: Optional[MigrationStatus] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[EmbeddingMigration]:
        """List migration tasks"""
        with self.get_connection() as conn:
            query = "SELECT * FROM embedding_migrations WHERE 1=1"
            params: Dict[str, Any] = {"limit": limit, "offset": offset}

            if user_id:
                query += " AND user_id = :user_id"
                params["user_id"] = user_id

            if status:
                query += " AND status = :status"
                params["status"] = status.value if hasattr(status, "value") else status

            query += " ORDER BY created_at DESC LIMIT :limit OFFSET :offset"

            rows = conn.execute(text(query), params).fetchall()
            return [self._row_to_migration(row) for row in rows]

    def update_migration(self, migration: EmbeddingMigration) -> EmbeddingMigration:
        """Update migration task"""
        with self.transaction() as conn:
            migration.updated_at = _utc_now()

            conn.execute(
                text(
                    """
                    UPDATE embedding_migrations
                    SET source_model = :source_model, target_model = :target_model, source_provider = :source_provider, target_provider = :target_provider,
                        user_id = :user_id, workspace_id = :workspace_id, intent_id = :intent_id, scope = :scope, strategy = :strategy,
                        total_count = :total_count, processed_count = :processed_count, failed_count = :failed_count, status = :status,
                        started_at = :started_at, completed_at = :completed_at, error_message = :error_message, metadata = :metadata,
                        updated_at = :updated_at
                    WHERE id = :id
                """
                ),
                {
                    "id": str(migration.id),
                    "source_model": migration.source_model,
                    "target_model": migration.target_model,
                    "source_provider": migration.source_provider,
                    "target_provider": migration.target_provider,
                    "user_id": migration.user_id,
                    "workspace_id": migration.workspace_id,
                    "intent_id": migration.intent_id,
                    "scope": migration.scope,
                    "strategy": migration.strategy,
                    "total_count": migration.total_count,
                    "processed_count": migration.processed_count,
                    "failed_count": migration.failed_count,
                    "status": migration.status,
                    "started_at": migration.started_at,
                    "completed_at": migration.completed_at,
                    "error_message": migration.error_message,
                    "metadata": json.dumps(migration.metadata) if migration.metadata else None,
                    "updated_at": migration.updated_at,
                },
            )
            return migration

    def delete_migration(self, migration_id: UUID) -> bool:
        """Delete migration task and its items"""
        with self.transaction() as conn:
            result = conn.execute(
                text("DELETE FROM embedding_migrations WHERE id = :id"),
                {"id": str(migration_id)},
            )
            return result.rowcount > 0

    def create_migration_item(self, item: EmbeddingMigrationItem) -> EmbeddingMigrationItem:
        """Create a migration item"""
        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO embedding_migration_items
                    (id, migration_id, source_embedding_id, target_embedding_id,
                     source_table, status, error_message, retry_count,
                     created_at, updated_at)
                    VALUES
                    (:id, :migration_id, :source_embedding_id, :target_embedding_id,
                     :source_table, :status, :error_message, :retry_count,
                     :created_at, :updated_at)
                """
                ),
                {
                    "id": str(item.id),
                    "migration_id": str(item.migration_id),
                    "source_embedding_id": item.source_embedding_id,
                    "target_embedding_id": item.target_embedding_id,
                    "source_table": item.source_table,
                    "status": item.status,
                    "error_message": item.error_message,
                    "retry_count": item.retry_count,
                    "created_at": item.created_at,
                    "updated_at": item.updated_at,
                },
            )
            return item

    def get_migration_items(
        self,
        migration_id: UUID,
        status: Optional[ItemStatus] = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> List[EmbeddingMigrationItem]:
        """Get migration items for a migration task"""
        with self.get_connection() as conn:
            query = "SELECT * FROM embedding_migration_items WHERE migration_id = :migration_id"
            params: Dict[str, Any] = {
                "migration_id": str(migration_id),
                "limit": limit,
                "offset": offset,
            }

            if status:
                query += " AND status = :status"
                params["status"] = status.value if hasattr(status, "value") else status

            query += " ORDER BY created_at LIMIT :limit OFFSET :offset"

            rows = conn.execute(text(query), params).fetchall()
            return [self._row_to_migration_item(row) for row in rows]

    def update_migration_item(self, item: EmbeddingMigrationItem) -> EmbeddingMigrationItem:
        """Update migration item"""
        with self.transaction() as conn:
            item.updated_at = _utc_now()

            conn.execute(
                text(
                    """
                    UPDATE embedding_migration_items
                    SET source_embedding_id = :source_embedding_id, target_embedding_id = :target_embedding_id,
                        source_table = :source_table, status = :status, error_message = :error_message,
                        retry_count = :retry_count, updated_at = :updated_at
                    WHERE id = :id
                """
                ),
                {
                    "id": str(item.id),
                    "source_embedding_id": item.source_embedding_id,
                    "target_embedding_id": item.target_embedding_id,
                    "source_table": item.source_table,
                    "status": item.status,
                    "error_message": item.error_message,
                    "retry_count": item.retry_count,
                    "updated_at": item.updated_at,
                },
            )
            return item

    def _row_to_migration(self, row) -> EmbeddingMigration:
        """Convert database row to EmbeddingMigration model"""
        data = row._mapping if hasattr(row, "_mapping") else row

        metadata = {}
        if data["metadata"]:
            try:
                metadata = json.loads(data["metadata"])
            except (json.JSONDecodeError, TypeError):
                metadata = {}

        return EmbeddingMigration(
            id=UUID(data["id"]),
            source_model=data["source_model"],
            target_model=data["target_model"],
            source_provider=data["source_provider"],
            target_provider=data["target_provider"],
            user_id=data["user_id"],
            workspace_id=data["workspace_id"],
            intent_id=data["intent_id"],
            scope=data["scope"],
            strategy=data["strategy"],
            total_count=data["total_count"],
            processed_count=data["processed_count"],
            failed_count=data["failed_count"],
            status=data["status"],
            started_at=data["started_at"],
            completed_at=data["completed_at"],
            error_message=data["error_message"],
            metadata=metadata,
            created_at=data["created_at"],
            updated_at=data["updated_at"],
        )

    def _row_to_migration_item(self, row) -> EmbeddingMigrationItem:
        """Convert database row to EmbeddingMigrationItem model"""
        data = row._mapping if hasattr(row, "_mapping") else row

        return EmbeddingMigrationItem(
            id=UUID(data["id"]),
            migration_id=UUID(data["migration_id"]),
            source_embedding_id=data["source_embedding_id"],
            target_embedding_id=data["target_embedding_id"],
            source_table=data["source_table"],
            status=data["status"],
            error_message=data["error_message"],
            retry_count=data["retry_count"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
        )
