"""
Handoff Registry — SSOT idempotency table for dispatch attempts.

Each dispatch attempt registers its idempotency_key here BEFORE
execution. A UNIQUE constraint on idempotency_key prevents duplicate
dispatches at the database level.
"""

from sqlalchemy import Column, String, Integer, DateTime, UniqueConstraint, Index
from sqlalchemy.sql import func

try:
    from app.database.base import Base
except ImportError:
    try:
        from ...database.base import Base
    except ImportError:
        try:
            from app.init_db import Base
        except ImportError:
            from sqlalchemy.ext.declarative import declarative_base

            Base = declarative_base()


class HandoffRegistry(Base):
    """Idempotency registry for phase dispatch attempts.

    Before the DispatchOrchestrator fires any external side-effect,
    it INSERT-s into this table. If the INSERT violates the unique
    constraint on ``idempotency_key``, the dispatch is a duplicate
    and must be aborted.
    """

    __tablename__ = "handoff_registry"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_handoff_registry_idempotency_key"),
        Index("ix_handoff_registry_task_ir_id", "task_ir_id"),
        Index("ix_handoff_registry_execution_id", "execution_id"),
        {"extend_existing": True},
    )

    id = Column(String, primary_key=True)
    idempotency_key = Column(String, nullable=False)
    task_ir_id = Column(String, nullable=False)
    phase_id = Column(String, nullable=False)
    attempt_number = Column(Integer, nullable=False, default=1)
    status = Column(String, nullable=False, default="dispatched")

    # Completion linkage fields.
    execution_id = Column(String, nullable=True)
    artifact_id = Column(String, nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
