"""
Tool Registry Model.

Stores registered tools discovered from WordPress sites and other providers.
"""
from typing import Dict, Any, List, Optional, Literal
from datetime import datetime
from pydantic import BaseModel, Field


class ToolInputSchema(BaseModel):
    """Input schema for a tool"""
    type: str = "object"
    properties: Dict[str, Any] = Field(default_factory=dict)
    required: List[str] = Field(default_factory=list)


class RegisteredTool(BaseModel):
    """A registered tool in the mindscape ai tool registry"""

    tool_id: str = Field(..., description="Unique tool ID (e.g., 'wp.my-site.post.create_draft')")
    site_id: str = Field(..., description="Site/connection ID")
    provider: str = Field(..., description="Provider type: wordpress, notion, etc.")
    display_name: str = Field(..., description="Display name for UI")
    origin_capability_id: str = Field(..., description="Original capability ID from discovery")

    # Capability metadata
    category: str = Field(..., description="Tool category: content, commerce, seo, etc.")
    description: str = Field(..., description="Tool description")
    endpoint: str = Field(..., description="API endpoint")
    methods: List[str] = Field(..., description="HTTP methods")
    danger_level: str = Field(default="low", description="low, medium, high")
    input_schema: ToolInputSchema = Field(default_factory=ToolInputSchema)

    # Control flags
    enabled: bool = Field(default=True, description="Whether tool is enabled")
    read_only: bool = Field(default=False, description="Read-only mode (for high-risk tools)")
    allowed_agent_roles: List[str] = Field(default_factory=list, description="Agent roles allowed to use this tool")
    side_effect_level: Optional[str] = Field(default=None, description="readonly, soft_write, or external_write")

    # Metadata
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ToolConnectionModel(BaseModel):
    """
    Tool connection configuration model

    Supports multiple tool types with multi-tenant capability.
    Maintains backward compatibility with WordPress-specific fields.
    """

    # Basic fields
    id: str = Field(..., description="Unique connection ID")
    profile_id: str = Field(..., description="Associated profile ID for multi-tenant support")
    name: str = Field(..., description="Display name for this connection")

    # Tool identification
    tool_type: str = Field(..., description="Tool type: wordpress, notion, google_drive, etc.")
    connection_type: Literal["local", "remote"] = Field(
        default="local",
        description="Local: direct API connection, Remote: via remote cluster/service"
    )

    # Display info
    description: Optional[str] = Field(None, description="Optional description")
    icon: Optional[str] = Field(None, description="Tool icon emoji")

    # Generic connection fields
    api_key: Optional[str] = Field(None, description="API key (encrypted in storage)")
    api_secret: Optional[str] = Field(None, description="API secret (encrypted in storage)")
    oauth_token: Optional[str] = Field(None, description="OAuth token (encrypted in storage)")
    oauth_refresh_token: Optional[str] = Field(None, description="OAuth refresh token")
    base_url: Optional[str] = Field(None, description="API base URL")

    # WordPress-specific fields (backward compatibility)
    wp_url: Optional[str] = Field(None, description="WordPress site URL (deprecated, use base_url)")
    wp_username: Optional[str] = Field(None, description="WordPress username (deprecated, use api_key)")
    wp_application_password: Optional[str] = Field(None, description="WordPress application password (deprecated, use api_secret)")

    # Remote connection fields
    remote_cluster_url: Optional[str] = Field(None, description="Remote service cluster URL")
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

    # Status fields
    enabled: bool = Field(default=True, description="Whether connection is enabled")
    is_active: bool = Field(default=True, description="Whether connection is active")
    is_validated: bool = Field(default=False, description="Whether connection has been validated")
    last_validated_at: Optional[datetime] = Field(None, description="Last validation timestamp")
    validation_error: Optional[str] = Field(None, description="Validation error message if any")

    # Usage statistics
    usage_count: int = Field(default=0, description="Number of times used")
    last_used_at: Optional[datetime] = Field(None, description="Last usage timestamp")

    # Discovery fields
    last_discovery: Optional[datetime] = Field(None, description="Last discovery timestamp")
    discovery_method: Optional[str] = Field(None, description="Discovery method: plugin, fallback, etc.")

    # Extension point
    x_platform: Optional[Dict[str, Any]] = Field(
        None,
        description="Platform-specific metadata (optional, can be used by extensions)"
    )

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

