"""Mindscape graph API route facade."""

from fastapi import APIRouter

from backend.app.services.mindscape_graph_service import (
    EdgeOrigin,
    EdgeType,
    GraphOverlay,
    MindscapeEdge,
    MindscapeGraph,
    MindscapeGraphService,
    MindscapeNode,
    NodeStatus,
    OverlayNode,
)
from backend.features.workspace.execution_graph_core.dependencies import (
    get_graph_service,
)
from backend.features.workspace.execution_graph_core.graph_routes import (
    get_graph,
    get_group_graph,
    register_graph_routes,
)
from backend.features.workspace.execution_graph_core.models import (
    CreateManualEdgeRequest,
    CreateManualNodeRequest,
    EdgeResponse,
    GraphResponse,
    NodePosition,
    NodeResponse,
    OperationResponse,
    PlaybookDAGResponse,
    PlaybookStepResponse,
    ReasoningGraphResponse,
    UpdateNodeRequest,
    UpdateOverlayRequest,
    Viewport,
)
from backend.features.workspace.execution_graph_core.overlay_routes import (
    accept_node,
    create_manual_edge,
    create_manual_node,
    reject_node,
    register_overlay_routes,
    update_node,
    update_overlay,
)
from backend.features.workspace.execution_graph_core.playbook_routes import (
    get_playbook_dag,
    register_playbook_routes,
)
from backend.features.workspace.execution_graph_core.reasoning_routes import (
    get_reasoning_graph,
    list_reasoning_graphs,
    register_reasoning_routes,
)

router = APIRouter(prefix="/api/v1/execution-graph", tags=["execution-graph"])

register_graph_routes(router)
register_overlay_routes(router)
register_reasoning_routes(router)
register_playbook_routes(router)

__all__ = [
    "CreateManualEdgeRequest",
    "CreateManualNodeRequest",
    "EdgeOrigin",
    "EdgeResponse",
    "EdgeType",
    "GraphOverlay",
    "GraphResponse",
    "MindscapeEdge",
    "MindscapeGraph",
    "MindscapeGraphService",
    "MindscapeNode",
    "NodePosition",
    "NodeResponse",
    "NodeStatus",
    "OperationResponse",
    "OverlayNode",
    "PlaybookDAGResponse",
    "PlaybookStepResponse",
    "ReasoningGraphResponse",
    "UpdateNodeRequest",
    "UpdateOverlayRequest",
    "Viewport",
    "accept_node",
    "create_manual_edge",
    "create_manual_node",
    "get_graph",
    "get_graph_service",
    "get_group_graph",
    "get_playbook_dag",
    "get_reasoning_graph",
    "list_reasoning_graphs",
    "reject_node",
    "router",
    "update_node",
    "update_overlay",
]
