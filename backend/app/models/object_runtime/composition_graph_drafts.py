"""Composition graph draft, import, export, and response models."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.models.object_runtime.composition_graph_common import (
    CompositionGraphDiagnostic,
    CompositionGraphViewport,
)
from backend.app.models.object_runtime.composition_graph_contracts import (
    CompositionGraphContract,
)


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


__all__ = [
    "CompositionGraphContractsResponse",
    "CompositionGraphDraft",
    "CompositionGraphDraftCreateRequest",
    "CompositionGraphDraftListResponse",
    "CompositionGraphDraftResponse",
    "CompositionGraphDraftUpdateRequest",
    "CompositionGraphEdge",
    "CompositionGraphHistoryEntry",
    "CompositionGraphImportExportPayload",
    "CompositionGraphImportRequest",
    "CompositionGraphImportResponse",
    "CompositionGraphMigration",
    "CompositionGraphNode",
]
