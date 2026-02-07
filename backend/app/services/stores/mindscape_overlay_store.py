"""
Mindscape Graph Overlay Store

Persists GraphOverlay data to PostgreSQL for workspace/group scopes.
Handles overlay versioning for cache invalidation.
"""

import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List, TYPE_CHECKING

from sqlalchemy import text

from app.services.stores.postgres_base import PostgresStoreBase

if TYPE_CHECKING:
    from backend.app.services.mindscape_graph_service import GraphOverlay

logger = logging.getLogger(__name__)


class MindscapeOverlayStore(PostgresStoreBase):
    """
    Store for persisting mindscape graph overlays.

    Schema:
    - mindscape_overlays: Main overlay data per scope
    """

    def __init__(self, db_path: Optional[str] = None, db_role: str = "core"):
        super().__init__(db_role=db_role)
        self.db_path = db_path
        self._ensure_schema()

    def _ensure_schema(self):
        """Ensure overlay table exists"""
        # Note: Table creation is handled by migrations
        # This is just a safety check
        pass

    def get_overlay(self, scope_type: str, scope_id: str) -> Optional["GraphOverlay"]:
        """
        Get overlay for scope.

        Args:
            scope_type: 'workspace' or 'workspace_group'
            scope_id: Workspace or group ID

        Returns:
            GraphOverlay or None if not found
        """
        with self.get_connection() as conn:
            result = conn.execute(
                text(
                    """
                    SELECT data, version FROM mindscape_overlays
                    WHERE scope_type = :scope_type AND scope_id = :scope_id
                """
                ),
                {"scope_type": scope_type, "scope_id": scope_id},
            ).fetchone()

            if not result:
                return None

            data = self.deserialize_json(result.data, {})
            overlay = self._deserialize_overlay(data)
            overlay.version = result.version
            return overlay

    def save_overlay(
        self, scope_type: str, scope_id: str, overlay: "GraphOverlay"
    ) -> "GraphOverlay":
        """
        Save or update overlay for scope.

        Args:
            scope_type: 'workspace' or 'workspace_group'
            scope_id: Workspace or group ID
            overlay: GraphOverlay to save

        Returns:
            Updated GraphOverlay with new version
        """
        now = datetime.utcnow()
        data = self._serialize_overlay(overlay)

        with self.transaction() as conn:
            # Check if exists
            result = conn.execute(
                text(
                    """
                    SELECT id, version FROM mindscape_overlays
                    WHERE scope_type = :scope_type AND scope_id = :scope_id
                """
                ),
                {"scope_type": scope_type, "scope_id": scope_id},
            ).fetchone()

            if result:
                # Update existing
                new_version = result.version + 1
                conn.execute(
                    text(
                        """
                        UPDATE mindscape_overlays
                        SET data = :data, version = :version, updated_at = :updated_at
                        WHERE id = :id
                    """
                    ),
                    {
                        "data": self.serialize_json(data),
                        "version": new_version,
                        "updated_at": now,
                        "id": result.id,
                    },
                )
                overlay.version = new_version
            else:
                # Create new
                import uuid

                overlay_id = str(uuid.uuid4())
                conn.execute(
                    text(
                        """
                        INSERT INTO mindscape_overlays
                        (id, scope_type, scope_id, data, version, created_at, updated_at)
                        VALUES (:id, :scope_type, :scope_id, :data, :version, :created_at, :updated_at)
                    """
                    ),
                    {
                        "id": overlay_id,
                        "scope_type": scope_type,
                        "scope_id": scope_id,
                        "data": self.serialize_json(data),
                        "version": 1,
                        "created_at": now,
                        "updated_at": now,
                    },
                )
                overlay.version = 1

        return overlay

    def delete_overlay(self, scope_type: str, scope_id: str) -> bool:
        """Delete overlay for scope"""
        with self.transaction() as conn:
            result = conn.execute(
                text(
                    """
                    DELETE FROM mindscape_overlays
                    WHERE scope_type = :scope_type AND scope_id = :scope_id
                """
                ),
                {"scope_type": scope_type, "scope_id": scope_id},
            )
            return result.rowcount > 0

    def _serialize_overlay(self, overlay: "GraphOverlay") -> Dict[str, Any]:
        """Serialize GraphOverlay to JSON-compatible dict"""
        return {
            "node_positions": overlay.node_positions,
            "collapsed_state": overlay.collapsed_state,
            "viewport": overlay.viewport,
            "renames": overlay.renames,
            "merge_redirects": overlay.merge_redirects,
            "manual_nodes": [
                {
                    "id": n.id,
                    "type": n.type,
                    "label": n.label,
                    "position": n.position,
                    "metadata": n.metadata,
                }
                for n in overlay.manual_nodes
            ],
            "manual_edges": [
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
                for e in overlay.manual_edges
            ],
            "node_status_overrides": overlay.node_status_overrides,
            "edge_status_overrides": overlay.edge_status_overrides,
        }

    def _deserialize_overlay(self, data: Dict[str, Any]) -> "GraphOverlay":
        """Deserialize JSON dict to GraphOverlay"""
        # Lazy import to avoid circular dependency
        from backend.app.services.mindscape_graph_service import (
            GraphOverlay,
            OverlayNode,
            MindscapeEdge,
            EdgeType,
            EdgeOrigin,
            NodeStatus,
        )

        manual_nodes = [
            OverlayNode(
                id=n["id"],
                type=n["type"],
                label=n["label"],
                position=n["position"],
                metadata=n.get("metadata", {}),
            )
            for n in data.get("manual_nodes", [])
        ]

        manual_edges = [
            MindscapeEdge(
                id=e["id"],
                from_id=e["from_id"],
                to_id=e["to_id"],
                type=EdgeType(e["type"]),
                origin=EdgeOrigin(e["origin"]),
                confidence=e.get("confidence", 1.0),
                status=NodeStatus(e["status"]),
                metadata=e.get("metadata", {}),
            )
            for e in data.get("manual_edges", [])
        ]

        return GraphOverlay(
            node_positions=data.get("node_positions", {}),
            collapsed_state=data.get("collapsed_state", {}),
            viewport=data.get("viewport"),
            renames=data.get("renames", {}),
            merge_redirects=data.get("merge_redirects", {}),
            manual_nodes=manual_nodes,
            manual_edges=manual_edges,
            node_status_overrides=data.get("node_status_overrides", {}),
            edge_status_overrides=data.get("edge_status_overrides", {}),
        )
