import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


class GraphChangelogOperationMixin:
    def _apply_graph_operation(
        self,
        workspace_id: str,
        operation: str,
        target_type: str,
        target_id: str,
        state: Dict[str, Any],
    ) -> None:
        """
        Apply an operation to the actual graph store.

        This is the integration point with MindscapeGraphService.
        """
        try:
            from backend.app.services.mindscape_graph_service import (
                GraphOverlay,
                OverlayNode,
                MindscapeEdge,
                EdgeType,
                EdgeOrigin,
                NodeStatus,
            )
            from backend.app.services.stores.mindscape_overlay_store import (
                MindscapeOverlayStore,
            )

            overlay_store = MindscapeOverlayStore()

            if target_type == "node":
                # Get or create overlay
                overlay = overlay_store.get_overlay("workspace", workspace_id)
                if not overlay:
                    overlay = GraphOverlay()

                if operation == "create_node":
                    # Create new OverlayNode
                    new_node = OverlayNode(
                        id=state.get("id", target_id),
                        type=state.get("type", "intent"),
                        label=state.get("label", ""),
                        position=state.get(
                            "position", {"x": state.get("x", 0), "y": state.get("y", 0)}
                        ),
                        metadata=state.get("metadata", {}),
                    )
                    overlay.manual_nodes.append(new_node)
                    overlay_store.save_overlay("workspace", workspace_id, overlay)

                elif operation == "update_node":
                    # Update node position or rename
                    if "position" in state or ("x" in state and "y" in state):
                        pos = state.get(
                            "position", {"x": state.get("x", 0), "y": state.get("y", 0)}
                        )
                        overlay.node_positions[target_id] = pos
                    if "label" in state:
                        overlay.renames[target_id] = state["label"]
                    overlay_store.save_overlay("workspace", workspace_id, overlay)

                elif operation == "delete_node":
                    # Remove from manual nodes
                    overlay.manual_nodes = [
                        n for n in overlay.manual_nodes if n.id != target_id
                    ]
                    overlay_store.save_overlay("workspace", workspace_id, overlay)

            elif target_type == "edge":
                overlay = overlay_store.get_overlay("workspace", workspace_id)
                if not overlay:
                    overlay = GraphOverlay()

                if operation == "create_edge":
                    new_edge = MindscapeEdge(
                        id=state.get("id", target_id),
                        from_id=state.get("from_id", ""),
                        to_id=state.get("to_id", ""),
                        type=EdgeType(state.get("type", "related_to")),
                        origin=EdgeOrigin(state.get("origin", "manual")),
                        confidence=state.get("confidence", 1.0),
                        status=NodeStatus(state.get("status", "accepted")),
                        metadata=state.get("metadata", {}),
                    )
                    overlay.manual_edges.append(new_edge)
                    overlay_store.save_overlay("workspace", workspace_id, overlay)

                elif operation == "delete_edge":
                    overlay.manual_edges = [
                        e for e in overlay.manual_edges if e.id != target_id
                    ]
                    overlay_store.save_overlay("workspace", workspace_id, overlay)

            logger.info(
                f"Applied graph operation: {operation} on {target_type}:{target_id}"
            )
        except Exception as e:
            logger.error(f"Failed to apply graph operation: {e}")
            raise

    def _get_reverse_operation(self, operation: str) -> str:
        """Get the reverse operation for undo"""
        reverse_map = {
            "create_node": "delete_node",
            "delete_node": "create_node",
            "update_node": "update_node",
            "create_edge": "delete_edge",
            "delete_edge": "create_edge",
            "update_edge": "update_edge",
            "update_overlay": "update_overlay",
        }
        return reverse_map.get(operation, operation)
