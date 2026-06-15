"""
Embedding Migration Service

Service for migrating embeddings from one model to another.
Handles batch processing, error recovery, and progress tracking.
"""

import logging
import asyncio
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


from uuid import UUID
import psycopg2

from app.database.config import get_vector_postgres_config

from backend.app.models.embedding_migration import (
    EmbeddingMigration,
    EmbeddingMigrationItem,
    EmbeddingMigrationCreate,
    MigrationStatus,
    MigrationStrategy,
    ItemStatus,
)
from backend.app.services.embedding_migration_store import EmbeddingMigrationStore
from backend.app.services.embedding_migration_apply import apply_migration_strategy
from backend.app.services.embedding_migration_providers import regenerate_embedding
from backend.app.services.embedding_migration_queries import (
    count_embeddings_to_migrate,
    fetch_embeddings_to_migrate,
)
from backend.app.services.embedding_migration_text import extract_source_text

logger = logging.getLogger(__name__)


class EmbeddingMigrationService:
    """Service for managing embedding migrations"""

    def __init__(self, store: Optional[EmbeddingMigrationStore] = None):
        """
        Initialize embedding migration service

        Args:
            store: EmbeddingMigrationStore instance (optional, will create if not provided)
        """
        self.store = store or EmbeddingMigrationStore()
        self._active_migrations: Dict[UUID, asyncio.Task] = {}

    def _get_postgres_config(self):
        """Get PostgreSQL config from environment"""
        return get_vector_postgres_config()

    def _get_connection(self):
        """Get PostgreSQL connection"""
        return psycopg2.connect(**self._get_postgres_config())

    async def create_migration_task(
        self, request: EmbeddingMigrationCreate, user_id: str
    ) -> EmbeddingMigration:
        """
        Create a new migration task

        Args:
            request: Migration creation request
            user_id: User ID initiating the migration

        Returns:
            Created migration task
        """
        # Count embeddings that need to be migrated
        total_count = await self._count_embeddings_to_migrate(
            source_model=request.source_model,
            source_provider=request.source_provider,
            workspace_id=request.workspace_id,
            intent_id=request.intent_id,
            scope=request.scope,
        )

        # Create migration task
        migration = EmbeddingMigration(
            source_model=request.source_model,
            target_model=request.target_model,
            source_provider=request.source_provider,
            target_provider=request.target_provider,
            user_id=user_id,
            workspace_id=request.workspace_id,
            intent_id=request.intent_id,
            scope=request.scope,
            strategy=request.strategy,
            total_count=total_count,
            metadata=request.metadata,
        )

        created_migration = self.store.create_migration(migration)
        logger.info(
            f"Created migration task {created_migration.id} with {total_count} embeddings to migrate"
        )

        return created_migration

    async def _count_embeddings_to_migrate(
        self,
        source_model: str,
        source_provider: str,
        workspace_id: Optional[str] = None,
        intent_id: Optional[str] = None,
        scope: Optional[str] = None,
    ) -> int:
        """
        Count embeddings that need to be migrated

        Args:
            source_model: Source embedding model name
            source_provider: Source provider name
            workspace_id: Optional workspace ID filter
            intent_id: Optional intent ID filter
            scope: Optional scope filter

        Returns:
            Number of embeddings to migrate
        """

        return await count_embeddings_to_migrate(
            get_connection=self._get_connection,
            source_model=source_model,
            source_provider=source_provider,
            workspace_id=workspace_id,
            intent_id=intent_id,
            scope=scope,
        )

    async def get_migration_status(
        self, migration_id: UUID
    ) -> Optional[EmbeddingMigration]:
        """
        Get migration task status

        Args:
            migration_id: Migration task ID

        Returns:
            Migration task or None if not found
        """
        return self.store.get_migration(migration_id)

    async def list_migrations(
        self,
        user_id: Optional[str] = None,
        status: Optional[MigrationStatus] = None,
        limit: int = 100,
        offset: int = 0,
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
        return self.store.list_migrations(
            user_id=user_id, status=status, limit=limit, offset=offset
        )

    async def execute_migration(self, migration_id: UUID) -> None:
        """
        Execute migration task asynchronously

        Args:
            migration_id: Migration task ID
        """
        migration = self.store.get_migration(migration_id)
        if not migration:
            raise ValueError(f"Migration {migration_id} not found")

        if migration.status in [MigrationStatus.IN_PROGRESS, MigrationStatus.COMPLETED]:
            logger.warning(f"Migration {migration_id} is already {migration.status}")
            return

        # Check if migration is already running
        if migration_id in self._active_migrations:
            logger.warning(f"Migration {migration_id} is already running")
            return

        # Update status to in_progress
        migration.status = MigrationStatus.IN_PROGRESS
        migration.started_at = _utc_now()
        self.store.update_migration(migration)

        # Start migration task
        task = asyncio.create_task(self._execute_migration_task(migration))
        self._active_migrations[migration_id] = task

        logger.info(f"Started migration task {migration_id}")

    async def _execute_migration_task(self, migration: EmbeddingMigration) -> None:
        """
        Execute migration task (internal async task)

        Args:
            migration: Migration task to execute
        """
        try:
            # Fetch embeddings to migrate
            embeddings = await self._fetch_embeddings_to_migrate(migration)

            # Create migration items
            await self._create_migration_items(migration, embeddings)

            # Process embeddings in batches
            batch_size = 10
            for i in range(0, len(embeddings), batch_size):
                batch = embeddings[i : i + batch_size]
                await self._process_batch(migration, batch)

                # Check for cancellation
                current_migration = self.store.get_migration(migration.id)
                if (
                    current_migration
                    and current_migration.status == MigrationStatus.CANCELLED
                ):
                    logger.info(f"Migration {migration.id} was cancelled")
                    return

            # Mark migration as completed
            migration.status = MigrationStatus.COMPLETED
            migration.completed_at = _utc_now()
            self.store.update_migration(migration)

            logger.info(f"Completed migration task {migration.id}")

        except Exception as e:
            logger.error(f"Migration task {migration.id} failed: {e}", exc_info=True)
            migration.status = MigrationStatus.FAILED
            migration.error_message = str(e)
            migration.completed_at = _utc_now()
            self.store.update_migration(migration)

        finally:
            # Remove from active migrations
            if migration.id in self._active_migrations:
                del self._active_migrations[migration.id]

    async def _fetch_embeddings_to_migrate(
        self, migration: EmbeddingMigration
    ) -> List[Dict[str, Any]]:
        """
        Fetch embeddings that need to be migrated

        Args:
            migration: Migration task

        Returns:
            List of embedding records
        """

        return await fetch_embeddings_to_migrate(
            get_connection=self._get_connection,
            migration=migration,
        )

    async def _create_migration_items(
        self, migration: EmbeddingMigration, embeddings: List[Dict[str, Any]]
    ) -> None:
        """
        Create migration items for all embeddings

        Args:
            migration: Migration task
            embeddings: List of embedding records
        """
        for embedding_record in embeddings:
            item = EmbeddingMigrationItem(
                migration_id=migration.id,
                source_embedding_id=str(embedding_record["id"]),
                source_table="mindscape_personal",
                status=ItemStatus.PENDING,
            )
            self.store.create_migration_item(item)

    async def _process_batch(
        self, migration: EmbeddingMigration, batch: List[Dict[str, Any]]
    ) -> None:
        """
        Process a batch of embeddings

        Args:
            migration: Migration task
            batch: List of embedding records to process
        """
        for embedding_record in batch:
            try:
                await self._migrate_single_embedding(migration, embedding_record)
            except Exception as e:
                logger.error(
                    f"Failed to migrate embedding {embedding_record['id']}: {e}",
                    exc_info=True,
                )
                # Update migration item status
                items = self.store.get_migration_items(migration.id)
                for item in items:
                    if item.source_embedding_id == str(embedding_record["id"]):
                        item.status = ItemStatus.FAILED
                        item.error_message = str(e)
                        self.store.update_migration_item(item)
                        break

                # Update migration failed count
                migration.failed_count += 1
                self.store.update_migration(migration)

    async def _migrate_single_embedding(
        self, migration: EmbeddingMigration, embedding_record: Dict[str, Any]
    ) -> None:
        """
        Migrate a single embedding

        Args:
            migration: Migration task
            embedding_record: Embedding record to migrate
        """
        # Get migration item
        items = self.store.get_migration_items(migration.id)
        migration_item = None
        for item in items:
            if item.source_embedding_id == str(embedding_record["id"]):
                migration_item = item
                break

        if not migration_item:
            logger.warning(
                f"Migration item not found for embedding {embedding_record['id']}"
            )
            return

        # Update item status to in_progress
        migration_item.status = ItemStatus.IN_PROGRESS
        self.store.update_migration_item(migration_item)

        # Extract source text
        source_text = self._extract_source_text(embedding_record)
        if not source_text:
            raise ValueError(
                f"Could not extract text from embedding {embedding_record['id']}"
            )

        # Regenerate embedding with target model
        new_embedding = await self._regenerate_embedding(
            source_text=source_text,
            target_model=migration.target_model,
            target_provider=migration.target_provider,
        )

        if not new_embedding:
            raise ValueError(
                f"Failed to regenerate embedding for {embedding_record['id']}"
            )

        # Apply migration strategy
        await self._apply_migration_strategy(
            migration=migration,
            embedding_record=embedding_record,
            new_embedding=new_embedding,
            migration_item=migration_item,
        )

        # Update item status to completed
        migration_item.status = ItemStatus.COMPLETED
        self.store.update_migration_item(migration_item)

        # Update migration progress
        migration.processed_count += 1
        self.store.update_migration(migration)

    def _extract_source_text(self, embedding_record: Dict[str, Any]) -> Optional[str]:
        """
        Extract source text from embedding record

        Args:
            embedding_record: Embedding record

        Returns:
            Source text or None if not found
        """
        return extract_source_text(embedding_record)

    async def _regenerate_embedding(
        self, source_text: str, target_model: str, target_provider: str
    ) -> Optional[List[float]]:
        """
        Regenerate embedding with target model

        Args:
            source_text: Source text to embed
            target_model: Target embedding model name
            target_provider: Target provider name

        Returns:
            New embedding vector or None if failed
        """
        return await regenerate_embedding(
            source_text=source_text,
            target_model=target_model,
            target_provider=target_provider,
        )

    async def _apply_migration_strategy(
        self,
        migration: EmbeddingMigration,
        embedding_record: Dict[str, Any],
        new_embedding: List[float],
        migration_item: EmbeddingMigrationItem,
    ) -> None:
        """
        Apply migration strategy to update embedding

        Args:
            migration: Migration task
            embedding_record: Original embedding record
            new_embedding: New embedding vector
            migration_item: Migration item
        """

        await apply_migration_strategy(
            get_connection=self._get_connection,
            store=self.store,
            migration=migration,
            embedding_record=embedding_record,
            new_embedding=new_embedding,
            migration_item=migration_item,
        )

    async def cancel_migration(self, migration_id: UUID) -> bool:
        """
        Cancel an in-progress migration

        Args:
            migration_id: Migration task ID

        Returns:
            True if cancelled, False if not found or cannot be cancelled
        """
        migration = self.store.get_migration(migration_id)
        if not migration:
            return False

        if migration.status not in [
            MigrationStatus.PENDING,
            MigrationStatus.IN_PROGRESS,
        ]:
            logger.warning(
                f"Cannot cancel migration {migration_id} with status {migration.status}"
            )
            return False

        migration.status = MigrationStatus.CANCELLED
        migration.completed_at = _utc_now()
        self.store.update_migration(migration)

        logger.info(f"Cancelled migration {migration_id}")
        return True

    async def delete_migration(self, migration_id: UUID) -> bool:
        """
        Delete a migration task

        Args:
            migration_id: Migration task ID

        Returns:
            True if deleted, False if not found
        """
        return self.store.delete_migration(migration_id)
