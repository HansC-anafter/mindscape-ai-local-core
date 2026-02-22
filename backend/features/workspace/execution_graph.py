"""
Mindscape Graph API Routes

API endpoints for the mindscape graph visualization:
- GET /graph - Get derived graph for workspace/group
- POST /overlay/nodes - Create manual node
- PATCH /overlay/nodes/{nodeId} - Update node (rename/merge)
- POST /overlay/nodes/{nodeId}/accept - Accept suggested node
- POST /overlay/nodes/{nodeId}/reject - Reject suggested node
- POST /overlay/edges - Create manual edge
- PATCH /overlay - Update overlay (positions, viewport, etc.)
"""

import logging
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from datetime import datetime

from backend.app.services.mindscape_graph_service import (
    MindscapeGraphService,
    MindscapeGraph,
    MindscapeNode,
    MindscapeEdge,
    GraphOverlay,
    OverlayNode,
    NodeStatus,
    EdgeType,
    EdgeOrigin,
)
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.routes.workspace_dependencies import get_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/execution-graph", tags=["execution-graph"])


# ==================== Request/Response Models ====================


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


# ==================== Dependencies ====================


def get_graph_service(
    store: MindscapeStore = Depends(get_store),
) -> MindscapeGraphService:
    """Get MindscapeGraphService instance"""
    return MindscapeGraphService(db_path=store.db_path)


# ==================== Endpoints ====================


@router.get("/graph", response_model=GraphResponse)
async def get_graph(
    workspace_id: Optional[str] = Query(None, description="Workspace ID"),
    workspace_group_id: Optional[str] = Query(None, description="Workspace Group ID"),
    include_reasoning: bool = Query(
        False,
        description="Include reasoning graph nodes (not supported for group queries)",
    ),
    service: MindscapeGraphService = Depends(get_graph_service),
):
    """
    Get mindscape graph for workspace or workspace group.

    Either workspace_id or workspace_group_id must be provided.
    """
    if not workspace_id and not workspace_group_id:
        raise HTTPException(
            status_code=400,
            detail="Either workspace_id or workspace_group_id is required",
        )

    try:
        graph = await service.get_graph(
            workspace_id=workspace_id, workspace_group_id=workspace_group_id
        )

        # Governance: optionally merge reasoning graph nodes into the main graph
        if include_reasoning:
            if workspace_group_id:
                raise HTTPException(
                    status_code=400,
                    detail="include_reasoning is not supported for group queries",
                )
            try:
                from backend.app.services.stores.reasoning_traces_store import (
                    ReasoningTracesStore,
                )

                traces_store = ReasoningTracesStore()
                traces = traces_store.list_by_workspace(workspace_id, limit=10)
                for trace in traces:
                    try:
                        rg = trace.graph
                        service.derive_from_reasoning_graph(workspace_id, rg, trace.id)
                    except Exception as e:
                        logger.warning(
                            f"Failed to derive reasoning graph {trace.id}: {e}"
                        )
                # Re-fetch graph with reasoning nodes included
                graph = await service.get_graph(
                    workspace_id=workspace_id,
                    workspace_group_id=workspace_group_id,
                )
            except Exception as e:
                logger.warning(f"Failed to include reasoning graphs: {e}")

        return GraphResponse(
            nodes=[
                {
                    "id": n.id,
                    "type": n.type,
                    "label": n.label,
                    "status": n.status.value,
                    "metadata": n.metadata,
                    "created_at": n.created_at.isoformat() if n.created_at else None,
                }
                for n in graph.nodes
            ],
            edges=[
                {
                    "id": e.id,
                    "from_id": e.from_id,
                    "to_id": e.to_id,
                    "type": e.type.value,
                    "origin": e.origin.value,
                    "confidence": e.confidence,
                    "status": e.status.value,
                    "metadata": e.metadata,
                }
                for e in graph.edges
            ],
            overlay={
                "node_positions": graph.overlay.node_positions,
                "collapsed_state": graph.overlay.collapsed_state,
                "viewport": graph.overlay.viewport,
                "version": graph.overlay.version,
            },
            scope_type=graph.scope_type,
            scope_id=graph.scope_id,
            derived_at=graph.derived_at.isoformat(),
        )
    except Exception as e:
        logger.error(f"Failed to get graph: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/overlay/nodes", response_model=NodeResponse)
async def create_manual_node(
    request: CreateManualNodeRequest,
    workspace_id: str = Query(..., description="Workspace ID"),
    service: MindscapeGraphService = Depends(get_graph_service),
):
    """Create a manual node in the overlay"""
    import uuid

    node_id = f"manual:{uuid.uuid4()}"
    manual_node = OverlayNode(
        id=node_id,
        type=request.type,
        label=request.label,
        position={"x": request.position.x, "y": request.position.y},
        metadata=request.metadata or {},
    )

    # Persist through update_overlay (writes to DB, not just cache)
    await service.update_overlay(
        "workspace",
        workspace_id,
        {"manual_nodes_add": [manual_node.__dict__]},
    )

    return NodeResponse(
        id=node_id,
        type=request.type,
        label=request.label,
        status=NodeStatus.ACCEPTED.value,
        metadata=request.metadata or {},
    )


@router.patch("/overlay/nodes/{node_id}", response_model=OperationResponse)
async def update_node(
    node_id: str,
    request: UpdateNodeRequest,
    workspace_id: str = Query(..., description="Workspace ID"),
    service: MindscapeGraphService = Depends(get_graph_service),
):
    """Update node (rename or merge)"""
    updates = {}

    if request.label:
        updates["renames"] = {node_id: request.label}

    if request.merge_into:
        await service.merge_nodes(
            "workspace", workspace_id, node_id, request.merge_into
        )
        return OperationResponse(
            success=True,
            message=f"Node {node_id} merged into {request.merge_into}",
            data={"redirect": request.merge_into},
        )

    if updates:
        await service.update_overlay("workspace", workspace_id, updates)

    return OperationResponse(
        success=True, message="Node updated", data={"node_id": node_id}
    )


@router.post("/overlay/nodes/{node_id}/accept", response_model=OperationResponse)
async def accept_node(
    node_id: str,
    workspace_id: str = Query(..., description="Workspace ID"),
    service: MindscapeGraphService = Depends(get_graph_service),
):
    """Accept a suggested node"""
    await service.accept_node("workspace", workspace_id, node_id)
    return OperationResponse(success=True, message=f"Node {node_id} accepted")


@router.post("/overlay/nodes/{node_id}/reject", response_model=OperationResponse)
async def reject_node(
    node_id: str,
    workspace_id: str = Query(..., description="Workspace ID"),
    service: MindscapeGraphService = Depends(get_graph_service),
):
    """Reject a suggested node"""
    await service.reject_node("workspace", workspace_id, node_id)
    return OperationResponse(success=True, message=f"Node {node_id} rejected")


@router.post("/overlay/edges", response_model=EdgeResponse)
async def create_manual_edge(
    request: CreateManualEdgeRequest,
    workspace_id: str = Query(..., description="Workspace ID"),
    service: MindscapeGraphService = Depends(get_graph_service),
):
    """Create a manual edge in the overlay"""
    from ...app.services.mindscape_graph_service import generate_edge_id

    edge_id = generate_edge_id(request.from_id, request.to_id, request.type)

    edge = MindscapeEdge(
        id=edge_id,
        from_id=request.from_id,
        to_id=request.to_id,
        type=EdgeType(request.type),
        origin=EdgeOrigin.USER,
        confidence=1.0,
        status=NodeStatus.ACCEPTED,
        metadata=request.metadata or {},
    )

    # Persist through update_overlay (writes to DB, not just cache)
    await service.update_overlay(
        "workspace",
        workspace_id,
        {
            "manual_edges_add": [
                {
                    "id": edge.id,
                    "from_id": edge.from_id,
                    "to_id": edge.to_id,
                    "type": edge.type.value,
                    "origin": edge.origin.value,
                    "confidence": edge.confidence,
                    "status": edge.status.value,
                    "metadata": edge.metadata,
                }
            ]
        },
    )

    return EdgeResponse(
        id=edge_id,
        from_id=request.from_id,
        to_id=request.to_id,
        type=request.type,
        origin=EdgeOrigin.USER.value,
        confidence=1.0,
        status=NodeStatus.ACCEPTED.value,
    )


@router.patch("/overlay", response_model=OperationResponse)
async def update_overlay(
    request: UpdateOverlayRequest,
    workspace_id: str = Query(..., description="Workspace ID"),
    service: MindscapeGraphService = Depends(get_graph_service),
):
    """Update overlay (positions, collapsed state, viewport)"""
    updates = {}

    if request.node_positions:
        updates["node_positions"] = {
            k: {"x": v.x, "y": v.y, "scale": v.scale}
            for k, v in request.node_positions.items()
        }

    if request.collapsed_state:
        updates["collapsed_state"] = request.collapsed_state

    if request.viewport:
        updates["viewport"] = {
            "x": request.viewport.x,
            "y": request.viewport.y,
            "zoom": request.viewport.zoom,
        }

    overlay = await service.update_overlay("workspace", workspace_id, updates)

    return OperationResponse(
        success=True, message="Overlay updated", data={"version": overlay.version}
    )


# ==================== Group Endpoints ====================


@router.get("/groups/{group_id}/graph", response_model=GraphResponse)
async def get_group_graph(
    group_id: str, service: MindscapeGraphService = Depends(get_graph_service)
):
    """Get aggregated graph for a workspace group"""
    try:
        graph = await service.get_graph(workspace_group_id=group_id)

        return GraphResponse(
            nodes=[
                {
                    "id": n.id,
                    "type": n.type,
                    "label": n.label,
                    "status": n.status.value,
                    "metadata": n.metadata,
                    "created_at": n.created_at.isoformat() if n.created_at else None,
                }
                for n in graph.nodes
            ],
            edges=[
                {
                    "id": e.id,
                    "from_id": e.from_id,
                    "to_id": e.to_id,
                    "type": e.type.value,
                    "origin": e.origin.value,
                    "confidence": e.confidence,
                    "status": e.status.value,
                    "metadata": e.metadata,
                }
                for e in graph.edges
            ],
            overlay={
                "node_positions": graph.overlay.node_positions,
                "collapsed_state": graph.overlay.collapsed_state,
                "viewport": graph.overlay.viewport,
                "version": graph.overlay.version,
            },
            scope_type=graph.scope_type,
            scope_id=graph.scope_id,
            derived_at=graph.derived_at.isoformat(),
        )
    except Exception as e:
        logger.error(f"Failed to get group graph: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ==================== SGR Reasoning Graph Endpoints ====================


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


@router.get("/reasoning/{trace_id}", response_model=ReasoningGraphResponse)
async def get_reasoning_graph(trace_id: str):
    """
    Get a reasoning graph by trace ID.

    Returns the full reasoning graph structure including nodes, edges, and metadata.
    """
    try:
        from backend.app.services.stores.reasoning_traces_store import ReasoningTracesStore

        store = ReasoningTracesStore()
        trace = store.get_by_id(trace_id)
        if not trace:
            raise HTTPException(
                status_code=404, detail=f"Reasoning trace not found: {trace_id}"
            )
        return ReasoningGraphResponse(
            id=trace.id,
            workspace_id=trace.workspace_id,
            execution_id=trace.execution_id,
            assistant_event_id=trace.assistant_event_id,
            graph=trace.graph_json,
            schema_version=trace.schema_version,
            sgr_mode=trace.sgr_mode,
            model=trace.model,
            token_count=trace.token_count,
            latency_ms=trace.latency_ms,
            created_at=trace.created_at.isoformat(),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get reasoning graph: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reasoning", response_model=List[ReasoningGraphResponse])
async def list_reasoning_graphs(
    workspace_id: str = Query(..., description="Workspace ID"),
    execution_id: Optional[str] = Query(None, description="Filter by execution ID"),
    limit: int = Query(20, ge=1, le=100, description="Max results"),
):
    """
    List reasoning graphs for a workspace.

    Optionally filter by execution_id to find the reasoning graph
    associated with a specific chat execution.
    """
    try:
        from backend.app.services.stores.reasoning_traces_store import ReasoningTracesStore

        store = ReasoningTracesStore()

        if execution_id:
            # Use workspace-scoped query to prevent cross-workspace access
            trace = store.get_by_execution_id_and_workspace(execution_id, workspace_id)
            traces = [trace] if trace else []
        else:
            traces = store.list_by_workspace(workspace_id, limit=limit)

        return [
            ReasoningGraphResponse(
                id=t.id,
                workspace_id=t.workspace_id,
                execution_id=t.execution_id,
                assistant_event_id=t.assistant_event_id,
                graph=t.graph_json,
                schema_version=t.schema_version,
                sgr_mode=t.sgr_mode,
                model=t.model,
                token_count=t.token_count,
                latency_ms=t.latency_ms,
                created_at=t.created_at.isoformat(),
            )
            for t in traces
        ]
    except Exception as e:
        logger.error(f"Failed to list reasoning graphs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Playbook DAG Expansion ====================


class PlaybookStepResponse(BaseModel):
    """Playbook step for DAG visualization"""

    id: str
    tool: Optional[str] = None
    tool_slot: Optional[str] = None
    depends_on: List[str] = []
    has_gate: bool = False
    gate_type: Optional[str] = None


class PlaybookDAGResponse(BaseModel):
    """Playbook DAG response for expansion view"""

    playbook_code: str
    name: str
    description: Optional[str] = None
    steps: List[PlaybookStepResponse]
    inputs: Dict[str, Any] = {}
    outputs: Dict[str, Any] = {}


@router.get("/playbook/{playbook_code}", response_model=PlaybookDAGResponse)
async def get_playbook_dag(
    playbook_code: str,
):
    """
    Get playbook details and step DAG for expansion view.

    Returns the playbook structure including:
    - Metadata (name, description)
    - Steps with dependencies for DAG rendering
    - Input/output definitions
    """
    try:
        from backend.app.services.playbook_registry import PlaybookRegistry

        registry = PlaybookRegistry()
        playbook_run = await registry.get_playbook(playbook_code)

        if not playbook_run:
            raise HTTPException(
                status_code=404, detail=f"Playbook not found: {playbook_code}"
            )

        # Extract playbook.json for step information
        playbook_json = playbook_run.playbook_json

        steps = []
        if playbook_json and playbook_json.steps:
            for step in playbook_json.steps:
                steps.append(
                    PlaybookStepResponse(
                        id=step.id,
                        tool=step.tool,
                        tool_slot=step.tool_slot,
                        depends_on=step.depends_on or [],
                        has_gate=step.gate is not None,
                        gate_type=step.gate.type if step.gate else None,
                    )
                )

        return PlaybookDAGResponse(
            playbook_code=playbook_code,
            name=(
                playbook_run.playbook.metadata.name
                if playbook_run.playbook
                else playbook_code
            ),
            description=(
                playbook_run.playbook.metadata.description
                if playbook_run.playbook
                else None
            ),
            steps=steps,
            inputs=(
                {k: v.dict() for k, v in (playbook_json.inputs or {}).items()}
                if playbook_json
                else {}
            ),
            outputs=(
                {k: v.dict() for k, v in (playbook_json.outputs or {}).items()}
                if playbook_json
                else {}
            ),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get playbook DAG: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
