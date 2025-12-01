"""
AI Role Configuration Models
Defines persistent storage for user's AI role selections and configurations
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class AIRoleConfig(BaseModel):
    """
    AI Role configuration - persisted user selections

    This model stores which AI roles a user has enabled and how they've configured them.
    Used for configuration backup and template export.
    """
    id: str = Field(..., description="Role ID (e.g., 'product_designer')")
    profile_id: str = Field(..., description="Associated profile ID")

    # Basic information
    name: str = Field(..., description="Role display name")
    description: str = Field(..., description="Role description")
    agent_type: str = Field(..., description="Agent type: planner, writer, coach, coder")
    icon: str = Field(default="🤖", description="Role icon emoji")

    # Capability configuration
    playbooks: List[str] = Field(
        default_factory=list,
        description="Associated playbook codes"
    )
    suggested_tasks: List[str] = Field(
        default_factory=list,
        description="Suggested tasks for this role"
    )
    tools: List[str] = Field(
        default_factory=list,
        description="Associated tool IDs (e.g., ['wordpress', 'notion'])"
    )

    # Mindscape profile override (role-specific adjustments)
    mindscape_profile_override: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Profile overrides when this role is active (e.g., specific domains, preferences)"
    )

    # Usage statistics
    usage_count: int = Field(default=0, description="Number of times this role was used")
    last_used_at: Optional[datetime] = None

    # Status
    is_enabled: bool = Field(default=True, description="Whether role is active")
    is_custom: bool = Field(default=False, description="Whether this is a user-created custom role")

    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Extension point for platform-specific data
    x_platform: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Platform-specific metadata (optional, can be used by extensions)"
    )

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class CreateAIRoleRequest(BaseModel):
    """Request to create or enable an AI role"""
    role_id: str = Field(..., description="Role ID (e.g., 'product_designer')")
    name: str
    description: str
    agent_type: str
    icon: str = "🤖"
    playbooks: List[str] = Field(default_factory=list)
    suggested_tasks: List[str] = Field(default_factory=list)
    tools: List[str] = Field(default_factory=list)
    mindscape_profile_override: Optional[Dict[str, Any]] = None
    is_custom: bool = False


class UpdateAIRoleRequest(BaseModel):
    """Request to update an AI role configuration"""
    name: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    playbooks: Optional[List[str]] = None
    suggested_tasks: Optional[List[str]] = None
    tools: Optional[List[str]] = None
    mindscape_profile_override: Optional[Dict[str, Any]] = None
    is_enabled: Optional[bool] = None


class AIRoleUsageRecord(BaseModel):
    """Record of AI role usage"""
    role_id: str
    profile_id: str
    execution_id: str
    task: str
    used_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
