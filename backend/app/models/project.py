"""
Project model for workspace-based project container

A Project represents a specific work item within a Workspace - a concrete deliverable
such as a web page, book, course, or campaign. Each Project has its own lifecycle,
sandbox, and flow execution context.

Key characteristics:
- Belongs to a Workspace (home_workspace_id)
- Has a specific type (web_page, book, course, campaign, etc.)
- Has its own state lifecycle (open, closed, archived)
- Maintains ownership information (initiator, human owner, AI PM)
- References a Playbook Flow for execution orchestration
"""

from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class Project(BaseModel):
    """
    Project model - workspace-based project container

    A Project is a concrete work item within a Workspace that represents
    a deliverable or campaign. Projects have their own sandbox, flow execution,
    and lifecycle management.
    """

    id: str = Field(..., description="Unique project identifier")
    type: str = Field(..., description="Project type: web_page, book, course, campaign, video_series")
    title: str = Field(..., description="Project title")
    home_workspace_id: str = Field(..., description="Home workspace ID")
    flow_id: str = Field(..., description="Playbook flow ID")
    state: str = Field(default="open", description="Project state: open, closed, archived")

    # Three ownership roles
    initiator_user_id: str = Field(..., description="User who initiated this project")
    human_owner_user_id: Optional[str] = Field(None, description="Human PM user ID")
    ai_pm_id: Optional[str] = Field(None, description="AI team PM ID")

    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional project metadata")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ProjectSuggestion(BaseModel):
    """
    Project suggestion from detector

    Used when ProjectDetector detects that a conversation might
    require creating a new Project.
    """

    mode: str = Field(..., description="Mode: quick_task, micro_flow, project")
    project_type: Optional[str] = Field(None, description="Project type if mode is project")
    project_title: Optional[str] = Field(None, description="Project title if mode is project")
    flow_id: Optional[str] = Field(None, description="Flow ID if mode is project")
    initial_spec_md: Optional[str] = Field(None, description="Initial specification in markdown")
    confidence: Optional[float] = Field(None, description="Confidence score (0.0-1.0)")


class ProjectAssignmentOutput(BaseModel):
    """
    Project assignment suggestion output

    Used by ProjectAssignmentAgent to suggest human owner and AI PM.
    """

    suggested_human_owner: Optional[Dict[str, Any]] = Field(None, description="Suggested human owner")
    suggested_ai_pm_id: Optional[str] = Field(None, description="Suggested AI PM ID")
    reasoning: Optional[str] = Field(None, description="Reasoning for assignment")

