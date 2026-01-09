"""
Channel Binding Model

Defines the data model for binding Site-Hub channels to Local-Core workspaces.
"""

from sqlalchemy import Column, String, Text, JSON, Boolean, DateTime, Index
from sqlalchemy.sql import func
from typing import Optional, Dict, Any
import logging

# Import Base from the database base module
try:
    from app.database.base import Base
except ImportError:
    try:
        from ...database.base import Base
    except ImportError:
        try:
            from app.init_db import Base
        except ImportError:
            try:
                from ...init_db import Base
            except ImportError:
                from sqlalchemy.ext.declarative import declarative_base
                Base = declarative_base()

logger = logging.getLogger(__name__)


class ChannelBinding(Base):
    __table_args__ = (
        Index('idx_workspace_runtime_channel', 'workspace_id', 'runtime_id', 'channel_id'),
        {'extend_existing': True}
    )
    """
    Channel Binding model for binding Site-Hub channels to Local-Core workspaces.

    Supports:
    - Binding Site-Hub channels to workspaces
    - Storing channel metadata (agency, tenant, chainagent)
    - Binding configuration (push_enabled, notification_enabled, etc.)
    - Status tracking
    """

    __tablename__ = "channel_bindings"

    # Primary key
    id = Column(String, primary_key=True)

    # Binding relationships
    workspace_id = Column(String, nullable=False, index=True)
    runtime_id = Column(String, nullable=False, index=True)
    channel_id = Column(String, nullable=False, index=True)

    # Channel information
    channel_type = Column(String, nullable=False)  # "line", "web", "seo", etc.
    channel_name = Column(String, nullable=True)

    # Site-Hub hierarchy
    agency = Column(String, nullable=True, index=True)
    tenant = Column(String, nullable=True, index=True)
    chainagent = Column(String, nullable=True, index=True)

    # Binding configuration
    binding_config = Column(JSON, nullable=True, default=dict)  # push_enabled, notification_enabled, etc.

    # Status
    status = Column(String, nullable=False, default="active")  # "active" | "inactive" | "pending"

    # Metadata (using extra_metadata to avoid SQLAlchemy reserved word conflict)
    extra_metadata = Column(JSON, nullable=True, default=dict)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert model to dictionary.

        Returns:
            Dictionary representation of the channel binding
        """
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "runtime_id": self.runtime_id,
            "channel_id": self.channel_id,
            "channel_type": self.channel_type,
            "channel_name": self.channel_name,
            "agency": self.agency,
            "tenant": self.tenant,
            "chainagent": self.chainagent,
            "binding_config": self.binding_config or {},
            "status": self.status,
            "metadata": self.extra_metadata or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

