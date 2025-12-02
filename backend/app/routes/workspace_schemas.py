"""
Workspace API Response Schemas

Pydantic models for workspace API responses.
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class EventsListResponse(BaseModel):
    """Response model for workspace events list"""
    workspace_id: str = Field(..., description="Workspace ID")
    total: int = Field(..., description="Total number of events returned")
    events: List[Dict[str, Any]] = Field(..., description="List of event objects")
    has_more: bool = Field(..., description="Whether there are more events available")


class TimelineListResponse(BaseModel):
    """Response model for workspace timeline list"""
    workspace_id: str = Field(..., description="Workspace ID")
    total: int = Field(..., description="Total number of timeline items returned")
    timeline_items: List[Dict[str, Any]] = Field(..., description="List of timeline item objects")
    events: List[Dict[str, Any]] = Field(..., description="List of event objects (same as timeline_items)")


class ArtifactResponse(BaseModel):
    """Artifact response schema"""
    id: str
    workspace_id: str
    intent_id: Optional[str]
    task_id: Optional[str]
    execution_id: Optional[str]
    playbook_code: str
    artifact_type: str
    title: str
    summary: str
    content: Dict[str, Any]
    storage_ref: Optional[str]
    sync_state: Optional[str]
    primary_action_type: str
    metadata: Optional[Dict[str, Any]]
    created_at: Optional[str]
    updated_at: Optional[str]


class ArtifactsListResponse(BaseModel):
    """Artifacts list response schema"""
    workspace_id: str
    total: int
    artifacts: List[ArtifactResponse]

