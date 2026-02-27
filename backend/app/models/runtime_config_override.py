"""
Runtime Config Override Model

Workspace-scoped overrides for runtime environment metadata.
Allows workspaces to set their own chainagent_id, site_key, etc.
with higher priority than the global runtime config.

Scope semantics:
  - "workspace": override applies only to this workspace
  - "global": override applies to all workspaces (set from any workspace)

Resolution order: workspace override > global override > runtime.extra_metadata
"""

from sqlalchemy import Column, String, JSON, DateTime, UniqueConstraint
from sqlalchemy.sql import func
from typing import Dict, Any

try:
    from app.database.base import Base
except ImportError:
    try:
        from ...database.base import Base
    except ImportError:
        from sqlalchemy.ext.declarative import declarative_base

        Base = declarative_base()


class RuntimeConfigOverride(Base):
    __tablename__ = "runtime_config_overrides"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "runtime_id", name="uq_workspace_runtime_override"
        ),
        {"extend_existing": True},
    )

    id = Column(String, primary_key=True)
    workspace_id = Column(String, nullable=False, index=True)
    runtime_id = Column(String, nullable=False, index=True)

    # "workspace" = only this workspace; "global" = fallback for all
    scope = Column(String, nullable=False, default="workspace")

    # Metadata overrides (chainagent_id, site_key, etc.)
    config_overrides = Column(JSON, nullable=False, default=dict)

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "runtime_id": self.runtime_id,
            "scope": self.scope,
            "config_overrides": self.config_overrides or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
