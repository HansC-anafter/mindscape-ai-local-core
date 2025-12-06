"""
Workspace Resource Binding Models
Defines workspace overlay layer for shared resources

Supports binding shared resources (playbooks, tools, data sources) to workspaces
with local overrides (display name, order, enabled status, etc.).
"""

from datetime import datetime
from typing import Optional, Dict, Any, Literal
from enum import Enum
from pydantic import BaseModel, Field


class ResourceType(str, Enum):
    """Resource types supported by workspace binding"""
    PLAYBOOK = "playbook"
    TOOL = "tool"
    DATA_SOURCE = "data_source"


class AccessMode(str, Enum):
    """Access mode for resource binding"""
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"


class WorkspaceResourceBinding(BaseModel):
    """
    Workspace Resource Binding

    Represents how a workspace uses a shared resource with local overrides.
    This is the overlay layer that allows workspace-specific customization
    without modifying the shared resource itself.

    Phase 1: Supports three resource types: playbook, tool, data_source
    """
    id: str = Field(..., description="Unique binding ID")
    workspace_id: str = Field(..., description="Workspace ID")
    resource_type: ResourceType = Field(..., description="Resource type: playbook, tool, or data_source")
    resource_id: str = Field(..., description="Resource ID (playbook_code, tool_id, or data_source_id)")

    # Access control
    access_mode: AccessMode = Field(
        default=AccessMode.READ,
        description="Access mode: read, write, or admin"
    )

    # Local overrides (JSON, only local-related settings)
    overrides: Dict[str, Any] = Field(
        default_factory=dict,
        description="Local overrides: display_name, order, category, default_params, enabled, etc."
    )

    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class CreateWorkspaceResourceBindingRequest(BaseModel):
    """Request to create a workspace resource binding"""
    workspace_id: str
    resource_type: ResourceType
    resource_id: str
    access_mode: AccessMode = AccessMode.READ
    overrides: Dict[str, Any] = Field(default_factory=dict)


class UpdateWorkspaceResourceBindingRequest(BaseModel):
    """Request to update a workspace resource binding"""
    access_mode: Optional[AccessMode] = None
    overrides: Optional[Dict[str, Any]] = None


# Override schemas for different resource types

class PlaybookOverrides(BaseModel):
    """Playbook-specific overrides"""
    local_display_name: Optional[str] = Field(None, description="Local display name (e.g., '寫書模式')")
    local_order: Optional[int] = Field(None, description="Local sort order")
    local_category: Optional[str] = Field(None, description="Local category")
    local_default_params: Optional[Dict[str, Any]] = Field(None, description="Default parameters for this workspace")
    local_enabled: Optional[bool] = Field(None, description="Whether playbook is enabled in this workspace")


class ToolOverrides(BaseModel):
    """Tool-specific overrides"""
    local_tool_whitelist: Optional[list[str]] = Field(None, description="List of allowed tool IDs")
    local_danger_overrides: Optional[Dict[str, str]] = Field(
        None,
        description="Danger level overrides (can only be more restrictive, not less)"
    )
    local_enabled: Optional[bool] = Field(None, description="Whether tool is enabled in this workspace")


class DataSourceOverrides(BaseModel):
    """Data source-specific overrides"""
    local_display_name: Optional[str] = Field(None, description="Local display name")
    local_access_mode: Optional[str] = Field(None, description="Local access mode override")
    local_enabled: Optional[bool] = Field(None, description="Whether data source is enabled in this workspace")

