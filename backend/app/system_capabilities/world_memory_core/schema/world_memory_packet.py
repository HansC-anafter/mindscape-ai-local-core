from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class WorldMemoryPacket(BaseModel):
    workspace_id: str = Field(..., description="Workspace identifier")
    snapshot_id: str = Field(..., description="World snapshot identifier")
    source: str = Field(..., description="Receipt source family")
    scene_id: Optional[str] = Field(None)
    current_zone: Optional[str] = Field(None)
    visible_objects: List[str] = Field(default_factory=list)
    reachable_zones: List[str] = Field(default_factory=list)
    resource_constraints: Dict[str, Any] = Field(default_factory=dict)
    environment_state: Dict[str, Any] = Field(default_factory=dict)
    performer_state: Dict[str, Any] = Field(default_factory=dict)
    active_motion: Optional[Dict[str, Any]] = Field(None)
    motion_artifact_refs: List[Dict[str, Any]] = Field(default_factory=list)
    motion_constraints: Dict[str, Any] = Field(default_factory=dict)
    performance_state: Dict[str, Any] = Field(default_factory=dict)
    geo_anchor: Optional[Dict[str, Any]] = Field(None)
    venue_context: Optional[Dict[str, Any]] = Field(None)
    route_context: Optional[Dict[str, Any]] = Field(None)
    streetview_context: Optional[Dict[str, Any]] = Field(None)
    metadata: Dict[str, Any] = Field(default_factory=dict)
