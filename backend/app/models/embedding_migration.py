"""
Embedding Migration Models

Models for managing embedding model migration tasks and tracking migration progress.
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from enum import Enum
from datetime import datetime
from uuid import UUID, uuid4


class MigrationStatus(str, Enum):
    """Migration task status"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MigrationStrategy(str, Enum):
    """Migration strategy for handling existing embeddings"""
    REPLACE = "replace"  # Update existing records with new embedding
    PRESERVE = "preserve"  # Keep old embedding, create new records
    DEPRECATE = "deprecate"  # Mark old embedding as deprecated


class ItemStatus(str, Enum):
    """Migration item status"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class EmbeddingMigration(BaseModel):
    """
    Embedding Migration Task

    Represents a migration task for converting embeddings from one model to another.
    """

    id: UUID = Field(default_factory=uuid4, description="Migration task ID")
    source_model: str = Field(..., description="Source embedding model name")
    target_model: str = Field(..., description="Target embedding model name")
    source_provider: str = Field(..., description="Source provider (e.g., 'openai')")
    target_provider: str = Field(..., description="Target provider (e.g., 'openai')")
    user_id: str = Field(..., description="User ID who initiated the migration")
    workspace_id: Optional[str] = Field(None, description="Optional workspace ID filter")
    intent_id: Optional[str] = Field(None, description="Optional intent ID filter")
    scope: Optional[str] = Field(None, description="Optional scope filter (global, workspace, intent)")
    strategy: MigrationStrategy = Field(
        default=MigrationStrategy.REPLACE,
        description="Migration strategy"
    )
    total_count: int = Field(default=0, description="Total number of embeddings to migrate")
    processed_count: int = Field(default=0, description="Number of embeddings processed")
    failed_count: int = Field(default=0, description="Number of embeddings that failed")
    status: MigrationStatus = Field(
        default=MigrationStatus.PENDING,
        description="Migration status"
    )
    started_at: Optional[datetime] = Field(None, description="Migration start time")
    completed_at: Optional[datetime] = Field(None, description="Migration completion time")
    error_message: Optional[str] = Field(None, description="Error message if migration failed")
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional migration metadata"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")

    class Config:
        use_enum_values = True


class EmbeddingMigrationItem(BaseModel):
    """
    Embedding Migration Item

    Represents a single embedding record being migrated.
    """

    id: UUID = Field(default_factory=uuid4, description="Migration item ID")
    migration_id: UUID = Field(..., description="Parent migration task ID")
    source_embedding_id: str = Field(..., description="Source embedding record ID")
    target_embedding_id: Optional[str] = Field(None, description="Target embedding record ID")
    source_table: str = Field(
        ...,
        description="Source table name (mindscape_personal, playbook_knowledge, external_docs)"
    )
    status: ItemStatus = Field(
        default=ItemStatus.PENDING,
        description="Item migration status"
    )
    error_message: Optional[str] = Field(None, description="Error message if item migration failed")
    retry_count: int = Field(default=0, description="Number of retry attempts")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")

    class Config:
        use_enum_values = True


class EmbeddingMigrationCreate(BaseModel):
    """Request model for creating a migration task"""

    source_model: str = Field(..., description="Source embedding model name")
    target_model: str = Field(..., description="Target embedding model name")
    source_provider: str = Field(..., description="Source provider")
    target_provider: str = Field(..., description="Target provider")
    workspace_id: Optional[str] = Field(None, description="Optional workspace ID filter")
    intent_id: Optional[str] = Field(None, description="Optional intent ID filter")
    scope: Optional[str] = Field(None, description="Optional scope filter")
    strategy: MigrationStrategy = Field(
        default=MigrationStrategy.REPLACE,
        description="Migration strategy"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional migration metadata"
    )


class EmbeddingMigrationResponse(BaseModel):
    """Response model for migration task"""

    migration: EmbeddingMigration = Field(..., description="Migration task details")
    progress_percentage: float = Field(..., description="Migration progress percentage")
    estimated_completion: Optional[datetime] = Field(
        None,
        description="Estimated completion time"
    )


class EmbeddingMigrationListResponse(BaseModel):
    """Response model for listing migration tasks"""

    migrations: List[EmbeddingMigration] = Field(..., description="List of migration tasks")
    total: int = Field(..., description="Total number of migrations")


class EmbeddingMigrationProgress(BaseModel):
    """Migration progress information"""

    migration_id: UUID = Field(..., description="Migration task ID")
    total_count: int = Field(..., description="Total number of items")
    processed_count: int = Field(..., description="Number of items processed")
    failed_count: int = Field(..., description="Number of items failed")
    progress_percentage: float = Field(..., description="Progress percentage")
    status: MigrationStatus = Field(..., description="Current status")
    estimated_completion: Optional[datetime] = Field(None, description="Estimated completion time")

