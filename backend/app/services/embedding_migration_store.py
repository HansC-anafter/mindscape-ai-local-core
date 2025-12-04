"""
Embedding Migration Store

Manages embedding migration tasks storage in SQLite database.
"""

import json
import sqlite3
from typing import Optional, List, Dict, Any
from pathlib import Path
from datetime import datetime
from uuid import UUID
import logging

from backend.app.models.embedding_migration import (
    EmbeddingMigration,
    EmbeddingMigrationItem,
    MigrationStatus,
    ItemStatus
)

logger = logging.getLogger(__name__)


class EmbeddingMigrationStore:
    """SQLite-based embedding migration store"""

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize embedding migration store

        Args:
            db_path: Path to SQLite database (default: ./data/mindscape.db)
        """
        if db_path is None:
            db_path = Path("./data/mindscape.db")
        else:
            db_path = Path(db_path)

        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize embedding migration tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Create embedding_migrations table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS embedding_migrations (
                id TEXT PRIMARY KEY,
                source_model TEXT NOT NULL,
                target_model TEXT NOT NULL,
                source_provider TEXT NOT NULL,
                target_provider TEXT NOT NULL,
                user_id TEXT NOT NULL,
                workspace_id TEXT,
                intent_id TEXT,
                scope TEXT,
                strategy TEXT NOT NULL,
                total_count INTEGER DEFAULT 0,
                processed_count INTEGER DEFAULT 0,
                failed_count INTEGER DEFAULT 0,
                status TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT,
                error_message TEXT,
                metadata TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        # Create embedding_migration_items table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS embedding_migration_items (
                id TEXT PRIMARY KEY,
                migration_id TEXT NOT NULL,
                source_embedding_id TEXT NOT NULL,
                target_embedding_id TEXT,
                source_table TEXT NOT NULL,
                status TEXT NOT NULL,
                error_message TEXT,
                retry_count INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (migration_id) REFERENCES embedding_migrations(id) ON DELETE CASCADE
            )
        """)

        # Create indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_embedding_migrations_user_id
            ON embedding_migrations(user_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_embedding_migrations_status
            ON embedding_migrations(status)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_embedding_migration_items_migration_id
            ON embedding_migration_items(migration_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_embedding_migration_items_status
            ON embedding_migration_items(status)
        """)

        conn.commit()
        conn.close()

    def create_migration(self, migration: EmbeddingMigration) -> EmbeddingMigration:
        """
        Create a new migration task

        Args:
            migration: Migration task to create

        Returns:
            Created migration task
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO embedding_migrations
                (id, source_model, target_model, source_provider, target_provider,
                 user_id, workspace_id, intent_id, scope, strategy,
                 total_count, processed_count, failed_count, status,
                 started_at, completed_at, error_message, metadata,
                 created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                str(migration.id),
                migration.source_model,
                migration.target_model,
                migration.source_provider,
                migration.target_provider,
                migration.user_id,
                migration.workspace_id,
                migration.intent_id,
                migration.scope,
                migration.strategy,
                migration.total_count,
                migration.processed_count,
                migration.failed_count,
                migration.status,
                migration.started_at.isoformat() if migration.started_at else None,
                migration.completed_at.isoformat() if migration.completed_at else None,
                migration.error_message,
                json.dumps(migration.metadata) if migration.metadata else None,
                migration.created_at.isoformat(),
                migration.updated_at.isoformat()
            ))

            conn.commit()
            return migration

        finally:
            conn.close()

    def get_migration(self, migration_id: UUID) -> Optional[EmbeddingMigration]:
        """
        Get migration task by ID

        Args:
            migration_id: Migration task ID

        Returns:
            Migration task or None if not found
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT * FROM embedding_migrations
                WHERE id = ?
            """, (str(migration_id),))

            row = cursor.fetchone()
            if not row:
                return None

            return self._row_to_migration(row)

        finally:
            conn.close()

    def list_migrations(
        self,
        user_id: Optional[str] = None,
        status: Optional[MigrationStatus] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[EmbeddingMigration]:
        """
        List migration tasks

        Args:
            user_id: Filter by user ID
            status: Filter by status
            limit: Maximum number of results
            offset: Offset for pagination

        Returns:
            List of migration tasks
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            query = "SELECT * FROM embedding_migrations WHERE 1=1"
            params = []

            if user_id:
                query += " AND user_id = ?"
                params.append(user_id)

            if status:
                query += " AND status = ?"
                params.append(status.value)

            query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            cursor.execute(query, params)
            rows = cursor.fetchall()

            return [self._row_to_migration(row) for row in rows]

        finally:
            conn.close()

    def update_migration(self, migration: EmbeddingMigration) -> EmbeddingMigration:
        """
        Update migration task

        Args:
            migration: Migration task to update

        Returns:
            Updated migration task
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            migration.updated_at = datetime.utcnow()

            cursor.execute("""
                UPDATE embedding_migrations
                SET source_model = ?, target_model = ?, source_provider = ?, target_provider = ?,
                    user_id = ?, workspace_id = ?, intent_id = ?, scope = ?, strategy = ?,
                    total_count = ?, processed_count = ?, failed_count = ?, status = ?,
                    started_at = ?, completed_at = ?, error_message = ?, metadata = ?,
                    updated_at = ?
                WHERE id = ?
            """, (
                migration.source_model,
                migration.target_model,
                migration.source_provider,
                migration.target_provider,
                migration.user_id,
                migration.workspace_id,
                migration.intent_id,
                migration.scope,
                migration.strategy,
                migration.total_count,
                migration.processed_count,
                migration.failed_count,
                migration.status,
                migration.started_at.isoformat() if migration.started_at else None,
                migration.completed_at.isoformat() if migration.completed_at else None,
                migration.error_message,
                json.dumps(migration.metadata) if migration.metadata else None,
                migration.updated_at.isoformat(),
                str(migration.id)
            ))

            conn.commit()
            return migration

        finally:
            conn.close()

    def delete_migration(self, migration_id: UUID) -> bool:
        """
        Delete migration task and its items

        Args:
            migration_id: Migration task ID

        Returns:
            True if deleted, False if not found
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("DELETE FROM embedding_migrations WHERE id = ?", (str(migration_id),))
            deleted = cursor.rowcount > 0
            conn.commit()
            return deleted

        finally:
            conn.close()

    def create_migration_item(self, item: EmbeddingMigrationItem) -> EmbeddingMigrationItem:
        """
        Create a migration item

        Args:
            item: Migration item to create

        Returns:
            Created migration item
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO embedding_migration_items
                (id, migration_id, source_embedding_id, target_embedding_id,
                 source_table, status, error_message, retry_count,
                 created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                str(item.id),
                str(item.migration_id),
                item.source_embedding_id,
                item.target_embedding_id,
                item.source_table,
                item.status,
                item.error_message,
                item.retry_count,
                item.created_at.isoformat(),
                item.updated_at.isoformat()
            ))

            conn.commit()
            return item

        finally:
            conn.close()

    def get_migration_items(
        self,
        migration_id: UUID,
        status: Optional[ItemStatus] = None,
        limit: int = 1000,
        offset: int = 0
    ) -> List[EmbeddingMigrationItem]:
        """
        Get migration items for a migration task

        Args:
            migration_id: Migration task ID
            status: Filter by status
            limit: Maximum number of results
            offset: Offset for pagination

        Returns:
            List of migration items
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            query = """
                SELECT * FROM embedding_migration_items
                WHERE migration_id = ?
            """
            params = [str(migration_id)]

            if status:
                query += " AND status = ?"
                params.append(status.value)

            query += " ORDER BY created_at LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            cursor.execute(query, params)
            rows = cursor.fetchall()

            return [self._row_to_migration_item(row) for row in rows]

        finally:
            conn.close()

    def update_migration_item(self, item: EmbeddingMigrationItem) -> EmbeddingMigrationItem:
        """
        Update migration item

        Args:
            item: Migration item to update

        Returns:
            Updated migration item
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            item.updated_at = datetime.utcnow()

            cursor.execute("""
                UPDATE embedding_migration_items
                SET source_embedding_id = ?, target_embedding_id = ?,
                    source_table = ?, status = ?, error_message = ?,
                    retry_count = ?, updated_at = ?
                WHERE id = ?
            """, (
                item.source_embedding_id,
                item.target_embedding_id,
                item.source_table,
                item.status,
                item.error_message,
                item.retry_count,
                item.updated_at.isoformat(),
                str(item.id)
            ))

            conn.commit()
            return item

        finally:
            conn.close()

    def _row_to_migration(self, row: sqlite3.Row) -> EmbeddingMigration:
        """Convert database row to EmbeddingMigration model"""
        metadata = {}
        if row["metadata"]:
            try:
                metadata = json.loads(row["metadata"])
            except (json.JSONDecodeError, TypeError):
                metadata = {}

        return EmbeddingMigration(
            id=UUID(row["id"]),
            source_model=row["source_model"],
            target_model=row["target_model"],
            source_provider=row["source_provider"],
            target_provider=row["target_provider"],
            user_id=row["user_id"],
            workspace_id=row["workspace_id"],
            intent_id=row["intent_id"],
            scope=row["scope"],
            strategy=row["strategy"],
            total_count=row["total_count"],
            processed_count=row["processed_count"],
            failed_count=row["failed_count"],
            status=row["status"],
            started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
            completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
            error_message=row["error_message"],
            metadata=metadata,
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"])
        )

    def _row_to_migration_item(self, row: sqlite3.Row) -> EmbeddingMigrationItem:
        """Convert database row to EmbeddingMigrationItem model"""
        return EmbeddingMigrationItem(
            id=UUID(row["id"]),
            migration_id=UUID(row["migration_id"]),
            source_embedding_id=row["source_embedding_id"],
            target_embedding_id=row["target_embedding_id"],
            source_table=row["source_table"],
            status=row["status"],
            error_message=row["error_message"],
            retry_count=row["retry_count"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"])
        )

