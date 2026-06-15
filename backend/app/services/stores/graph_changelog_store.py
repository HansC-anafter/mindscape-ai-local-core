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
from typing import Any, Dict, List, Optional

from app.services.stores.graph_changelog_models import (
    ChangelogEntry,
    decode_json_state,
    rows_to_changelog_entries,
)
from app.services.stores.graph_changelog_operations import GraphChangelogOperationMixin

logger = logging.getLogger(__name__)


class GraphChangelogStore(GraphChangelogOperationMixin):
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
            after_state = decode_json_state(row[6], {}) or {}

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

            before_state = decode_json_state(row[5])
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

            return rows_to_changelog_entries(rows)
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

            return rows_to_changelog_entries(rows)
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
