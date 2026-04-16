from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class WorldStateSnapshot(BaseModel):
    snapshot_id: str = Field(..., description="Unique snapshot identifier")
    workspace_id: str = Field(..., description="Workspace identifier")
    profile_id: Optional[str] = Field(None, description="Profile identifier")
    project_id: Optional[str] = Field(None, description="Project identifier")
    source: str = Field("synthetic", description="Receipt source family")
    captured_at: datetime = Field(default_factory=_utc_now)
    scene_id: Optional[str] = Field(None, description="Current scene or world identifier")
    current_zone: Optional[str] = Field(None, description="Current logical zone")
    visible_objects: List[str] = Field(default_factory=list)
    reachable_zones: List[str] = Field(default_factory=list)
    resource_constraints: Dict[str, Any] = Field(default_factory=dict)
    environment_state: Dict[str, Any] = Field(default_factory=dict)
    performer_state: Dict[str, Any] = Field(default_factory=dict)
    active_motion: Optional[Dict[str, Any]] = Field(None)
    motion_artifact_refs: List[Dict[str, Any]] = Field(default_factory=list)
    motion_constraints: Dict[str, Any] = Field(default_factory=dict)
    active_schedule: Optional[Dict[str, Any]] = Field(None)
    schedule_artifact_refs: List[Dict[str, Any]] = Field(default_factory=list)
    schedule_constraints: Dict[str, Any] = Field(default_factory=dict)
    geo_anchor: Optional[Dict[str, Any]] = Field(None)
    venue_context: Optional[Dict[str, Any]] = Field(None)
    route_context: Optional[Dict[str, Any]] = Field(None)
    streetview_context: Optional[Dict[str, Any]] = Field(None)
    metadata: Dict[str, Any] = Field(default_factory=dict)
