from sqlalchemy import Column, String, DateTime, Text, Index
from sqlalchemy.dialects.postgresql import JSONB
from app.database.base import Base
from datetime import datetime


class ArtifactModel(Base):
    __tablename__ = "artifacts"

    id = Column(String, primary_key=True)
    workspace_id = Column(String, nullable=False)
    intent_id = Column(String)
    task_id = Column(String)
    execution_id = Column(String)
    playbook_code = Column(String, nullable=False)
    artifact_type = Column(String, nullable=False)
    title = Column(String, nullable=False)
    summary = Column(String)
    content = Column(JSONB, nullable=False)  # Dict/Content
    storage_ref = Column(String)
    sync_state = Column(String)
    primary_action_type = Column(String, nullable=False)
    metadata_ = Column("metadata", JSONB)  # mapped to "metadata" column in DB
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)

    # New columns from migrations
    source_execution_id = Column(String)
    source_step_id = Column(String)
    thread_id = Column(String)

    __table_args__ = (
        Index("idx_artifacts_workspace", "workspace_id"),
        Index("idx_artifacts_intent", "intent_id"),
        Index("idx_artifacts_task", "task_id"),
        Index("idx_artifacts_playbook", "playbook_code"),
        Index(
            "idx_artifacts_created_at", "created_at"
        ),  # DESC handled by DB, SQLAlchemy creates standard index
        Index("idx_artifacts_workspace_created_at", "workspace_id", "created_at"),
        Index("idx_artifacts_workspace_intent", "workspace_id", "intent_id"),
        Index("idx_artifacts_execution", "source_execution_id"),
        Index("idx_artifacts_step", "source_step_id"),
        Index("idx_artifacts_thread", "workspace_id", "thread_id", "created_at"),
    )
