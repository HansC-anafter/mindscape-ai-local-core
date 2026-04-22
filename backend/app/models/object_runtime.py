"""Shared runtime transport models for the Addressable Object Layer."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class ObjectRef(BaseModel):
    """Stable transport identity for an addressable object."""

    model_config = ConfigDict(extra="forbid")

    uri: str
    owner_pack: str
    object_kind: str
    object_id: str
    workspace_id: Optional[str] = None
    version: Optional[str] = None
    selector: Optional[Dict[str, Any]] = None
    source_surface: Optional[str] = None


class ObjectSummary(BaseModel):
    """Bounded runtime summary for object-aware UI and meeting entry."""

    model_config = ConfigDict(extra="forbid")

    ref: ObjectRef
    title: str
    subtitle: Optional[str] = None
    summary_text: Optional[str] = None
    status: Optional[str] = None
    labels: List[str] = Field(default_factory=list)
    thumbnail_ref: Optional[str] = None
    owner_surface_url: Optional[str] = None
    updated_at: Optional[str] = None


class ObjectAction(BaseModel):
    """Contextual runtime action exposed for a resolved object."""

    model_config = ConfigDict(extra="forbid")

    action_code: str
    label: str
    description: str
    verb: str
    mode: str
    requires_review: bool = False
    target_kind: Optional[str] = None


class ObjectResolverCapabilities(BaseModel):
    """Resolver capability flags for one installed object kind."""

    model_config = ConfigDict(extra="forbid")

    summary: bool = False
    detail: bool = False
    relations: bool = False
    actions: bool = False


class ObjectMeetingProjectionCapabilities(BaseModel):
    """Meeting entry capability summary for one object kind."""

    model_config = ConfigDict(extra="forbid")

    available: bool = False
    verbs: List[str] = Field(default_factory=list)


class ObjectMaterializerCapabilities(BaseModel):
    """Materialization capability summary for one object kind."""

    model_config = ConfigDict(extra="forbid")

    available: bool = False
    verbs: List[str] = Field(default_factory=list)
    write_modes: List[str] = Field(default_factory=list)
    output_types: List[str] = Field(default_factory=list)


class ObjectGraphProjectionCapabilities(BaseModel):
    """Graph projection capability summary for one object kind."""

    model_config = ConfigDict(extra="forbid")

    available: bool = False
    node_kinds: List[str] = Field(default_factory=list)
    relation_kinds: List[str] = Field(default_factory=list)


class ObjectCatalogEntry(BaseModel):
    """Installed runtime object capability entry."""

    model_config = ConfigDict(extra="forbid")

    owner_pack: str
    object_kind: str
    display_name: str
    canonical_schema: Optional[str] = None
    id_field: str
    summary_fields: List[str] = Field(default_factory=list)
    supports: List[str] = Field(default_factory=list)
    resolver_capabilities: ObjectResolverCapabilities = Field(
        default_factory=ObjectResolverCapabilities
    )
    meeting_projection_capabilities: ObjectMeetingProjectionCapabilities = Field(
        default_factory=ObjectMeetingProjectionCapabilities
    )
    materializer_capabilities: ObjectMaterializerCapabilities = Field(
        default_factory=ObjectMaterializerCapabilities
    )
    graph_projection_capabilities: ObjectGraphProjectionCapabilities = Field(
        default_factory=ObjectGraphProjectionCapabilities
    )


class ObjectCatalogResponse(BaseModel):
    """Workspace-scoped object catalog response."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    catalog_version: str
    entries: List[ObjectCatalogEntry] = Field(default_factory=list)


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


class ObjectMeetingAttachRequest(BaseModel):
    """Request payload for turning object refs into bounded meeting attachments."""

    model_config = ConfigDict(extra="forbid")

    meeting_type: str
    meeting_id: Optional[str] = None
    objects: List[ObjectRef] = Field(min_length=1)
    target_ref: Optional[ObjectRef] = None
    intent_summary: str
    write_mode: ObjectMeetingAttachWriteMode = "proposal_only"


class MeetingAttachmentSummary(BaseModel):
    """Bounded meeting attachment summary returned by the runtime."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["source", "target", "baseline", "constraint", "evidence"]
    ref: ObjectRef
    projection_level: Literal["summary", "meeting"] = "meeting"


class ObjectMeetingAttachResponse(BaseModel):
    """Runtime response for meeting attachment requests."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    meeting_id: str
    status: Literal["attached", "materialized", "rejected"]
    attachments: List[MeetingAttachmentSummary] = Field(default_factory=list)
    target_ref: Optional[ObjectRef] = None
    staged_refs: List[ObjectRef] = Field(default_factory=list)
    review_routes: List[str] = Field(default_factory=list)
    errors: List[SelectionResolveError] = Field(default_factory=list)
