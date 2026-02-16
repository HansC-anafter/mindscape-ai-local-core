"""
Runtime Environment Model

Defines the data model for external runtime environments (e.g., cloud providers, API services).
Supports authentication configuration and encrypted storage of credentials.
"""

from sqlalchemy import Column, String, Text, JSON, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.ext.declarative import declarative_base
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
                # Fallback if Base is not available
                Base = declarative_base()

logger = logging.getLogger(__name__)


class RuntimeEnvironment(Base):
    __table_args__ = {"extend_existing": True}
    """
    Runtime Environment model for storing external runtime configurations.

    Supports:
    - User-defined runtime names and descriptions
    - Configuration page URLs
    - Authentication (API Key, OAuth2)
    - Encrypted credential storage
    """

    __tablename__ = "runtime_environments"

    # Primary key
    id = Column(String, primary_key=True)

    # User identification
    # Note: No foreign key constraint since 'users' table may not exist in all deployments
    user_id = Column(String, nullable=False, index=True)

    # Basic information
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    icon = Column(String, nullable=True)  # Emoji or icon identifier

    # Configuration URL (where the settings page is hosted)
    config_url = Column(String, nullable=False)

    # Authentication configuration
    auth_type = Column(
        String, nullable=False, default="none"
    )  # "api_key" | "oauth2" | "none"
    auth_config = Column(JSON, nullable=True)  # Encrypted credentials stored here

    # Status
    status = Column(
        String, nullable=False, default="not_configured"
    )  # "active" | "inactive" | "configured" | "not_configured"
    is_default = Column(Boolean, nullable=False, default=False)

    # OAuth connection status: "disconnected" | "pending" | "connected" | "error"
    auth_status = Column(String, nullable=False, default="disconnected", index=True)

    # Architecture support (for future Dispatch Workspace integration)
    supports_dispatch = Column(Boolean, nullable=False, default=True)
    supports_cell = Column(Boolean, nullable=False, default=True)
    recommended_for_dispatch = Column(Boolean, nullable=False, default=False)

    # Custom metadata (avoiding SQLAlchemy reserved word 'metadata')
    extra_metadata = Column(JSON, nullable=True, default=dict)

    # Timestamps
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def to_dict(self, include_sensitive: bool = False) -> Dict[str, Any]:
        """
        Convert model to dictionary.

        Args:
            include_sensitive: Whether to include encrypted credentials (default: False)

        Returns:
            Dictionary representation of the runtime environment
        """
        data = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "icon": self.icon,
            "config_url": self.config_url,
            "auth_type": self.auth_type,
            "status": self.status,
            "is_default": self.is_default,
            "supports_dispatch": self.supports_dispatch,
            "supports_cell": self.supports_cell,
            "recommended_for_dispatch": self.recommended_for_dispatch,
            "metadata": self.extra_metadata or {},
            "auth_status": self.auth_status or "disconnected",
            "auth_identity": (
                (self.auth_config or {}).get("identity")
                if self.auth_status == "connected"
                else None
            ),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

        # Only include auth_config if explicitly requested (and decrypted)
        if include_sensitive and self.auth_config:
            data["auth_config"] = self.auth_config

        return data
