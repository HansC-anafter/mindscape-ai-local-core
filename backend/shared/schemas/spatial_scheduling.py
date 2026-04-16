"""
Spatial Scheduling Shared Contract

Provider-neutral actuation-planning envelope shared between local-core
meeting orchestration and downstream pack consumers.
"""

from __future__ import annotations

from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


SPATIAL_SCHEDULING_SCHEMA_VERSION = "2026-04-16"


def _new_schedule_id() -> str:
    return f"ssched_{uuid4().hex[:12]}"


class SpatialAnchor(BaseModel):
    anchor_id: str
    anchor_kind: str = Field("logical")
    label: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SpatialEntityRef(BaseModel):
    entity_id: str
    entity_kind: str = Field("task_phase")
    display_name: Optional[str] = None
    role: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SpatialScheduleSegment(BaseModel):
    segment_id: str
    order: int = Field(ge=0)
    title: str
    description: Optional[str] = None
    intent_id: Optional[str] = None
    entity_refs: list[str] = Field(default_factory=list)
    intent_tags: list[str] = Field(default_factory=list)
    anchors: list[str] = Field(default_factory=list)
    motion_constraint_objects: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SpatialSchedulingIR(BaseModel):
    schedule_id: str = Field(default_factory=_new_schedule_id)
    schema_version: str = Field(default=SPATIAL_SCHEDULING_SCHEMA_VERSION)
    workspace_id: str
    source: str = Field("meeting")
    status: str = Field("planned")
    title: Optional[str] = None
    decision: Optional[str] = None
    entities: list[SpatialEntityRef] = Field(default_factory=list)
    anchors: list[SpatialAnchor] = Field(default_factory=list)
    segments: list[SpatialScheduleSegment] = Field(default_factory=list)
    consumer_hints: list[str] = Field(default_factory=list)
    constraint_summary: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "SPATIAL_SCHEDULING_SCHEMA_VERSION",
    "SpatialAnchor",
    "SpatialEntityRef",
    "SpatialScheduleSegment",
    "SpatialSchedulingIR",
]
