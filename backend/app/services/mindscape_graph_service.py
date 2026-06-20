"""Mindscape graph service facade."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from backend.app.services.mindscape_graph_derivation import (
    derive_edges,
    derive_from_artifacts,
    derive_from_executions,
    derive_from_reasoning_graph,
    derive_from_timeline,
    derive_graph,
    get_workspace_ids,
)
from backend.app.services.mindscape_graph_models import (
    DERIVATION_RULES,
    DerivationRule,
    EdgeOrigin,
    EdgeType,
    GraphOverlay,
    MindscapeEdge,
    MindscapeGraph,
    MindscapeNode,
    NodeIdPrefix,
    NodeStatus,
    OverlayNode,
    _normalize_datetime,
    generate_edge_id,
    generate_node_id,
)
from backend.app.services.mindscape_graph_overlay import (
    apply_overlay,
    canonicalize,
    load_overlay,
    update_overlay as update_overlay_helper,
)

logger = logging.getLogger(__name__)


class MindscapeGraphService:
    """
    Core service for mindscape graph operations.

    Implements derived graph creation, overlay merge, canonicalization, and
    overlay mutation through the canonical graph service path.
    """

    def __init__(self, db_path: str):
        """
        Initialize graph service.

        Args:
            db_path: Path to SQLite database
        """
        self.db_path = db_path
        self._overlay_cache: Dict[str, GraphOverlay] = {}
        logger.info(f"MindscapeGraphService initialized with db_path: {db_path}")

    async def get_graph(
        self,
        workspace_id: Optional[str] = None,
        workspace_group_id: Optional[str] = None,
    ) -> MindscapeGraph:
        """
        Get complete mindscape graph for workspace or group.

        Args:
            workspace_id: Single workspace ID
            workspace_group_id: Workspace group ID for aggregated view

        Returns:
            Complete MindscapeGraph with derived nodes/edges and overlay
        """
        if not workspace_id and not workspace_group_id:
            raise ValueError("Either workspace_id or workspace_group_id required")

        scope_type = "workspace" if workspace_id else "workspace_group"
        scope_id = workspace_id or workspace_group_id
        graph = await self._derive_graph(scope_type, scope_id)
        overlay = await self._load_overlay(scope_type, scope_id)
        graph = self._apply_overlay(graph, overlay)
        return self._canonicalize(graph)

    async def _derive_graph(self, scope_type: str, scope_id: str) -> MindscapeGraph:
        """Derive graph from existing data sources."""
        return await derive_graph(self, scope_type, scope_id)

    async def _get_workspace_ids(self, scope_type: str, scope_id: str) -> List[str]:
        """Get workspace IDs for the given scope."""
        return await get_workspace_ids(scope_type, scope_id)

    async def _derive_from_timeline(
        self, graph: MindscapeGraph, workspace_id: str, timeline_store: Any, tasks_store: Any
    ) -> None:
        """Derive intent nodes from timeline items."""
        await derive_from_timeline(graph, workspace_id, timeline_store, tasks_store)

    async def _derive_from_executions(
        self, graph: MindscapeGraph, workspace_id: str, tasks_store: Any
    ) -> None:
        """Derive execution nodes from tasks."""
        await derive_from_executions(graph, workspace_id, tasks_store)

    async def _derive_from_artifacts(
        self, graph: MindscapeGraph, workspace_id: str
    ) -> None:
        """Derive artifact nodes from artifact registry."""
        await derive_from_artifacts(graph, workspace_id)

    def derive_from_reasoning_graph(
        self,
        graph: MindscapeGraph,
        trace_id: str,
        reasoning_graph: Dict[str, Any],
    ) -> None:
        """Derive reasoning nodes and edges from an SGR reasoning graph."""
        derive_from_reasoning_graph(graph, trace_id, reasoning_graph)

    def _derive_edges(self, graph: MindscapeGraph) -> None:
        """Derive edges based on derivation rules."""
        derive_edges(graph)

    async def _load_overlay(self, scope_type: str, scope_id: str) -> GraphOverlay:
        """Load overlay from storage."""
        return await load_overlay(self, scope_type, scope_id)

    def _apply_overlay(
        self, graph: MindscapeGraph, overlay: GraphOverlay
    ) -> MindscapeGraph:
        """Apply overlay modifications to derived graph."""
        return apply_overlay(graph, overlay)

    def _canonicalize(self, graph: MindscapeGraph) -> MindscapeGraph:
        """Apply merge redirects to all references."""
        return canonicalize(graph)

    async def update_overlay(
        self, scope_type: str, scope_id: str, updates: Dict[str, Any]
    ) -> GraphOverlay:
        """
        Update overlay with new modifications.

        Args:
            scope_type: workspace or workspace_group
            scope_id: Workspace or group ID
            updates: Dict with overlay field updates

        Returns:
            Updated GraphOverlay
        """
        return await update_overlay_helper(self, scope_type, scope_id, updates)

    async def accept_node(self, scope_type: str, scope_id: str, node_id: str) -> bool:
        """Accept a suggested node."""
        await self.update_overlay(
            scope_type,
            scope_id,
            {"node_status_overrides": {node_id: NodeStatus.ACCEPTED.value}},
        )
        return True

    async def reject_node(self, scope_type: str, scope_id: str, node_id: str) -> bool:
        """Reject a suggested node."""
        await self.update_overlay(
            scope_type,
            scope_id,
            {"node_status_overrides": {node_id: NodeStatus.REJECTED.value}},
        )
        return True

    async def merge_nodes(
        self, scope_type: str, scope_id: str, source_node_id: str, target_node_id: str
    ) -> bool:
        """Merge source node into target by creating an alias redirect."""
        await self.update_overlay(
            scope_type, scope_id, {"merge_redirects": {source_node_id: target_node_id}}
        )
        return True
