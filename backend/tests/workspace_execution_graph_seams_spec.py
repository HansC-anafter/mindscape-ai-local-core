from datetime import datetime, timezone
from pathlib import Path

from backend.app.services import mindscape_graph_service as graph_service
from backend.features.workspace import execution_graph
from backend.features.workspace.execution_graph_core.serializers import (
    build_graph_response,
)


ROOT = Path(__file__).resolve().parents[2]
FACADE_PATH = ROOT / "backend" / "features" / "workspace" / "execution_graph.py"
CORE_DIR = ROOT / "backend" / "features" / "workspace" / "execution_graph_core"


def test_public_facade_exports_legacy_route_symbols() -> None:
    assert execution_graph.MindscapeGraphService is graph_service.MindscapeGraphService
    assert execution_graph.MindscapeGraph is graph_service.MindscapeGraph
    assert execution_graph.MindscapeNode is graph_service.MindscapeNode
    assert execution_graph.MindscapeEdge is graph_service.MindscapeEdge
    assert execution_graph.GraphOverlay is graph_service.GraphOverlay
    assert execution_graph.OverlayNode is graph_service.OverlayNode
    assert execution_graph.NodeStatus is graph_service.NodeStatus
    assert execution_graph.EdgeType is graph_service.EdgeType
    assert execution_graph.EdgeOrigin is graph_service.EdgeOrigin

    for name in [
        "NodePosition",
        "Viewport",
        "CreateManualNodeRequest",
        "UpdateNodeRequest",
        "CreateManualEdgeRequest",
        "UpdateOverlayRequest",
        "GraphResponse",
        "NodeResponse",
        "EdgeResponse",
        "OperationResponse",
        "ReasoningGraphResponse",
        "PlaybookStepResponse",
        "PlaybookDAGResponse",
        "get_graph_service",
        "get_graph",
        "get_group_graph",
        "create_manual_node",
        "update_node",
        "accept_node",
        "reject_node",
        "create_manual_edge",
        "update_overlay",
        "get_reasoning_graph",
        "list_reasoning_graphs",
        "get_playbook_dag",
    ]:
        assert hasattr(execution_graph, name), name


def test_execution_graph_router_registers_existing_paths_once() -> None:
    expected = {
        ("GET", "/api/v1/execution-graph/graph"),
        ("POST", "/api/v1/execution-graph/overlay/nodes"),
        ("PATCH", "/api/v1/execution-graph/overlay/nodes/{node_id}"),
        ("POST", "/api/v1/execution-graph/overlay/nodes/{node_id}/accept"),
        ("POST", "/api/v1/execution-graph/overlay/nodes/{node_id}/reject"),
        ("POST", "/api/v1/execution-graph/overlay/edges"),
        ("PATCH", "/api/v1/execution-graph/overlay"),
        ("GET", "/api/v1/execution-graph/groups/{group_id}/graph"),
        ("GET", "/api/v1/execution-graph/reasoning/{trace_id}"),
        ("GET", "/api/v1/execution-graph/reasoning"),
        ("GET", "/api/v1/execution-graph/playbook/{playbook_code}"),
    }

    actual = {
        (method, route.path)
        for route in execution_graph.router.routes
        for method in getattr(route, "methods", set())
        if method not in {"HEAD", "OPTIONS"}
    }

    assert actual == expected
    assert len(actual) == len(expected)


def test_graph_response_serializer_preserves_schema_shape() -> None:
    created_at = datetime(2026, 6, 21, 10, 30, tzinfo=timezone.utc)
    derived_at = datetime(2026, 6, 21, 11, 45, tzinfo=timezone.utc)
    graph = graph_service.MindscapeGraph(
        nodes=[
            graph_service.MindscapeNode(
                id="intent:one",
                type="intent",
                label="Intent One",
                status=graph_service.NodeStatus.ACCEPTED,
                metadata={"priority": "high"},
                created_at=created_at,
            )
        ],
        edges=[
            graph_service.MindscapeEdge(
                id="edge:one",
                from_id="intent:one",
                to_id="execution:one",
                type=graph_service.EdgeType.SPAWNS,
                origin=graph_service.EdgeOrigin.USER,
                confidence=0.75,
                status=graph_service.NodeStatus.SUGGESTED,
                metadata={"source": "test"},
            )
        ],
        overlay=graph_service.GraphOverlay(
            node_positions={"intent:one": {"x": 1, "y": 2}},
            collapsed_state={"intent:one": False},
            viewport={"x": 0, "y": 0, "zoom": 1},
            version=7,
        ),
        scope_type="workspace",
        scope_id="workspace-1",
        derived_at=derived_at,
    )

    response = build_graph_response(graph)

    assert response.scope_type == "workspace"
    assert response.scope_id == "workspace-1"
    assert response.derived_at == derived_at.isoformat()
    assert response.nodes == [
        {
            "id": "intent:one",
            "type": "intent",
            "label": "Intent One",
            "status": "accepted",
            "metadata": {"priority": "high"},
            "created_at": created_at.isoformat(),
        }
    ]
    assert response.edges == [
        {
            "id": "edge:one",
            "from_id": "intent:one",
            "to_id": "execution:one",
            "type": "spawns",
            "origin": "user",
            "confidence": 0.75,
            "status": "suggested",
            "metadata": {"source": "test"},
        }
    ]
    assert response.overlay == {
        "node_positions": {"intent:one": {"x": 1, "y": 2}},
        "collapsed_state": {"intent:one": False},
        "viewport": {"x": 0, "y": 0, "zoom": 1},
        "version": 7,
    }


def test_route_registration_uses_single_public_router() -> None:
    facade_source = FACADE_PATH.read_text(encoding="utf-8")
    private_source = "\n".join(
        path.read_text(encoding="utf-8") for path in CORE_DIR.glob("*.py")
    )

    assert facade_source.count("APIRouter(") == 1
    assert 'prefix="/api/v1/execution-graph"' in facade_source
    assert "register_graph_routes(router)" in facade_source
    assert "register_overlay_routes(router)" in facade_source
    assert "register_reasoning_routes(router)" in facade_source
    assert "register_playbook_routes(router)" in facade_source
    assert "APIRouter(" not in private_source
    assert "include_router(" not in private_source
    assert "router = APIRouter" not in private_source


def test_execution_graph_seam_files_stay_below_line_gate() -> None:
    paths = [
        FACADE_PATH,
        *(sorted(CORE_DIR.glob("*.py"))),
        Path(__file__),
    ]

    for path in paths:
        assert len(path.read_text(encoding="utf-8").splitlines()) <= 500, path
