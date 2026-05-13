"""Generic composition graph contracts for pack-pluggable workbench flows."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.models.object_runtime.meeting import ObjectRoleEntry

CompositionGraphPortDirection = Literal["input", "output"]
CompositionGraphDiagnosticSeverity = Literal["error", "warning", "info"]
CompositionGraphCompileStatus = Literal["succeeded", "failed"]


class CompositionGraphViewport(BaseModel):
    """Viewport state persisted with a graph draft."""

    model_config = ConfigDict(extra="forbid")

    x: float = 0
    y: float = 0
    zoom: float = 1


class CompositionGraphPort(BaseModel):
    """Typed connection point for a graph node type."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    direction: CompositionGraphPortDirection
    label: Optional[str] = None
    data_type: str = Field(default="any", min_length=1)
    required: bool = False
    accepted_object_roles: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CompositionGraphNodeType(BaseModel):
    """Node type exposed by core or by an installed capability contract."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    source: Literal["core", "pack"] = "pack"
    capability_code: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    input_ports: List[CompositionGraphPort] = Field(default_factory=list)
    output_ports: List[CompositionGraphPort] = Field(default_factory=list)
    payload_schema: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_ports(self) -> "CompositionGraphNodeType":
        for port in self.input_ports:
            if port.direction != "input":
                raise ValueError("input_ports entries must use direction=input")
        for port in self.output_ports:
            if port.direction != "output":
                raise ValueError("output_ports entries must use direction=output")
        return self


class CompositionGraphEdgeType(BaseModel):
    """Edge type exposed by an installed capability contract."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    source_data_type: str = "any"
    target_data_type: str = "any"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CompositionGraphCompileTarget(BaseModel):
    """Pack-owned callable used for graph compilation."""

    model_config = ConfigDict(extra="forbid")

    backend: str = Field(min_length=1)
    output_mode: Literal["meeting_command_envelope"] = "meeting_command_envelope"


class CompositionGraphContract(BaseModel):
    """Installed pack graph contract normalized for the workbench UI."""

    model_config = ConfigDict(extra="forbid")

    capability_code: str = Field(min_length=1)
    label: str = Field(min_length=1)
    enabled: bool = True
    contract_version: str = Field(min_length=1)
    accepted_object_roles: List[str] = Field(default_factory=list)
    node_types: List[CompositionGraphNodeType] = Field(default_factory=list)
    edge_types: List[CompositionGraphEdgeType] = Field(default_factory=list)
    compile: CompositionGraphCompileTarget
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_pack_node_ownership(self) -> "CompositionGraphContract":
        for node_type in self.node_types:
            if node_type.id == "object_reference":
                raise ValueError("object_reference is core-owned and cannot be declared by packs")
        return self


class CompositionGraphDiagnostic(BaseModel):
    """Validation or compile diagnostic tied to a graph, node, or edge."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    severity: CompositionGraphDiagnosticSeverity = "error"
    node_id: Optional[str] = None
    edge_id: Optional[str] = None
    port_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CompositionGraphNode(BaseModel):
    """Persisted graph node instance."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    type: str = Field(min_length=1)
    position: Dict[str, float] = Field(default_factory=lambda: {"x": 0, "y": 0})
    payload: Dict[str, Any] = Field(default_factory=dict)
    capability_code: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("position")
    @classmethod
    def _validate_position(cls, value: Dict[str, Any]) -> Dict[str, float]:
        if not isinstance(value, dict):
            raise ValueError("position must be an object")
        x = float(value.get("x", 0))
        y = float(value.get("y", 0))
        return {"x": x, "y": y}


class CompositionGraphEdge(BaseModel):
    """Persisted graph edge instance."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    target: str = Field(min_length=1)
    source_port: str = Field(min_length=1)
    target_port: str = Field(min_length=1)
    type: str = "default"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CompositionGraphHistoryEntry(BaseModel):
    """Bounded edit history entry for graph draft changes."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    operation: str = Field(min_length=1)
    timestamp: str = Field(min_length=1)
    actor: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CompositionGraphMigration(BaseModel):
    """Schema migration marker applied while reading a draft."""

    model_config = ConfigDict(extra="forbid")

    from_version: str = Field(min_length=1)
    to_version: str = Field(min_length=1)
    applied_at: str = Field(min_length=1)


class CompositionGraphDraft(BaseModel):
    """Thread-scoped graph draft persisted as a data artifact."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    graph_id: str = Field(min_length=1)
    workspace_id: str = Field(min_length=1)
    title: str = "Composition Graph"
    schema_version: str = "composition_graph.v1"
    meeting_id: Optional[str] = None
    thread_id: Optional[str] = None
    selected_primary_pack: Optional[str] = None
    nodes: List[CompositionGraphNode] = Field(default_factory=list)
    edges: List[CompositionGraphEdge] = Field(default_factory=list)
    viewport: CompositionGraphViewport = Field(default_factory=CompositionGraphViewport)
    history: List[CompositionGraphHistoryEntry] = Field(default_factory=list)
    migrations: List[CompositionGraphMigration] = Field(default_factory=list)
    node_diagnostics: Dict[str, List[CompositionGraphDiagnostic]] = Field(default_factory=dict)
    edge_diagnostics: Dict[str, List[CompositionGraphDiagnostic]] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CompositionGraphDraftCreateRequest(BaseModel):
    """Create request for a graph draft."""

    model_config = ConfigDict(extra="forbid")

    title: str = "Composition Graph"
    meeting_id: Optional[str] = None
    thread_id: Optional[str] = None
    selected_primary_pack: Optional[str] = None
    nodes: List[CompositionGraphNode] = Field(default_factory=list)
    edges: List[CompositionGraphEdge] = Field(default_factory=list)
    viewport: CompositionGraphViewport = Field(default_factory=CompositionGraphViewport)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CompositionGraphDraftUpdateRequest(BaseModel):
    """Update request for a graph draft."""

    model_config = ConfigDict(extra="forbid")

    title: Optional[str] = None
    meeting_id: Optional[str] = None
    thread_id: Optional[str] = None
    selected_primary_pack: Optional[str] = None
    nodes: Optional[List[CompositionGraphNode]] = None
    edges: Optional[List[CompositionGraphEdge]] = None
    viewport: Optional[CompositionGraphViewport] = None
    history: Optional[List[CompositionGraphHistoryEntry]] = None
    metadata: Optional[Dict[str, Any]] = None


class CompositionGraphImportExportPayload(BaseModel):
    """Portable graph JSON payload."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "composition_graph.v1"
    graph_id: str = Field(min_length=1)
    title: str = "Composition Graph"
    selected_primary_pack: Optional[str] = None
    nodes: List[CompositionGraphNode] = Field(default_factory=list)
    edges: List[CompositionGraphEdge] = Field(default_factory=list)
    viewport: CompositionGraphViewport = Field(default_factory=CompositionGraphViewport)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CompositionGraphImportRequest(BaseModel):
    """Import a portable graph payload into a draft."""

    model_config = ConfigDict(extra="forbid")

    graph: CompositionGraphImportExportPayload
    meeting_id: Optional[str] = None
    thread_id: Optional[str] = None
    persist: bool = True


class CompositionGraphCommandEnvelopeDraft(BaseModel):
    """Generic meeting command envelope returned by graph compile."""

    model_config = ConfigDict(extra="allow")

    meeting_id: str = Field(min_length=1)
    intent_text: str = Field(min_length=1)
    thread_id: Optional[str] = None
    context_objects: List[ObjectRoleEntry] = Field(default_factory=list)
    meeting_mentions: List[Dict[str, Any]] = Field(default_factory=list)
    requested_action: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CompositionGraphCompileRequest(BaseModel):
    """Compile request for a graph draft or inline graph payload."""

    model_config = ConfigDict(extra="forbid")

    graph_id: Optional[str] = None
    draft_id: Optional[str] = None
    meeting_id: str = Field(min_length=1)
    thread_id: Optional[str] = None
    command: str = Field(min_length=1)
    selected_primary_pack: Optional[str] = None
    nodes: Optional[List[CompositionGraphNode]] = None
    edges: Optional[List[CompositionGraphEdge]] = None
    viewport: Optional[CompositionGraphViewport] = None
    meeting_mentions: List[Dict[str, Any]] = Field(default_factory=list)
    context_objects: List[ObjectRoleEntry] = Field(default_factory=list)
    object_action_entries: List[ObjectRoleEntry] = Field(default_factory=list)
    selected_pack_tool: Optional[str] = None
    action_parameters: Dict[str, Any] = Field(default_factory=dict)


class CompositionGraphCompileResponse(BaseModel):
    """Result of validating and compiling a composition graph."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    status: CompositionGraphCompileStatus
    output_mode: Literal["meeting_command_envelope"] = "meeting_command_envelope"
    diagnostics: List[CompositionGraphDiagnostic] = Field(default_factory=list)
    command_envelope: Optional[CompositionGraphCommandEnvelopeDraft] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CompositionGraphContractsResponse(BaseModel):
    """Installed composition graph contracts visible to a workspace."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    contracts: List[CompositionGraphContract] = Field(default_factory=list)
    diagnostics: List[CompositionGraphDiagnostic] = Field(default_factory=list)


class CompositionGraphDraftListResponse(BaseModel):
    """List response for graph drafts."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    drafts: List[CompositionGraphDraft] = Field(default_factory=list)


class CompositionGraphDraftResponse(BaseModel):
    """Single draft response."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    draft: CompositionGraphDraft


class CompositionGraphImportResponse(BaseModel):
    """Import validation and optional persistence response."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    valid: bool
    diagnostics: List[CompositionGraphDiagnostic] = Field(default_factory=list)
    draft: Optional[CompositionGraphDraft] = None
