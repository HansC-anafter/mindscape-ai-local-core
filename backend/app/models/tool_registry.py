"""
Tool Registry Model.

Stores registered tools discovered from WordPress sites and other providers.
"""
from typing import Dict, Any, List, Optional
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
    """WordPress connection configuration"""

    id: str
    name: str
    wp_url: str
    wp_username: str
    wp_application_password: str
    enabled: bool = True
    last_discovery: Optional[datetime] = None
    discovery_method: Optional[str] = None  # "plugin" or "fallback"
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

