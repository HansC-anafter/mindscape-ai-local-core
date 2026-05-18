
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

class ArtifactResponse(BaseModel):
    """Artifact API response model matching the API draft specification"""

    id: str
    workspace_id: str
    intent_id: Optional[str] = None
    type: str  # 'illustration' | 'document' | 'other'
    title: str
    description: Optional[str] = None
    file_path: Optional[str] = None
    external_url: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str
    task_id: Optional[str] = None
    execution_id: Optional[str] = None  # Add execution_id
    thread_id: Optional[str] = None
    playbook_code: Optional[str] = None
    artifact_type: Optional[str] = None
    content: Optional[Dict[str, Any]] = None
    content_preview: Optional[str] = None
    platform: Optional[str] = None

    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})


class CreateArtifactRequest(BaseModel):
    """Request model for creating a new artifact"""

    workspace_id: str
    intent_id: Optional[str] = None
    type: str  # 'illustration' | 'document' | 'other'
    title: str
    description: Optional[str] = None
    file_path: Optional[str] = None
    external_url: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CreateArtifactReviewDecisionRequest(BaseModel):
    decision: str
    reviewer_id: Optional[str] = None
    notes: Optional[str] = None
    checklist_scores: Dict[str, Any] = Field(default_factory=dict)
    followup_actions: List[str] = Field(default_factory=list)


class UpdateArtifactFollowupRequestStateRequest(BaseModel):
    request_state: str
    actor_id: Optional[str] = None
    notes: Optional[str] = None
    execution_ref: Dict[str, Any] = Field(default_factory=dict)


class DispatchArtifactFollowupRequest(BaseModel):
    actor_id: Optional[str] = None
    notes: Optional[str] = None


class ListArtifactsResponse(BaseModel):
    """Response model for listing artifacts"""

    artifacts: List[ArtifactResponse]
    total: Optional[int] = None
    limit: Optional[int] = None
    offset: Optional[int] = None
