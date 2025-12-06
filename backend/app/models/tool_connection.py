"""
Tool Connection Models
Defines tool connection configurations for both local and remote integrations
"""

from datetime import datetime
from typing import List, Optional, Dict, Any, Literal
from enum import Enum
from pydantic import BaseModel, Field


class ToolConnectionStatus(str, Enum):
    """
    Tool connection status

    - unavailable: Tool not implemented/registered (e.g., tool not in tool_info.py)
    - registered_but_not_connected: Tool registered in tool_info.py, but user hasn't configured connection
    - connected: API key/OAuth OK, ready to use
    """
    UNAVAILABLE = "unavailable"
    REGISTERED_BUT_NOT_CONNECTED = "registered_but_not_connected"
    CONNECTED = "connected"


class ToolConnection(BaseModel):
    """
    Tool connection configuration

    Supports both local (direct API) and remote (via remote service) connections.
    """
    id: str = Field(..., description="Unique connection ID")
    profile_id: str = Field(..., description="Associated profile ID")

    # Tool identification
    tool_type: str = Field(..., description="Tool type: wordpress, notion, google_drive, etc.")
    connection_type: Literal["local", "remote"] = Field(
        default="local",
        description="Local: direct API connection, Remote: via remote cluster/service"
    )

    # Display info
    name: str = Field(..., description="Display name for this connection")
    description: Optional[str] = Field(None, description="Optional description")
    icon: Optional[str] = Field(None, description="Tool icon emoji")

    # Local connection (direct API)
    api_key: Optional[str] = Field(None, description="API key (encrypted in storage)")
    api_secret: Optional[str] = Field(None, description="API secret (encrypted in storage)")
    oauth_token: Optional[str] = Field(None, description="OAuth token (encrypted in storage)")
    oauth_refresh_token: Optional[str] = Field(None, description="OAuth refresh token")
    base_url: Optional[str] = Field(None, description="API base URL")

    # Remote connection (via remote service)
    remote_cluster_url: Optional[str] = Field(None, description="Remote service base URL")
    remote_connection_id: Optional[str] = Field(None, description="Connection ID in remote service")

    # Configuration
    config: Dict[str, Any] = Field(
        default_factory=dict,
        description="Tool-specific configuration"
    )

    # Associations
    associated_roles: List[str] = Field(
        default_factory=list,
        description="AI role IDs that can use this tool"
    )

    # Status
    is_active: bool = Field(default=True, description="Whether connection is active")
    is_validated: bool = Field(default=False, description="Whether connection has been validated")
    last_validated_at: Optional[datetime] = None
    validation_error: Optional[str] = None

    # Usage statistics
    usage_count: int = Field(default=0, description="Number of times used")
    last_used_at: Optional[datetime] = None

    # Data Source fields (Phase 1: declarative approach, not separate table)
    data_source_type: Optional[str] = Field(
        None,
        description="DataSource type if this connection is a data source (e.g., 'wordpress', 'notion', 'google_drive')"
    )
    tenant_id: Optional[str] = Field(
        None,
        description="Tenant scope for multi-tenant support"
    )
    owner_profile_id: Optional[str] = Field(
        None,
        description="Owner profile ID (for data source ownership)"
    )

    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Extension point for platform-specific data
    x_platform: Optional[Dict[str, Any]] = Field(
        None,
        description="Platform-specific metadata (optional, can be used by extensions)"
    )

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ToolConnectionTemplate(BaseModel):
    """
    Tool connection template (for export - without sensitive data)

    Used when exporting configuration as a portable template.
    Can be imported by other users or platforms.
    Contains structure but not actual credentials.
    """
    tool_type: str
    name: str
    description: Optional[str] = None
    icon: Optional[str] = None

    # Configuration schema (without actual values)
    config_schema: Dict[str, Any] = Field(
        default_factory=dict,
        description="Configuration schema for this tool"
    )
    required_permissions: List[str] = Field(
        default_factory=list,
        description="Required permissions/scopes"
    )
    setup_guide_url: Optional[str] = Field(
        None,
        description="URL to setup guide"
    )

    associated_roles: List[str] = Field(default_factory=list)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class CreateToolConnectionRequest(BaseModel):
    """Request to create a tool connection"""
    tool_type: str
    connection_type: Literal["local", "remote"] = "local"
    name: str
    description: Optional[str] = None

    # Local connection
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    oauth_token: Optional[str] = None
    base_url: Optional[str] = None

    # Remote connection
    remote_cluster_url: Optional[str] = None
    remote_connection_id: Optional[str] = None

    config: Dict[str, Any] = Field(default_factory=dict)
    associated_roles: List[str] = Field(default_factory=list)
    x_platform: Optional[Dict[str, Any]] = Field(
        None,
        description="Platform-specific metadata (e.g., workspace_id, actor_id, metadata)"
    )


class UpdateToolConnectionRequest(BaseModel):
    """Request to update a tool connection"""
    name: Optional[str] = None
    description: Optional[str] = None
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    oauth_token: Optional[str] = None
    base_url: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    associated_roles: Optional[List[str]] = None
    is_active: Optional[bool] = None
    x_platform: Optional[Dict[str, Any]] = Field(
        None,
        description="Platform-specific metadata (e.g., workspace_id, actor_id, metadata)"
    )


class ValidateToolConnectionRequest(BaseModel):
    """Request to validate a tool connection"""
    connection_id: str


class ToolConnectionValidationResult(BaseModel):
    """Result of tool connection validation"""
    connection_id: str
    is_valid: bool
    error_message: Optional[str] = None
    validated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
