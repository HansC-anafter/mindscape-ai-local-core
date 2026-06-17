from typing import List, Optional

from pydantic import BaseModel

from ..models.graph import LensNodeState


class SetWorkspaceOverrideRequest(BaseModel):
    """Request to set workspace override"""

    state: LensNodeState


class SetSessionOverrideRequest(BaseModel):
    """Request to set session override"""

    state: LensNodeState


class ChatRequest(BaseModel):
    """Request for Mind-Lens chat"""

    mode: str  # 'mirror' | 'experiment' | 'writeback'
    message: str
    profile_id: str
    workspace_id: Optional[str] = None
    session_id: Optional[str] = None
    effective_lens: Optional[dict] = None
    selected_node_ids: Optional[List[str]] = None


class ChatResponse(BaseModel):
    """Response from Mind-Lens chat"""

    response: str
    mode: str
    suggestions: Optional[List[str]] = None


class PresetSnapshotRequest(BaseModel):
    """Request to create a preset snapshot"""

    profile_id: str
    name: str
    workspace_id: Optional[str] = None
    session_id: Optional[str] = None
    description: Optional[str] = None
