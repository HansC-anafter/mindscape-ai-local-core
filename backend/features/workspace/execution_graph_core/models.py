"""Request and response models for execution graph routes."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class NodePosition(BaseModel):
    x: float
    y: float
    scale: Optional[float] = None


class Viewport(BaseModel):
    x: float
    y: float
    zoom: float


class CreateManualNodeRequest(BaseModel):
    type: str = Field(..., description="Node type: intent, note, milestone")
    label: str = Field(..., description="Node label")
    position: NodePosition = Field(..., description="Node position")
    metadata: Optional[Dict[str, Any]] = None


class UpdateNodeRequest(BaseModel):
    label: Optional[str] = Field(None, description="New label (rename)")
    merge_into: Optional[str] = Field(None, description="Target node ID for merge")


class CreateManualEdgeRequest(BaseModel):
    from_id: str = Field(..., description="Source node ID")
    to_id: str = Field(..., description="Target node ID")
    type: str = Field(..., description="Edge type")
    metadata: Optional[Dict[str, Any]] = None


class UpdateOverlayRequest(BaseModel):
    node_positions: Optional[Dict[str, NodePosition]] = None
    collapsed_state: Optional[Dict[str, bool]] = None
    viewport: Optional[Viewport] = None


class GraphResponse(BaseModel):
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]
    overlay: Dict[str, Any]
    scope_type: str
    scope_id: str
    derived_at: str


class NodeResponse(BaseModel):
    id: str
    type: str
    label: str
    status: str
    metadata: Dict[str, Any]


class EdgeResponse(BaseModel):
    id: str
    from_id: str
    to_id: str
    type: str
    origin: str
    confidence: float
    status: str


class OperationResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None


class ReasoningGraphResponse(BaseModel):
    """Response model for reasoning graph data."""

    id: str
    workspace_id: str
    execution_id: Optional[str] = None
    assistant_event_id: Optional[str] = None
    graph: Dict[str, Any]
    schema_version: int
    sgr_mode: str
    model: Optional[str] = None
    token_count: Optional[int] = None
    latency_ms: Optional[int] = None
    created_at: str


class PlaybookStepResponse(BaseModel):
    """Playbook step for DAG visualization."""

    id: str
    tool: Optional[str] = None
    tool_slot: Optional[str] = None
    depends_on: List[str] = []
    has_gate: bool = False
    gate_type: Optional[str] = None


class PlaybookDAGResponse(BaseModel):
    """Playbook DAG response for expansion view."""

    playbook_code: str
    name: str
    description: Optional[str] = None
    steps: List[PlaybookStepResponse]
    inputs: Dict[str, Any] = {}
    outputs: Dict[str, Any] = {}
