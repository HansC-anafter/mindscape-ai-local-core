"""Overlay helpers for MindscapeGraphService."""

from __future__ import annotations

import logging
from typing import Any, Dict, Set

from backend.app.services.mindscape_graph_models import (
    EdgeOrigin,
    EdgeType,
    GraphOverlay,
    MindscapeEdge,
    MindscapeGraph,
    MindscapeNode,
    NodeStatus,
    OverlayNode,
    generate_edge_id,
)

logger = logging.getLogger(__name__)


async def load_overlay(service: Any, scope_type: str, scope_id: str) -> GraphOverlay:
    """Load overlay from storage."""
    cache_key = f"{scope_type}:{scope_id}"
    if cache_key in service._overlay_cache:
        return service._overlay_cache[cache_key]

    try:
        from .stores.mindscape_overlay_store import MindscapeOverlayStore

        store = MindscapeOverlayStore(service.db_path)
        overlay = store.get_overlay(scope_type, scope_id)
    except Exception as exc:
        logger.warning(f"Failed to load overlay (table may not exist): {exc}")
        overlay = None

    if overlay is None:
        overlay = GraphOverlay()

    service._overlay_cache[cache_key] = overlay
    return overlay


def apply_overlay(graph: MindscapeGraph, overlay: GraphOverlay) -> MindscapeGraph:
    """Apply overlay modifications to derived graph."""
    graph.overlay = overlay

    for manual_node in overlay.manual_nodes:
        graph.nodes.append(
            MindscapeNode(
                id=manual_node.id,
                type=manual_node.type,
                label=manual_node.label,
                status=NodeStatus.ACCEPTED,
                metadata=manual_node.metadata,
            )
        )

    graph.edges.extend(overlay.manual_edges)

    for node in graph.nodes:
        if node.id in overlay.node_status_overrides:
            node.status = NodeStatus(overlay.node_status_overrides[node.id])

    for edge in graph.edges:
        if edge.id in overlay.edge_status_overrides:
            edge.status = NodeStatus(overlay.edge_status_overrides[edge.id])

    for node in graph.nodes:
        if node.id in overlay.renames:
            node.label = overlay.renames[node.id]

    return graph


def canonicalize(graph: MindscapeGraph) -> MindscapeGraph:
    """Apply merge redirects to all graph and overlay references."""
    redirects = graph.overlay.merge_redirects
    if not redirects:
        return graph

    def redirect(node_id: str) -> str:
        visited: Set[str] = set()
        current = node_id
        while current in redirects and current not in visited:
            visited.add(current)
            current = redirects[current]
        return current

    canonical_nodes: Dict[str, MindscapeNode] = {}
    for node in graph.nodes:
        canonical_id = redirect(node.id)
        if canonical_id not in canonical_nodes:
            node.id = canonical_id
            canonical_nodes[canonical_id] = node

    graph.nodes = list(canonical_nodes.values())

    for edge in graph.edges:
        edge.from_id = redirect(edge.from_id)
        edge.to_id = redirect(edge.to_id)
        edge.id = generate_edge_id(edge.from_id, edge.to_id, edge.type.value)

    graph.overlay.node_positions = {
        redirect(key): value for key, value in graph.overlay.node_positions.items()
    }
    graph.overlay.collapsed_state = {
        redirect(key): value for key, value in graph.overlay.collapsed_state.items()
    }
    graph.overlay.renames = {
        redirect(key): value for key, value in graph.overlay.renames.items()
    }

    return graph


async def update_overlay(
    service: Any, scope_type: str, scope_id: str, updates: Dict[str, Any]
) -> GraphOverlay:
    """Update overlay with new modifications and persist it."""
    overlay = await load_overlay(service, scope_type, scope_id)

    if "node_positions" in updates:
        overlay.node_positions.update(updates["node_positions"])
    if "collapsed_state" in updates:
        overlay.collapsed_state.update(updates["collapsed_state"])
    if "viewport" in updates:
        overlay.viewport = updates["viewport"]
    if "renames" in updates:
        overlay.renames.update(updates["renames"])
    if "merge_redirects" in updates:
        overlay.merge_redirects.update(updates["merge_redirects"])
    if "node_status_overrides" in updates:
        overlay.node_status_overrides.update(updates["node_status_overrides"])
    if "edge_status_overrides" in updates:
        overlay.edge_status_overrides.update(updates["edge_status_overrides"])

    if "manual_nodes_add" in updates:
        for node_data in updates["manual_nodes_add"]:
            overlay.manual_nodes.append(
                OverlayNode(
                    id=node_data["id"],
                    type=node_data["type"],
                    label=node_data["label"],
                    position=node_data.get("position", {"x": 0, "y": 0}),
                    metadata=node_data.get("metadata", {}),
                )
            )
    if "manual_edges_add" in updates:
        for edge_data in updates["manual_edges_add"]:
            overlay.manual_edges.append(
                MindscapeEdge(
                    id=edge_data["id"],
                    from_id=edge_data["from_id"],
                    to_id=edge_data["to_id"],
                    type=EdgeType(edge_data["type"]),
                    origin=EdgeOrigin(edge_data.get("origin", "user")),
                    confidence=edge_data.get("confidence", 1.0),
                    status=NodeStatus(edge_data.get("status", "accepted")),
                    metadata=edge_data.get("metadata", {}),
                )
            )

    overlay.version += 1

    cache_key = f"{scope_type}:{scope_id}"
    service._overlay_cache[cache_key] = overlay

    from .stores.mindscape_overlay_store import MindscapeOverlayStore

    store = MindscapeOverlayStore(service.db_path)
    store.save_overlay(scope_type, scope_id, overlay)

    return overlay
