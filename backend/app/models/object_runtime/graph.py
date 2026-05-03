"""Object graph projection models."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from backend.app.models.object_runtime.refs import ObjectRef, ObjectSummary
from backend.app.models.object_runtime.selection import SelectionResolveError


class ObjectGraphRelation(BaseModel):
    """Normalized runtime graph relation between addressable objects."""

    model_config = ConfigDict(extra="forbid")

    relation_kind: str
    direction: Literal["outbound", "inbound", "bidirectional"] = "outbound"
    target_ref: ObjectRef
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ObjectGuidanceCard(BaseModel):
    """Pack-projected next-step guidance for a bounded object graph."""

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    description: Optional[str] = None
    intent: Optional[str] = None
    command_template: Optional[str] = None
    review_label: Optional[str] = None
    review_routes: List[str] = Field(default_factory=list)
    proposal_ref: Optional[ObjectRef] = None
    target_ref: Optional[ObjectRef] = None
    required_roles: List[str] = Field(default_factory=list)
    priority: int = 100
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ObjectGraphProjection(BaseModel):
    """Normalized runtime graph projection for one resolved object."""

    model_config = ConfigDict(extra="forbid")

    ref: ObjectRef
    summary: Optional[ObjectSummary] = None
    node_kind: Optional[str] = None
    relations: List[ObjectGraphRelation] = Field(default_factory=list)
    guidance: List[ObjectGuidanceCard] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ObjectGraphProjectRequest(BaseModel):
    """Request payload for bounded runtime graph projection."""

    model_config = ConfigDict(extra="forbid")

    objects: List[ObjectRef] = Field(min_length=1)
    include_relations: bool = True
    include_summaries: bool = True


class ObjectGraphProjectResponse(BaseModel):
    """Runtime response for bounded object graph projection requests."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    projections: List[ObjectGraphProjection] = Field(default_factory=list)
    errors: List[SelectionResolveError] = Field(default_factory=list)
