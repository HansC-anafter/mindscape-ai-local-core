"""Overlay mutation routes for execution graph APIs."""

import uuid

from fastapi import Depends, Query

from backend.app.services.mindscape_graph_service import (
    EdgeOrigin,
    EdgeType,
    MindscapeEdge,
    MindscapeGraphService,
    NodeStatus,
    OverlayNode,
    generate_edge_id,
)
from backend.features.workspace.execution_graph_core.dependencies import (
    get_graph_service,
)
from backend.features.workspace.execution_graph_core.models import (
    CreateManualEdgeRequest,
    CreateManualNodeRequest,
    EdgeResponse,
    NodeResponse,
    OperationResponse,
    UpdateNodeRequest,
    UpdateOverlayRequest,
)


async def create_manual_node(
    request: CreateManualNodeRequest,
    workspace_id: str = Query(..., description="Workspace ID"),
    service: MindscapeGraphService = Depends(get_graph_service),
) -> NodeResponse:
    """Create a manual node in the overlay."""
    node_id = f"manual:{uuid.uuid4()}"
    manual_node = OverlayNode(
        id=node_id,
        type=request.type,
        label=request.label,
        position={"x": request.position.x, "y": request.position.y},
        metadata=request.metadata or {},
    )

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


async def update_node(
    node_id: str,
    request: UpdateNodeRequest,
    workspace_id: str = Query(..., description="Workspace ID"),
    service: MindscapeGraphService = Depends(get_graph_service),
) -> OperationResponse:
    """Update node by renaming or merging."""
    updates = {}

    if request.label:
        updates["renames"] = {node_id: request.label}

    if request.merge_into:
        await service.merge_nodes(
            "workspace",
            workspace_id,
            node_id,
            request.merge_into,
        )
        return OperationResponse(
            success=True,
            message=f"Node {node_id} merged into {request.merge_into}",
            data={"redirect": request.merge_into},
        )

    if updates:
        await service.update_overlay("workspace", workspace_id, updates)

    return OperationResponse(
        success=True,
        message="Node updated",
        data={"node_id": node_id},
    )


async def accept_node(
    node_id: str,
    workspace_id: str = Query(..., description="Workspace ID"),
    service: MindscapeGraphService = Depends(get_graph_service),
) -> OperationResponse:
    """Accept a suggested node."""
    await service.accept_node("workspace", workspace_id, node_id)
    return OperationResponse(success=True, message=f"Node {node_id} accepted")


async def reject_node(
    node_id: str,
    workspace_id: str = Query(..., description="Workspace ID"),
    service: MindscapeGraphService = Depends(get_graph_service),
) -> OperationResponse:
    """Reject a suggested node."""
    await service.reject_node("workspace", workspace_id, node_id)
    return OperationResponse(success=True, message=f"Node {node_id} rejected")


async def create_manual_edge(
    request: CreateManualEdgeRequest,
    workspace_id: str = Query(..., description="Workspace ID"),
    service: MindscapeGraphService = Depends(get_graph_service),
) -> EdgeResponse:
    """Create a manual edge in the overlay."""
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


async def update_overlay(
    request: UpdateOverlayRequest,
    workspace_id: str = Query(..., description="Workspace ID"),
    service: MindscapeGraphService = Depends(get_graph_service),
) -> OperationResponse:
    """Update overlay positions, collapsed state, and viewport."""
    updates = {}

    if request.node_positions:
        updates["node_positions"] = {
            node_id: {"x": value.x, "y": value.y, "scale": value.scale}
            for node_id, value in request.node_positions.items()
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
        success=True,
        message="Overlay updated",
        data={"version": overlay.version},
    )


def register_overlay_routes(router) -> None:
    """Register overlay routes on the public execution graph router."""
    router.post("/overlay/nodes", response_model=NodeResponse)(create_manual_node)
    router.patch("/overlay/nodes/{node_id}", response_model=OperationResponse)(
        update_node
    )
    router.post("/overlay/nodes/{node_id}/accept", response_model=OperationResponse)(
        accept_node
    )
    router.post("/overlay/nodes/{node_id}/reject", response_model=OperationResponse)(
        reject_node
    )
    router.post("/overlay/edges", response_model=EdgeResponse)(create_manual_edge)
    router.patch("/overlay", response_model=OperationResponse)(update_overlay)
