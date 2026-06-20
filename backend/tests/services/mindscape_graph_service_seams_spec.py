from pathlib import Path

from backend.app.services import mindscape_graph_derivation as derivation
from backend.app.services import mindscape_graph_models as models
from backend.app.services import mindscape_graph_overlay as overlay
from backend.app.services import mindscape_graph_service as facade


def test_legacy_model_and_helper_imports_still_resolve_from_facade() -> None:
    assert facade.GraphOverlay is models.GraphOverlay
    assert facade.MindscapeGraph is models.MindscapeGraph
    assert facade.MindscapeNode is models.MindscapeNode
    assert facade.MindscapeEdge is models.MindscapeEdge
    assert facade.EdgeType is models.EdgeType
    assert facade.EdgeOrigin is models.EdgeOrigin
    assert facade.NodeStatus is models.NodeStatus
    assert facade.NodeIdPrefix is models.NodeIdPrefix
    assert facade.generate_node_id is models.generate_node_id
    assert facade.generate_edge_id is models.generate_edge_id
    assert facade.DERIVATION_RULES is models.DERIVATION_RULES


def test_overlay_application_and_canonicalization_preserve_redirects() -> None:
    service = facade.MindscapeGraphService(":memory:")
    graph = facade.MindscapeGraph(
        nodes=[
            facade.MindscapeNode(id="intent:a", type="intent", label="A"),
            facade.MindscapeNode(id="intent:b", type="intent", label="B"),
        ],
        edges=[
            facade.MindscapeEdge(
                id="edge:manual",
                from_id="intent:b",
                to_id="intent:a",
                type=facade.EdgeType.REFERS_TO,
            )
        ],
    )
    graph_overlay = facade.GraphOverlay(
        node_positions={"intent:b": {"x": 12, "y": 34}},
        collapsed_state={"intent:b": True},
        renames={"intent:b": "Renamed B"},
        merge_redirects={"intent:b": "intent:a"},
        manual_nodes=[
            facade.OverlayNode(
                id="manual:note",
                type="note",
                label="Manual Note",
                position={"x": 1, "y": 2},
            )
        ],
        manual_edges=[
            facade.MindscapeEdge(
                id="edge:note",
                from_id="manual:note",
                to_id="intent:b",
                type=facade.EdgeType.REFERS_TO,
                origin=facade.EdgeOrigin.USER,
            )
        ],
        node_status_overrides={"intent:a": facade.NodeStatus.ACCEPTED.value},
    )

    with_overlay = service._apply_overlay(graph, graph_overlay)
    canonical = service._canonicalize(with_overlay)

    assert any(node.id == "manual:note" for node in canonical.nodes)
    assert all(node.id != "intent:b" for node in canonical.nodes)
    assert canonical.overlay.node_positions == {"intent:a": {"x": 12, "y": 34}}
    assert canonical.overlay.collapsed_state == {"intent:a": True}
    assert canonical.overlay.renames == {"intent:a": "Renamed B"}
    assert all(edge.from_id != "intent:b" for edge in canonical.edges)
    assert all(edge.to_id != "intent:b" for edge in canonical.edges)


def test_reasoning_graph_projection_adds_sgr_nodes_and_edges() -> None:
    service = facade.MindscapeGraphService(":memory:")
    graph = facade.MindscapeGraph()

    service.derive_from_reasoning_graph(
        graph,
        "trace-1",
        {
            "nodes": [
                {"id": "n1", "type": "premise", "content": "Premise"},
                {"id": "n2", "type": "conclusion", "content": "Conclusion"},
            ],
            "edges": [{"source": "n1", "target": "n2", "relation": "supports"}],
        },
    )

    assert [node.type for node in graph.nodes] == [
        "reasoning_premise",
        "reasoning_conclusion",
    ]
    assert len(graph.edges) == 1
    assert graph.edges[0].type is facade.EdgeType.SUPPORTS
    assert graph.edges[0].origin is facade.EdgeOrigin.SGR
    assert graph.edges[0].metadata["reasoning_trace_id"] == "trace-1"


def test_helper_modules_do_not_define_duplicate_resource_surfaces() -> None:
    helper_modules = [models, derivation, overlay]
    forbidden_markers = [
        "APIRouter(",
        "@router",
        "create_task(",
        "Queue(",
        "pool_size",
        "pgbouncer",
        "polling_interval",
        "setInterval",
        "class MindscapeGraphService",
    ]

    for module in helper_modules:
        source = Path(module.__file__).read_text(encoding="utf-8")
        for marker in forbidden_markers:
            assert marker not in source

    overlay_source = Path(overlay.__file__).read_text(encoding="utf-8")
    assert overlay_source.count("save_overlay(") == 1
