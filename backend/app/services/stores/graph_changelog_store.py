"""
Graph Changelog Store

Implements Event Sourcing for the Mindscape Graph, tracking every atomic
operation for undo/redo and time-travel support.

Usage:
    store = GraphChangelogStore()

    # Create a pending change
    change_id = store.create_pending_change(
        workspace_id="ws-123",
        operation="create_node",
        target_type="node",
        target_id="node-456",
        after_state={"label": "New Node", "type": "intent"},
        actor="llm",
        actor_context="conversation:abc123"
    )

    # Apply the change
    store.apply_change(change_id, applied_by="profile-789")

    # Undo a change
    store.undo_change(change_id)

    # Get history
    history = store.get_history(workspace_id="ws-123")
"""

import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ChangelogEntry:
    """A single changelog entry"""

    id: str
    workspace_id: str
    version: int
    operation: str
    target_type: str
    target_id: str
    after_state: Dict[str, Any]
    actor: str
    status: str = "pending"
    before_state: Optional[Dict[str, Any]] = None
    actor_context: Optional[str] = None
    created_at: Optional[datetime] = None
    applied_at: Optional[datetime] = None
    applied_by: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "version": self.version,
            "operation": self.operation,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "before_state": self.before_state,
            "after_state": self.after_state,
            "actor": self.actor,
            "actor_context": self.actor_context,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "applied_at": self.applied_at.isoformat() if self.applied_at else None,
            "applied_by": self.applied_by,
        }


class GraphChangelogStore:
    """
    Graph Changelog Store - Event Sourcing for Mindscape Graph

    Tracks every atomic operation on the graph for:
    - Audit trail
    - Undo/Redo functionality
    - Time-travel to previous versions
    - LLM change approval workflow
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize the changelog store.

        Args:
            db_path: Optional path to SQLite database (for local dev).
                     If None, uses PostgreSQL from environment.
        """
        self.db_path = db_path
        self._connection = None

    def _get_postgres_connection(self):
        """Get PostgreSQL connection"""
        try:
            import psycopg2
            from backend.app.database.config import get_core_postgres_config

            config = get_core_postgres_config()
            return psycopg2.connect(**config)
        except Exception as e:
            logger.warning(f"Failed to get PostgreSQL connection: {e}")
            return None

    def _get_next_version(self, workspace_id: str) -> int:
        """Get the next version number for a workspace"""
        conn = self._get_postgres_connection()
        if not conn:
            return 1

        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT COALESCE(MAX(version), 0) + 1
                FROM graph_changelog
                WHERE workspace_id = %s
                """,
                (workspace_id,),
            )
            result = cursor.fetchone()
            return result[0] if result else 1
        except Exception as e:
            logger.error(f"Failed to get next version: {e}")
            return 1
        finally:
            conn.close()

    def create_pending_change(
        self,
        workspace_id: str,
        operation: str,
        target_type: str,
        target_id: str,
        after_state: Dict[str, Any],
        actor: str,
        actor_context: str = "",
        before_state: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Create a pending change entry.

        Args:
            workspace_id: Workspace ID
            operation: Operation type (create_node, update_node, etc.)
            target_type: Target type (node, edge, overlay)
            target_id: ID of the affected entity
            after_state: State after the change (JSON-serializable)
            actor: Actor type (user, llm, system, playbook)
            actor_context: Additional context (conversation ID, etc.)
            before_state: State before the change (for undo support)

        Returns:
            Change ID (UUID)
        """
        conn = self._get_postgres_connection()
        if not conn:
            raise RuntimeError("Database connection not available")

        change_id = str(uuid.uuid4())
        version = self._get_next_version(workspace_id)

        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO graph_changelog (
                    id, workspace_id, version, operation, target_type, target_id,
                    before_state, after_state, actor, actor_context, status, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending', NOW()
                )
                """,
                (
                    change_id,
                    workspace_id,
                    version,
                    operation,
                    target_type,
                    target_id,
                    json.dumps(before_state) if before_state else None,
                    json.dumps(after_state),
                    actor,
                    actor_context or None,
                ),
            )
            conn.commit()
            logger.info(
                f"Created pending change {change_id} for {operation} on {target_type}:{target_id}"
            )
            return change_id
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to create pending change: {e}")
            raise
        finally:
            conn.close()

    def apply_change(
        self,
        change_id: str,
        applied_by: str,
    ) -> Dict[str, Any]:
        """
        Apply a pending change.

        Args:
            change_id: Change ID to apply
            applied_by: Profile ID of the approver

        Returns:
            Result dict with success status and applied change details
        """
        conn = self._get_postgres_connection()
        if not conn:
            raise RuntimeError("Database connection not available")

        try:
            cursor = conn.cursor()

            # Get the pending change
            cursor.execute(
                """
                SELECT id, workspace_id, operation, target_type, target_id,
                       before_state, after_state, status
                FROM graph_changelog
                WHERE id = %s
                """,
                (change_id,),
            )
            row = cursor.fetchone()

            if not row:
                return {"success": False, "error": "Change not found"}

            if row[7] != "pending":
                return {
                    "success": False,
                    "error": f"Change is not pending (status: {row[7]})",
                }

            workspace_id = row[1]
            operation = row[2]
            target_type = row[3]
            target_id = row[4]
            after_state = json.loads(row[6]) if row[6] else {}

            # Apply the actual change to the graph
            self._apply_graph_operation(
                workspace_id=workspace_id,
                operation=operation,
                target_type=target_type,
                target_id=target_id,
                state=after_state,
            )

            # Update changelog status
            cursor.execute(
                """
                UPDATE graph_changelog
                SET status = 'applied', applied_at = NOW(), applied_by = %s
                WHERE id = %s
                """,
                (applied_by, change_id),
            )
            conn.commit()

            logger.info(f"Applied change {change_id} by {applied_by}")
            return {
                "success": True,
                "change_id": change_id,
                "operation": operation,
                "target_id": target_id,
            }
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to apply change: {e}")
            return {"success": False, "error": str(e)}
        finally:
            conn.close()

    def reject_change(self, change_id: str) -> Dict[str, Any]:
        """
        Reject a pending change.

        Args:
            change_id: Change ID to reject

        Returns:
            Result dict
        """
        conn = self._get_postgres_connection()
        if not conn:
            raise RuntimeError("Database connection not available")

        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE graph_changelog
                SET status = 'rejected'
                WHERE id = %s AND status = 'pending'
                RETURNING id
                """,
                (change_id,),
            )
            result = cursor.fetchone()
            conn.commit()

            if result:
                logger.info(f"Rejected change {change_id}")
                return {"success": True, "change_id": change_id}
            else:
                return {"success": False, "error": "Change not found or not pending"}
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to reject change: {e}")
            return {"success": False, "error": str(e)}
        finally:
            conn.close()

    def undo_change(self, change_id: str) -> Dict[str, Any]:
        """
        Undo an applied change using before_state.

        Args:
            change_id: Change ID to undo

        Returns:
            Result dict
        """
        conn = self._get_postgres_connection()
        if not conn:
            raise RuntimeError("Database connection not available")

        try:
            cursor = conn.cursor()

            # Get the applied change
            cursor.execute(
                """
                SELECT id, workspace_id, operation, target_type, target_id,
                       before_state, after_state, status
                FROM graph_changelog
                WHERE id = %s
                """,
                (change_id,),
            )
            row = cursor.fetchone()

            if not row:
                return {"success": False, "error": "Change not found"}

            if row[7] != "applied":
                return {
                    "success": False,
                    "error": f"Change is not applied (status: {row[7]})",
                }

            before_state = json.loads(row[5]) if row[5] else None
            if before_state is None:
                return {"success": False, "error": "No before_state available for undo"}

            workspace_id = row[1]
            operation = row[2]
            target_type = row[3]
            target_id = row[4]

            # Apply the reverse operation
            reverse_op = self._get_reverse_operation(operation)
            self._apply_graph_operation(
                workspace_id=workspace_id,
                operation=reverse_op,
                target_type=target_type,
                target_id=target_id,
                state=before_state,
            )

            # Update changelog status
            cursor.execute(
                """
                UPDATE graph_changelog
                SET status = 'undone'
                WHERE id = %s
                """,
                (change_id,),
            )
            conn.commit()

            logger.info(f"Undid change {change_id}")
            return {"success": True, "change_id": change_id}
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to undo change: {e}")
            return {"success": False, "error": str(e)}
        finally:
            conn.close()

    def get_pending_changes(
        self,
        workspace_id: str,
        actor: Optional[str] = None,
    ) -> List[ChangelogEntry]:
        """
        Get all pending changes for a workspace.

        Args:
            workspace_id: Workspace ID
            actor: Optional filter by actor type

        Returns:
            List of pending ChangelogEntry objects
        """
        conn = self._get_postgres_connection()
        if not conn:
            return []

        try:
            cursor = conn.cursor()
            query = """
                SELECT id, workspace_id, version, operation, target_type, target_id,
                       before_state, after_state, actor, actor_context, status,
                       created_at, applied_at, applied_by
                FROM graph_changelog
                WHERE workspace_id = %s AND status = 'pending'
            """
            params = [workspace_id]

            if actor:
                query += " AND actor = %s"
                params.append(actor)

            query += " ORDER BY version ASC"

            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()

            entries = []
            for row in rows:
                entries.append(
                    ChangelogEntry(
                        id=row[0],
                        workspace_id=row[1],
                        version=row[2],
                        operation=row[3],
                        target_type=row[4],
                        target_id=row[5],
                        before_state=json.loads(row[6]) if row[6] else None,
                        after_state=json.loads(row[7]) if row[7] else {},
                        actor=row[8],
                        actor_context=row[9],
                        status=row[10],
                        created_at=row[11],
                        applied_at=row[12],
                        applied_by=row[13],
                    )
                )
            return entries
        except Exception as e:
            logger.error(f"Failed to get pending changes: {e}")
            return []
        finally:
            conn.close()

    def get_history(
        self,
        workspace_id: str,
        limit: int = 50,
        include_pending: bool = False,
        include_rejected: bool = False,
    ) -> List[ChangelogEntry]:
        """
        Get changelog history for a workspace.

        Args:
            workspace_id: Workspace ID
            limit: Maximum number of entries
            include_pending: Include pending changes
            include_rejected: Include rejected changes

        Returns:
            List of ChangelogEntry objects, newest first
        """
        conn = self._get_postgres_connection()
        if not conn:
            return []

        try:
            cursor = conn.cursor()

            statuses = ["'applied'", "'undone'"]
            if include_pending:
                statuses.append("'pending'")
            if include_rejected:
                statuses.append("'rejected'")

            query = f"""
                SELECT id, workspace_id, version, operation, target_type, target_id,
                       before_state, after_state, actor, actor_context, status,
                       created_at, applied_at, applied_by
                FROM graph_changelog
                WHERE workspace_id = %s AND status IN ({','.join(statuses)})
                ORDER BY version DESC
                LIMIT %s
            """

            cursor.execute(query, (workspace_id, limit))
            rows = cursor.fetchall()

            entries = []
            for row in rows:
                entries.append(
                    ChangelogEntry(
                        id=row[0],
                        workspace_id=row[1],
                        version=row[2],
                        operation=row[3],
                        target_type=row[4],
                        target_id=row[5],
                        before_state=json.loads(row[6]) if row[6] else None,
                        after_state=json.loads(row[7]) if row[7] else {},
                        actor=row[8],
                        actor_context=row[9],
                        status=row[10],
                        created_at=row[11],
                        applied_at=row[12],
                        applied_by=row[13],
                    )
                )
            return entries
        except Exception as e:
            logger.error(f"Failed to get history: {e}")
            return []
        finally:
            conn.close()

    def get_current_version(self, workspace_id: str) -> int:
        """Get the current applied version for a workspace"""
        conn = self._get_postgres_connection()
        if not conn:
            return 0

        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT COALESCE(MAX(version), 0)
                FROM graph_changelog
                WHERE workspace_id = %s AND status = 'applied'
                """,
                (workspace_id,),
            )
            result = cursor.fetchone()
            return result[0] if result else 0
        except Exception as e:
            logger.error(f"Failed to get current version: {e}")
            return 0
        finally:
            conn.close()

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
            "update_node": "update_node",  # Uses before_state
            "create_edge": "delete_edge",
            "delete_edge": "create_edge",
            "update_edge": "update_edge",
            "update_overlay": "update_overlay",
        }
        return reverse_map.get(operation, operation)
