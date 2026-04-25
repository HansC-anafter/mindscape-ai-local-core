"""Shared runtime transport models for the Addressable Object Layer."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


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

ObjectMaterializeWriteMode = Literal[
    "proposal_only",
    "staged",
    "recommendation_only",
    "canonical_with_review",
]

ObjectRuntimeRole = Literal["source", "target", "baseline", "constraint", "evidence"]


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


class ObjectRoleEntry(BaseModel):
    """Role-bearing object context entry for attach and materialize transport."""

    model_config = ConfigDict(extra="forbid")

    role: ObjectRuntimeRole
    ref: ObjectRef


class ObjectMeetingAttachRequest(BaseModel):
    """Request payload for turning object refs into bounded meeting attachments."""

    model_config = ConfigDict(extra="forbid")

    meeting_type: str
    meeting_id: Optional[str] = None
    entries: List[ObjectRoleEntry] = Field(min_length=1)
    intent_summary: str
    write_mode: ObjectMeetingAttachWriteMode = "proposal_only"

    @model_validator(mode="before")
    @classmethod
    def _coerce_legacy_payload(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value

        payload = dict(value)
        raw_entries = payload.get("entries")
        legacy_objects = payload.pop("objects", None)
        legacy_target_ref = payload.pop("target_ref", None)

        normalized_entries: List[Any] = []
        if isinstance(raw_entries, list):
            normalized_entries.extend(raw_entries)
        if isinstance(legacy_objects, list):
            normalized_entries.extend(
                {"role": "source", "ref": raw_object} for raw_object in legacy_objects
            )
        if legacy_target_ref is not None:
            normalized_entries.append({"role": "target", "ref": legacy_target_ref})

        if normalized_entries:
            payload["entries"] = normalized_entries
        return payload

    @property
    def target_ref(self) -> Optional[ObjectRef]:
        for entry in self.entries:
            if entry.role == "target":
                return entry.ref
        return None

    @property
    def source_objects(self) -> List[ObjectRef]:
        return [entry.ref for entry in self.entries if entry.role == "source"]


class MeetingAttachmentSummary(BaseModel):
    """Bounded meeting attachment summary returned by the runtime."""

    model_config = ConfigDict(extra="forbid")

    role: ObjectRuntimeRole
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


class ObjectMaterializeRequest(BaseModel):
    """Request payload for generic runtime review/promote materialization."""

    model_config = ConfigDict(extra="forbid")

    object_ref: ObjectRef
    verb: str
    intent_summary: str
    meeting_id: Optional[str] = None
    write_mode: ObjectMaterializeWriteMode = "staged"
    context_entries: List[ObjectRoleEntry] = Field(default_factory=list)
    request_context: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _coerce_legacy_context_objects(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value

        payload = dict(value)
        raw_entries = payload.get("context_entries")
        legacy_objects = payload.pop("context_objects", None)

        normalized_entries: List[Any] = []
        if isinstance(raw_entries, list):
            normalized_entries.extend(raw_entries)
        if isinstance(legacy_objects, list):
            normalized_entries.extend(
                {"role": "source", "ref": raw_object} for raw_object in legacy_objects
            )

        if normalized_entries:
            payload["context_entries"] = normalized_entries
        return payload


class ObjectMaterializeResponse(BaseModel):
    """Runtime response for generic object materialization requests."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    status: Literal["planned", "materialized", "rejected"]
    verb: str
    object_ref: ObjectRef
    staged_refs: List[ObjectRef] = Field(default_factory=list)
    review_routes: List[str] = Field(default_factory=list)
    canonical_routes: List[str] = Field(default_factory=list)
    request_plan: Optional[Dict[str, Any]] = None
    errors: List[SelectionResolveError] = Field(default_factory=list)


class ObjectGraphRelation(BaseModel):
    """Normalized runtime graph relation between addressable objects."""

    model_config = ConfigDict(extra="forbid")

    relation_kind: str
    direction: Literal["outbound", "inbound", "bidirectional"] = "outbound"
    target_ref: ObjectRef
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ObjectGraphProjection(BaseModel):
    """Normalized runtime graph projection for one resolved object."""

    model_config = ConfigDict(extra="forbid")

    ref: ObjectRef
    summary: Optional[ObjectSummary] = None
    node_kind: Optional[str] = None
    relations: List[ObjectGraphRelation] = Field(default_factory=list)
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
