"""
Data Source Models
View layer over ToolConnection for data source abstraction

Phase 1: Declarative approach - DataSource is a view/service interface,
not a separate table. Uses ToolConnection as underlying storage.
"""

from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field

from .tool_connection import ToolConnection


class DataSource(BaseModel):
    """
    Data Source model - view layer over ToolConnection

    Represents a data source in the real world (WordPress site, Notion workspace,
    Google Drive, Local Filesystem, etc.) that can be shared across workspaces.

    Phase 1: This is a view model that reads from/writes to ToolConnection.
    Future: May be split into a separate table if needed.
    """
    id: str = Field(..., description="Unique data source ID (e.g., 'wp:my-blog', 'notion:workspace-1')")
    type: str = Field(..., description="Data source type: wordpress, notion, google_drive, local_filesystem, etc.")
    profile_id: str = Field(..., description="Associated profile ID")
    tenant_id: Optional[str] = Field(None, description="Tenant scope for multi-tenant support")
    owner_profile_id: Optional[str] = Field(None, description="Owner profile ID")

    # Display info
    name: str = Field(..., description="Display name for this data source")
    description: Optional[str] = Field(None, description="Optional description")
    icon: Optional[str] = Field(None, description="Data source icon emoji")

    # Configuration (sensitive data stored securely)
    config: Dict[str, Any] = Field(
        default_factory=dict,
        description="Data source configuration (URL, authentication, etc.)"
    )

    # Connection info (from ToolConnection)
    connection_id: str = Field(..., description="Underlying ToolConnection ID")
    connection_type: str = Field(..., description="Connection type: local or remote")

    # Status
    is_active: bool = Field(default=True, description="Whether data source is active")
    is_validated: bool = Field(default=False, description="Whether connection has been validated")

    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    @classmethod
    def from_tool_connection(cls, connection: ToolConnection) -> "DataSource":
        """Create DataSource view from ToolConnection"""
        if not connection.data_source_type:
            raise ValueError(f"ToolConnection {connection.id} is not a data source")

        return cls(
            id=connection.id,
            type=connection.data_source_type,
            profile_id=connection.profile_id,
            tenant_id=connection.tenant_id,
            owner_profile_id=connection.owner_profile_id,
            name=connection.name,
            description=connection.description,
            icon=connection.icon,
            config=connection.config,
            connection_id=connection.id,
            connection_type=connection.connection_type,
            is_active=connection.is_active,
            is_validated=connection.is_validated,
            created_at=connection.created_at,
            updated_at=connection.updated_at,
        )

    def to_tool_connection(self) -> ToolConnection:
        """Convert DataSource to ToolConnection for storage"""
        return ToolConnection(
            id=self.id,
            profile_id=self.profile_id,
            tool_type=self.type,
            connection_type=self.connection_type,
            name=self.name,
            description=self.description,
            icon=self.icon,
            config=self.config,
            data_source_type=self.type,
            tenant_id=self.tenant_id,
            owner_profile_id=self.owner_profile_id,
            is_active=self.is_active,
            is_validated=self.is_validated,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class CreateDataSourceRequest(BaseModel):
    """Request to create a new data source"""
    type: str = Field(..., description="Data source type")
    name: str = Field(..., description="Display name")
    description: Optional[str] = None
    icon: Optional[str] = None
    config: Dict[str, Any] = Field(default_factory=dict)
    tenant_id: Optional[str] = None
    owner_profile_id: Optional[str] = None
    connection_type: str = Field(default="local", description="Connection type: local or remote")


class UpdateDataSourceRequest(BaseModel):
    """Request to update a data source"""
    name: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None
    tenant_id: Optional[str] = None
    owner_profile_id: Optional[str] = None

