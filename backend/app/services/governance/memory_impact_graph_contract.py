"""Contract models for workspace memory impact graph responses."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class MemoryImpactGraphNode(BaseModel):
    """A single node in the task-centered memory impact subgraph."""

    id: str
    type: str
    label: str
    subtitle: Optional[str] = None
    status: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MemoryImpactGraphEdge(BaseModel):
    """A directed edge in the task-centered memory impact subgraph."""

    id: str
    from_node_id: str
    to_node_id: str
    kind: str
    provenance: Literal["explicit", "inferred"] = "explicit"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MemoryImpactGraphFocus(BaseModel):
    """Focus metadata for the subgraph response."""

    workspace_id: str
    session_id: str
    focus_node_id: str
    project_id: Optional[str] = None
    thread_id: Optional[str] = None
    execution_id: Optional[str] = None
    execution_ids: List[str] = Field(default_factory=list)


class MemoryImpactPacketSummary(BaseModel):
    """Selected packet summary for operator-facing graph drilldown."""

    selected_node_count: int = 0
    route_sections: List[str] = Field(default_factory=list)
    counts_by_type: Dict[str, int] = Field(default_factory=dict)
    selection: Dict[str, Any] = Field(default_factory=dict)


class MemoryImpactGraphResponse(BaseModel):
    """Workspace-scoped task/session memory impact graph payload."""

    workspace_id: str
    session_id: str
    focus: MemoryImpactGraphFocus
    packet_summary: MemoryImpactPacketSummary
    nodes: List[MemoryImpactGraphNode]
    edges: List[MemoryImpactGraphEdge]
    warnings: List[str] = Field(default_factory=list)
