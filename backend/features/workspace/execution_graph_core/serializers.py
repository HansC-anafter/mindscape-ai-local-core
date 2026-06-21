"""Serializers for execution graph responses."""

from backend.app.services.mindscape_graph_service import MindscapeGraph
from backend.features.workspace.execution_graph_core.models import GraphResponse


def build_graph_response(graph: MindscapeGraph) -> GraphResponse:
    """Build an API graph response from a Mindscape graph."""
    return GraphResponse(
        nodes=[
            {
                "id": node.id,
                "type": node.type,
                "label": node.label,
                "status": node.status.value,
                "metadata": node.metadata,
                "created_at": (
                    node.created_at.isoformat() if node.created_at else None
                ),
            }
            for node in graph.nodes
        ],
        edges=[
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
            for edge in graph.edges
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
