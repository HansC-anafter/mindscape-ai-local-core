"""Shared runtime transport models for the Addressable Object Layer."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


ObjectSelectorFamily = Literal[
    "object_root",
    "dom_anchor",
    "image_region",
    "media_time_range",
    "storyboard_scene",
    "storyboard_slot",
    "timeline_clip",
    "pack_local_path",
    "graph_node",
]


class ObjectSelectorRegion(BaseModel):
    """Normalized rectangular selector bounds for visual and canvas objects."""

    model_config = ConfigDict(extra="forbid")

    x: float
    y: float
    w: float
    h: float

    @model_validator(mode="after")
    def _validate_size(self) -> "ObjectSelectorRegion":
        if self.w <= 0 or self.h <= 0:
            raise ValueError("selector region width and height must be positive")
        return self


class ObjectSelector(BaseModel):
    """Typed sub-object selector used by AOL runtime payloads.

    Existing legacy selector dictionaries remain accepted by ObjectRef and
    SelectionHints when they do not declare selector_type.
    """

    model_config = ConfigDict(extra="forbid")

    selector_type: ObjectSelectorFamily
    surface_id: Optional[str] = None
    element_id: Optional[str] = None
    dom_id: Optional[str] = None
    css_selector: Optional[str] = None
    xpath: Optional[str] = None
    region: Optional[ObjectSelectorRegion] = None
    time_start_seconds: Optional[float] = None
    time_end_seconds: Optional[float] = None
    scene_id: Optional[str] = None
    slot_id: Optional[str] = None
    clip_id: Optional[str] = None
    path: Optional[str] = None
    node_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_selector_family_payload(self) -> "ObjectSelector":
        if self.selector_type == "dom_anchor" and not any(
            [self.dom_id, self.css_selector, self.xpath, self.element_id]
        ):
            raise ValueError(
                "dom_anchor selectors require dom_id, css_selector, xpath, or element_id"
            )
        if self.selector_type == "image_region" and self.region is None:
            raise ValueError("image_region selectors require region")
        if self.selector_type == "media_time_range":
            if self.time_start_seconds is None or self.time_end_seconds is None:
                raise ValueError(
                    "media_time_range selectors require time_start_seconds and time_end_seconds"
                )
            if self.time_start_seconds < 0 or self.time_end_seconds < 0:
                raise ValueError("media_time_range selector times must be non-negative")
            if self.time_end_seconds < self.time_start_seconds:
                raise ValueError(
                    "media_time_range selector end must be greater than or equal to start"
                )
        if self.selector_type == "storyboard_scene" and not self.scene_id:
            raise ValueError("storyboard_scene selectors require scene_id")
        if self.selector_type == "storyboard_slot" and not self.slot_id:
            raise ValueError("storyboard_slot selectors require slot_id")
        if self.selector_type == "timeline_clip" and not self.clip_id:
            raise ValueError("timeline_clip selectors require clip_id")
        if self.selector_type == "pack_local_path" and not self.path:
            raise ValueError("pack_local_path selectors require path")
        if self.selector_type == "graph_node" and not self.node_id:
            raise ValueError("graph_node selectors require node_id")
        return self


def _validate_object_selector_payload(value: Any) -> Optional[Dict[str, Any]]:
    """Validate typed selector payloads without rewriting legacy selectors."""

    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("selector must be an object")
    if "selector_type" not in value:
        return value
    return ObjectSelector.model_validate(value).model_dump(exclude_none=True)


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

    @field_validator("selector", mode="before")
    @classmethod
    def _validate_selector(cls, value: Any) -> Optional[Dict[str, Any]]:
        return _validate_object_selector_payload(value)


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


class ObjectAffordanceCapability(BaseModel):
    """Callable object affordance declared by an installed pack."""

    model_config = ConfigDict(extra="forbid")

    verb: str
    label: Optional[str] = None
    description: Optional[str] = None
    object_kinds: List[str] = Field(default_factory=list)
    input_schema: Dict[str, Any] = Field(default_factory=dict)
    output_schema: Dict[str, Any] = Field(default_factory=dict)
    required_roles: List[str] = Field(default_factory=list)
    write_modes: List[str] = Field(default_factory=list)
    planner_backend: str
    executor_backend: Optional[str] = None


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
    granularity: Optional[str] = None
    selector_families: List[ObjectSelectorFamily] = Field(default_factory=list)
    indexer_backend: Optional[str] = None
    mention_fields: List[str] = Field(default_factory=list)
    owner_surface_patterns: List[str] = Field(default_factory=list)
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
    affordances: List[ObjectAffordanceCapability] = Field(default_factory=list)


class ObjectCatalogResponse(BaseModel):
    """Workspace-scoped object catalog response."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    catalog_version: str
    entries: List[ObjectCatalogEntry] = Field(default_factory=list)


class ObjectInstanceRecord(BaseModel):
    """Workspace-scoped searchable read-model row for a concrete object."""

    model_config = ConfigDict(extra="forbid")

    ref: ObjectRef
    title: str
    subtitle: Optional[str] = None
    summary_text: Optional[str] = None
    labels: List[str] = Field(default_factory=list)
    thumbnail_ref: Optional[str] = None
    owner_surface_url: Optional[str] = None
    mention_tokens: List[str] = Field(default_factory=list)
    mention_text: str = ""
    search_text: str = ""
    affordance_verbs: List[str] = Field(default_factory=list)
    stale: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)
    updated_at: Optional[str] = None


class ObjectInstanceIndexRequest(BaseModel):
    """Batch index request from an owner-pack object indexer."""

    model_config = ConfigDict(extra="forbid")

    source: Optional[str] = None
    records: List[ObjectInstanceRecord] = Field(default_factory=list)


class ObjectInstanceIndexResponse(BaseModel):
    """Batch index write result."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    indexed_count: int


class ObjectInstanceSyncRequest(BaseModel):
    """Workspace-scoped indexer discovery/sync request."""

    model_config = ConfigDict(extra="forbid")

    owner_pack: Optional[str] = None
    object_kind: Optional[str] = None
    limit: int = Field(default=100, ge=1, le=500)
    force: bool = False
    reason: Optional[str] = None


class ObjectInstanceSyncSourceResult(BaseModel):
    """Per catalog-indexer sync outcome."""

    model_config = ConfigDict(extra="forbid")

    owner_pack: str
    object_kind: str
    indexer_backend: str
    indexed_count: int = 0
    status: Literal["synced", "skipped", "failed"] = "synced"
    message: Optional[str] = None


class ObjectInstanceSyncResponse(BaseModel):
    """Object instance sync result across discovered owner-pack indexers."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    indexed_count: int
    sources: List[ObjectInstanceSyncSourceResult] = Field(default_factory=list)


class ObjectSearchResponse(BaseModel):
    """Concrete object instance search response."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    query: str
    results: List[ObjectInstanceRecord] = Field(default_factory=list)


class ObjectReadRequest(BaseModel):
    """Read a concrete workspace object instance from a stable ObjectRef."""

    model_config = ConfigDict(extra="forbid")

    object_ref: Dict[str, Any]


class ObjectReadResponse(BaseModel):
    """Workspace-scoped read response for a concrete object instance."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    object: ObjectInstanceRecord


class ObjectMentionCompletionItem(BaseModel):
    """Command-bar mention completion item backed by the object index."""

    model_config = ConfigDict(extra="forbid")

    id: str
    token: str
    label: str
    description: str
    ref: ObjectRef
    owner_pack: str
    object_kind: str
    score: float = 0.0
    source: str = "object_instance_registry"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ObjectMentionCompletionResponse(BaseModel):
    """Mention completion response for the meeting command bar."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    query: str
    results: List[ObjectMentionCompletionItem] = Field(default_factory=list)


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


class ObjectActionPlanRequest(BaseModel):
    """Request payload for planning a schema-backed object affordance."""

    model_config = ConfigDict(extra="forbid")

    instruction: str
    entries: List[ObjectRoleEntry] = Field(min_length=1)
    affordance_verb: Optional[str] = None
    write_mode: Optional[ObjectMaterializeWriteMode] = None
    meeting_id: Optional[str] = None
    request_context: Dict[str, Any] = Field(default_factory=dict)


class ObjectActionPlanResponse(BaseModel):
    """Structured plan for invoking an object affordance."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    status: Literal["planned", "needs_disambiguation", "unsupported", "rejected"]
    selected_affordance: Optional[ObjectAffordanceCapability] = None
    role_assignments: List[ObjectRoleEntry] = Field(default_factory=list)
    missing_roles: List[str] = Field(default_factory=list)
    write_mode: Optional[str] = None
    request_plan: Optional[Dict[str, Any]] = None
    errors: List[SelectionResolveError] = Field(default_factory=list)


class ObjectActionInvokeRequest(BaseModel):
    """Invoke a planned schema-backed object affordance."""

    model_config = ConfigDict(extra="forbid")

    instruction: str
    object_action_plan: Dict[str, Any]
    entries: List[ObjectRoleEntry] = Field(default_factory=list)
    meeting_id: Optional[str] = None
    thread_id: Optional[str] = None
    execution_id: Optional[str] = None
    request_context: Dict[str, Any] = Field(default_factory=dict)


class ObjectActionInvokeResponse(BaseModel):
    """Result of invoking an object affordance and closing addressable outputs."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    status: Literal["succeeded", "failed", "skipped"]
    action_plan_id: str
    execution_id: str
    task_id: str
    closure: Optional[Dict[str, Any]] = None
    executor_result: Dict[str, Any] = Field(default_factory=dict)
    errors: List[SelectionResolveError] = Field(default_factory=list)


class ObjectRelationRecord(BaseModel):
    """Durable relation/provenance edge between two addressable objects."""

    model_config = ConfigDict(extra="forbid")

    relation_id: Optional[str] = None
    workspace_id: Optional[str] = None
    source_ref: ObjectRef
    relation_kind: str = Field(min_length=1)
    target_ref: ObjectRef
    source_role: Optional[str] = None
    target_role: Optional[str] = None
    provenance_type: Optional[str] = None
    provenance_id: Optional[str] = None
    meeting_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ObjectRelationIndexRequest(BaseModel):
    """Batch write request for object relation/provenance edges."""

    model_config = ConfigDict(extra="forbid")

    source: Optional[str] = None
    relations: List[ObjectRelationRecord] = Field(default_factory=list)


class ObjectRelationIndexResponse(BaseModel):
    """Batch relation write result."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    indexed_count: int


class ObjectRelationSearchResponse(BaseModel):
    """Workspace-scoped relation lookup response."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    results: List[ObjectRelationRecord] = Field(default_factory=list)


class ObjectActionClosureRequest(BaseModel):
    """Persist the durable output objects and provenance for an executed action."""

    model_config = ConfigDict(extra="forbid")

    action_plan_id: str = Field(min_length=1)
    status: Literal["succeeded", "failed", "cancelled"] = "succeeded"
    entries: List[ObjectRoleEntry] = Field(default_factory=list)
    output_records: List[ObjectInstanceRecord] = Field(default_factory=list)
    output_relations: List[ObjectRelationRecord] = Field(default_factory=list)
    meeting_id: Optional[str] = None
    affordance_verb: Optional[str] = None
    execution_result: Dict[str, Any] = Field(default_factory=dict)


class ObjectActionClosureResponse(BaseModel):
    """Result of indexing action outputs and closure relations."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    action_plan_id: str
    status: Literal["succeeded", "failed", "cancelled"]
    indexed_output_count: int
    indexed_relation_count: int
    output_refs: List[ObjectRef] = Field(default_factory=list)
    relations: List[ObjectRelationRecord] = Field(default_factory=list)


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
