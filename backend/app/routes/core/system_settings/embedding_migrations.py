"""
Embedding Migrations endpoints
"""
from fastapi import APIRouter, HTTPException, Query, Body
from typing import Dict, Any, List, Optional
import logging

from .shared import settings_store
from .constants import DEFAULT_CHAT_MODELS, DEFAULT_EMBEDDING_MODELS
from backend.app.models.system_settings import (
    SystemSetting,
    SystemSettingsUpdate,
    SystemSettingsResponse,
    LLMModelConfig,
    LLMModelSettingsResponse,
    ModelType,
    SettingType
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/embedding-migrations", response_model=Dict[str, Any])
async def create_embedding_migration(
    request: Dict[str, Any]
):
    """Create a new embedding migration task"""
    try:
        from backend.app.services.embedding_migration_service import EmbeddingMigrationService
        from backend.app.models.embedding_migration import EmbeddingMigrationCreate, MigrationStrategy

        service = EmbeddingMigrationService()
        user_id = request.get("user_id", "default-user")

        create_request = EmbeddingMigrationCreate(
            source_model=request["source_model"],
            target_model=request["target_model"],
            source_provider=request.get("source_provider", "openai"),
            target_provider=request.get("target_provider", "openai"),
            workspace_id=request.get("workspace_id"),
            intent_id=request.get("intent_id"),
            scope=request.get("scope"),
            strategy=MigrationStrategy(request.get("strategy", "replace")),
            metadata=request.get("metadata", {})
        )

        migration = await service.create_migration_task(create_request, user_id)

        return {
            "success": True,
            "migration": {
                "id": str(migration.id),
                "source_model": migration.source_model,
                "target_model": migration.target_model,
                "total_count": migration.total_count,
                "status": migration.status,
                "created_at": migration.created_at.isoformat()
            },
            "message": f"Migration task created with {migration.total_count} embeddings to migrate"
        }
    except Exception as e:
        logger.error(f"Failed to create migration task: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create migration task: {str(e)}")


@router.get("/embedding-migrations", response_model=Dict[str, Any])
async def list_embedding_migrations(
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(100, description="Maximum number of results"),
    offset: int = Query(0, description="Offset for pagination")
):
    """List all embedding migration tasks"""
    try:
        from backend.app.services.embedding_migration_service import EmbeddingMigrationService
        from backend.app.models.embedding_migration import MigrationStatus

        service = EmbeddingMigrationService()
        migration_status = MigrationStatus(status) if status else None

        migrations = await service.list_migrations(
            user_id=user_id,
            status=migration_status,
            limit=limit,
            offset=offset
        )

        return {
            "success": True,
            "migrations": [
                {
                    "id": str(m.id),
                    "source_model": m.source_model,
                    "target_model": m.target_model,
                    "total_count": m.total_count,
                    "processed_count": m.processed_count,
                    "failed_count": m.failed_count,
                    "status": m.status,
                    "progress_percentage": (m.processed_count / m.total_count * 100) if m.total_count > 0 else 0,
                    "created_at": m.created_at.isoformat(),
                    "started_at": m.started_at.isoformat() if m.started_at else None,
                    "completed_at": m.completed_at.isoformat() if m.completed_at else None
                }
                for m in migrations
            ],
            "total": len(migrations)
        }
    except Exception as e:
        logger.error(f"Failed to list migration tasks: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list migration tasks: {str(e)}")


@router.get("/embedding-migrations/{migration_id}", response_model=Dict[str, Any])
async def get_embedding_migration(migration_id: str):
    """Get migration task status"""
    try:
        from backend.app.services.embedding_migration_service import EmbeddingMigrationService
        from uuid import UUID

        service = EmbeddingMigrationService()
        migration = await service.get_migration_status(UUID(migration_id))

        if not migration:
            raise HTTPException(status_code=404, detail=f"Migration {migration_id} not found")

        progress_percentage = (migration.processed_count / migration.total_count * 100) if migration.total_count > 0 else 0

        return {
            "success": True,
            "migration": {
                "id": str(migration.id),
                "source_model": migration.source_model,
                "target_model": migration.target_model,
                "source_provider": migration.source_provider,
                "target_provider": migration.target_provider,
                "strategy": migration.strategy,
                "total_count": migration.total_count,
                "processed_count": migration.processed_count,
                "failed_count": migration.failed_count,
                "status": migration.status,
                "progress_percentage": progress_percentage,
                "error_message": migration.error_message,
                "created_at": migration.created_at.isoformat(),
                "started_at": migration.started_at.isoformat() if migration.started_at else None,
                "completed_at": migration.completed_at.isoformat() if migration.completed_at else None
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get migration status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get migration status: {str(e)}")


@router.post("/embedding-migrations/{migration_id}/start", response_model=Dict[str, Any])
async def start_embedding_migration(migration_id: str):
    """Start executing a migration task"""
    try:
        from backend.app.services.embedding_migration_service import EmbeddingMigrationService
        from uuid import UUID

        service = EmbeddingMigrationService()
        await service.execute_migration(UUID(migration_id))

        return {
            "success": True,
            "message": f"Migration task {migration_id} started"
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to start migration: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to start migration: {str(e)}")


@router.post("/embedding-migrations/{migration_id}/cancel", response_model=Dict[str, Any])
async def cancel_embedding_migration(migration_id: str):
    """Cancel an in-progress migration task"""
    try:
        from backend.app.services.embedding_migration_service import EmbeddingMigrationService
        from uuid import UUID

        service = EmbeddingMigrationService()
        cancelled = await service.cancel_migration(UUID(migration_id))

        if not cancelled:
            raise HTTPException(status_code=404, detail=f"Migration {migration_id} not found or cannot be cancelled")

        return {
            "success": True,
            "message": f"Migration task {migration_id} cancelled"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel migration: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to cancel migration: {str(e)}")


@router.delete("/embedding-migrations/{migration_id}", response_model=Dict[str, Any])
async def delete_embedding_migration(migration_id: str):
    """Delete a migration task"""
    try:
        from backend.app.services.embedding_migration_service import EmbeddingMigrationService
        from uuid import UUID

        service = EmbeddingMigrationService()
        deleted = await service.delete_migration(UUID(migration_id))

        if not deleted:
            raise HTTPException(status_code=404, detail=f"Migration {migration_id} not found")

        return {
            "success": True,
            "message": f"Migration task {migration_id} deleted"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete migration: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete migration: {str(e)}")
