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
SPATIAL_CONSTRAINT_SECTION_KEYS = (
    "scene",
    "camera",
    "objects",
    "anchors",
    "spatial_relations",
    "occlusion",
    "displacement",
    "output_boundaries",
)


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


class SpatialConstraintItem(BaseModel):
    item_id: str
    label: Optional[str] = None
    summary: str
    anchor_ids: list[str] = Field(default_factory=list)
    entity_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SpatialConsumerPromptSegment(BaseModel):
    text: str = Field(..., description="Consumer-facing prompt segment text")
    consumer: str = Field(
        "generic",
        description="Neutral downstream consumer identifier",
    )
    role: str = Field(
        "instruction",
        description="Prompt role such as instruction, style, safety, or negative",
    )
    section_keys: list[str] = Field(
        default_factory=list,
        description="Constraint-summary sections this prompt segment is grounded to",
    )
    constraint_item_ids: list[str] = Field(
        default_factory=list,
        description="Bounded constraint items this prompt segment depends on",
    )
    segment_ids: list[str] = Field(
        default_factory=list,
        description="Schedule segment identifiers this prompt segment applies to",
    )
    anchor_ids: list[str] = Field(
        default_factory=list,
        description="Anchor identifiers this prompt segment is bound to",
    )
    entity_refs: list[str] = Field(
        default_factory=list,
        description="Entities this prompt segment references",
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


class SpatialConstraintSummary(BaseModel):
    scene: list[SpatialConstraintItem] = Field(default_factory=list)
    camera: list[SpatialConstraintItem] = Field(default_factory=list)
    objects: list[SpatialConstraintItem] = Field(default_factory=list)
    anchors: list[SpatialConstraintItem] = Field(default_factory=list)
    spatial_relations: list[SpatialConstraintItem] = Field(default_factory=list)
    occlusion: list[SpatialConstraintItem] = Field(default_factory=list)
    displacement: list[SpatialConstraintItem] = Field(default_factory=list)
    output_boundaries: list[SpatialConstraintItem] = Field(default_factory=list)
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
    consumer_prompt_segments: list[SpatialConsumerPromptSegment] = Field(
        default_factory=list
    )
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
    constraint_summary: SpatialConstraintSummary = Field(
        default_factory=SpatialConstraintSummary
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "SPATIAL_CONSTRAINT_SECTION_KEYS",
    "SPATIAL_SCHEDULING_SCHEMA_VERSION",
    "SpatialAnchor",
    "SpatialConstraintItem",
    "SpatialConsumerPromptSegment",
    "SpatialConstraintSummary",
    "SpatialEntityRef",
    "SpatialScheduleSegment",
    "SpatialSchedulingIR",
]
