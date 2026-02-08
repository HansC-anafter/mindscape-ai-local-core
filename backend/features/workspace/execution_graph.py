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

    # Get current overlay and add node
    overlay = await service._load_overlay("workspace", workspace_id)
    overlay.manual_nodes.append(manual_node)
    overlay.version += 1

    # Update cache
    service._overlay_cache[f"workspace:{workspace_id}"] = overlay

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

    # Get current overlay and add edge
    overlay = await service._load_overlay("workspace", workspace_id)
    overlay.manual_edges.append(edge)
    overlay.version += 1

    # Update cache
    service._overlay_cache[f"workspace:{workspace_id}"] = overlay

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
        from app.services.playbook_registry import PlaybookRegistry

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
