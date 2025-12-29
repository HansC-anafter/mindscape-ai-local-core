"""
ChangeSet models for Mind-Lens unified implementation.

ChangeSet represents a collection of node state changes that can be applied
to different scopes (session, workspace, or preset).
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from datetime import datetime, timezone
from enum import Enum

from .graph import LensNodeState


class NodeChange(BaseModel):
    """Single node state change"""
    node_id: str
    node_label: str
    from_state: LensNodeState
    to_state: LensNodeState

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class ApplyTarget(str, Enum):
    """ChangeSet apply target"""
    SESSION_ONLY = "session_only"
    WORKSPACE = "workspace"
    PRESET = "preset"


class ChangeSet(BaseModel):
    """Change set for lens node state changes"""
    id: str
    profile_id: str
    session_id: str
    workspace_id: Optional[str]
    changes: List[NodeChange]
    summary: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class ChangeSetCreateRequest(BaseModel):
    """Request to create changeset"""
    session_id: str
    workspace_id: Optional[str] = None
    profile_id: str


class ChangeSetApplyRequest(BaseModel):
    """Request to apply changeset"""
    changeset: ChangeSet
    apply_to: ApplyTarget
    target_workspace_id: Optional[str] = None

