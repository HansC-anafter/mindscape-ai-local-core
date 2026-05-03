"""Selection resolution models for object runtime."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.models.object_runtime.catalog import ObjectAction
from backend.app.models.object_runtime.refs import (
    ObjectRef,
    ObjectSummary,
    _validate_object_selector_payload,
)


class SelectionBounds(BaseModel):
    """Optional element bounds for UI-originated selections."""

    model_config = ConfigDict(extra="forbid")

    x: float
    y: float
    w: float
    h: float


class SelectionElement(BaseModel):
    """Metadata about the selected UI element."""

    model_config = ConfigDict(extra="forbid")

    element_id: Optional[str] = None
    label: Optional[str] = None
    bounds: Optional[SelectionBounds] = None


class SelectionSurface(BaseModel):
    """Metadata about the surface that emitted the selection."""

    model_config = ConfigDict(extra="forbid")

    surface_type: str
    pack_code: Optional[str] = None
    surface_id: str
    route: Optional[str] = None


class SelectionHints(BaseModel):
    """Object-level hints supplied by the emitting surface."""

    model_config = ConfigDict(extra="forbid")

    owner_pack: Optional[str] = None
    object_kind: Optional[str] = None
    object_id: Optional[str] = None
    version: Optional[str] = None
    selector: Optional[Dict[str, Any]] = None
    source_surface: Optional[str] = None

    @field_validator("selector", mode="before")
    @classmethod
    def _validate_selector(cls, value: Any) -> Optional[Dict[str, Any]]:
        return _validate_object_selector_payload(value)


SelectionResolveMode = Literal[
    "resolve_only",
    "contextual_actions",
    "attach_to_meeting",
    "open_owner_surface",
]

ObjectMeetingAttachWriteMode = Literal[
    "proposal_only",
    "staged",
    "recommendation_only",
]

ObjectMaterializeWriteMode = Literal[
    "proposal_only",
    "staged",
    "recommendation_only",
    "canonical_with_review",
]

ObjectRuntimeRole = Literal[
    "source",
    "target",
    "baseline",
    "constraint",
    "evidence",
    "character",
    "output",
    "meeting",
    "session",
    "node",
]


class SelectionResolveRequest(BaseModel):
    """Selection resolution request payload."""

    model_config = ConfigDict(extra="forbid")

    selection_id: str
    surface: SelectionSurface
    element: Optional[SelectionElement] = None
    hints: Optional[SelectionHints] = None
    mode: SelectionResolveMode


class ResolvedSelectionObject(BaseModel):
    """Resolved object with runtime summary and actions."""

    model_config = ConfigDict(extra="forbid")

    ref: ObjectRef
    summary: ObjectSummary
    actions: List[ObjectAction] = Field(default_factory=list)


class SelectionCandidateObject(BaseModel):
    """Candidate object returned during disambiguation."""

    model_config = ConfigDict(extra="forbid")

    ref: ObjectRef
    summary: Optional[ObjectSummary] = None


class SelectionResolveError(BaseModel):
    """Structured warning or failure emitted by selection resolve."""

    model_config = ConfigDict(extra="forbid")

    code: str
    message: str


class SelectionResolveResponse(BaseModel):
    """Selection resolve result envelope."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    selection_id: str
    status: Literal["resolved", "ambiguous", "unresolved"]
    resolved_objects: List[ResolvedSelectionObject] = Field(default_factory=list)
    candidate_objects: List[SelectionCandidateObject] = Field(default_factory=list)
    errors: List[SelectionResolveError] = Field(default_factory=list)
