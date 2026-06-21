"""Composition graph compile and execution run models."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from backend.app.models.object_runtime.composition_graph_common import (
    CompositionGraphCompileStatus,
    CompositionGraphDiagnostic,
    CompositionGraphRunNodeStatus,
    CompositionGraphRunStatus,
    CompositionGraphViewport,
)
from backend.app.models.object_runtime.composition_graph_drafts import (
    CompositionGraphEdge,
    CompositionGraphNode,
)
from backend.app.models.object_runtime.meeting import ObjectRoleEntry
from backend.app.models.run_harness import RunHarnessSpec


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
    output_mode: Literal["meeting_command_envelope", "run_harness_spec"] = (
        "meeting_command_envelope"
    )


class CompositionGraphCompileResponse(BaseModel):
    """Result of validating and compiling a composition graph."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    status: CompositionGraphCompileStatus
    output_mode: Literal["meeting_command_envelope", "run_harness_spec"] = (
        "meeting_command_envelope"
    )
    diagnostics: List[CompositionGraphDiagnostic] = Field(default_factory=list)
    command_envelope: Optional[CompositionGraphCommandEnvelopeDraft] = None
    run_harness_spec: Optional[RunHarnessSpec] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CompositionGraphRunContext(BaseModel):
    """Context attached to an executable composition graph run."""

    model_config = ConfigDict(extra="forbid")

    meeting_id: Optional[str] = None
    thread_id: Optional[str] = None
    command: str = ""


class CompositionGraphRunNodeState(BaseModel):
    """Persisted execution state for one graph node inside a run."""

    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(min_length=1)
    node_type: str = Field(min_length=1)
    status: CompositionGraphRunNodeStatus = "pending"
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    input_values: Dict[str, Any] = Field(default_factory=dict)
    outputs: Dict[str, Any] = Field(default_factory=dict)
    diagnostics: List[CompositionGraphDiagnostic] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CompositionGraphRun(BaseModel):
    """Artifact-backed executable composition graph run."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    graph_id: str = Field(min_length=1)
    workspace_id: str = Field(min_length=1)
    status: CompositionGraphRunStatus = "pending"
    schema_version: str = "composition_graph_run.v1"
    draft_id: Optional[str] = None
    meeting_id: Optional[str] = None
    thread_id: Optional[str] = None
    command: str = ""
    nodes: List[CompositionGraphNode] = Field(default_factory=list)
    edges: List[CompositionGraphEdge] = Field(default_factory=list)
    node_states: Dict[str, CompositionGraphRunNodeState] = Field(default_factory=dict)
    diagnostics: List[CompositionGraphDiagnostic] = Field(default_factory=list)
    outputs: Dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(min_length=1)
    updated_at: str = Field(min_length=1)
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CompositionGraphRunRequest(BaseModel):
    """Start request for an executable composition graph run."""

    model_config = ConfigDict(extra="forbid")

    graph_id: Optional[str] = None
    draft_id: Optional[str] = None
    meeting_id: Optional[str] = None
    thread_id: Optional[str] = None
    command: str = ""
    nodes: Optional[List[CompositionGraphNode]] = None
    edges: Optional[List[CompositionGraphEdge]] = None
    viewport: Optional[CompositionGraphViewport] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CompositionGraphRunResponse(BaseModel):
    """Single graph run response."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    run: CompositionGraphRun


class CompositionGraphRunResumeRequest(BaseModel):
    """Resume request for a waiting graph run."""

    model_config = ConfigDict(extra="forbid")

    command: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "CompositionGraphCommandEnvelopeDraft",
    "CompositionGraphCompileRequest",
    "CompositionGraphCompileResponse",
    "CompositionGraphRun",
    "CompositionGraphRunContext",
    "CompositionGraphRunNodeState",
    "CompositionGraphRunRequest",
    "CompositionGraphRunResponse",
    "CompositionGraphRunResumeRequest",
]
