"""
PlaybookExecutions store for managing playbook execution records

Provides persistent storage for playbook executions with checkpoint/resume support.
"""

import logging
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
from typing import List, Optional, Dict, Any
from backend.app.services.stores.base import StoreBase, StoreNotFoundError
from backend.app.models.workspace import PlaybookExecution

logger = logging.getLogger(__name__)


class PlaybookExecutionsStore(StoreBase):
    """Store for managing playbook execution records"""

    def create_execution(self, execution: PlaybookExecution) -> PlaybookExecution:
        """
        Create a new playbook execution record

        Args:
            execution: PlaybookExecution model instance

        Returns:
            Created execution
        """
        with self.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO playbook_executions (
                    id, workspace_id, playbook_code, intent_instance_id, thread_id,
                    status, phase, last_checkpoint, progress_log_path,
                    feature_list_path, metadata, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    execution.id,
                    execution.workspace_id,
                    execution.playbook_code,
                    execution.intent_instance_id,
                    execution.thread_id,
                    execution.status,
                    execution.phase,
                    execution.last_checkpoint,
                    execution.progress_log_path,
                    execution.feature_list_path,
                    (
                        self.serialize_json(execution.metadata)
                        if execution.metadata
                        else None
                    ),
                    self.to_isoformat(execution.created_at),
                    self.to_isoformat(execution.updated_at),
                ),
            )
            logger.info(
                f"Created playbook execution: {execution.id} (workspace: {execution.workspace_id}, playbook: {execution.playbook_code})"
            )
            return execution

    def get_execution(self, execution_id: str) -> Optional[PlaybookExecution]:
        """
        Get playbook execution by ID

        Args:
            execution_id: Execution ID

        Returns:
            PlaybookExecution model or None if not found
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM playbook_executions WHERE id = ?", (execution_id,)
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_execution(row)

    def update_checkpoint(
        self, execution_id: str, checkpoint_data: str, phase: Optional[str] = None
    ) -> bool:
        """
        Update checkpoint data for an execution

        Args:
            execution_id: Execution ID
            checkpoint_data: JSON checkpoint data
            phase: Current phase (optional)

        Returns:
            True if updated, False if execution not found
        """
        with self.transaction() as conn:
            cursor = conn.cursor()
            update_fields = ["last_checkpoint = ?", "updated_at = ?"]
            update_values = [checkpoint_data, self.to_isoformat(_utc_now())]

            if phase is not None:
                update_fields.append("phase = ?")
                update_values.append(phase)

            update_values.append(execution_id)

            cursor.execute(
                f"""
                UPDATE playbook_executions
                SET {", ".join(update_fields)}
                WHERE id = ?
            """,
                update_values,
            )

            if cursor.rowcount == 0:
                return False

            logger.info(f"Updated checkpoint for execution: {execution_id}")
            return True

    def add_phase_summary(
        self, execution_id: str, phase: str, summary_data: Dict[str, Any]
    ) -> bool:
        """
        Add phase summary to execution

        Args:
            execution_id: Execution ID
            phase: Phase ID
            summary_data: Summary data to append

        Returns:
            True if updated, False if execution not found
        """
        execution = self.get_execution(execution_id)
        if not execution:
            return False

        # Note: Phase summaries are stored in ExecutionSession.phase_summaries
        # This method updates the execution record timestamp
        with self.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE playbook_executions
                SET updated_at = ?
                WHERE id = ?
            """,
                (self.to_isoformat(_utc_now()), execution_id),
            )

            logger.info(
                f"Added phase summary for execution: {execution_id}, phase: {phase}"
            )
            return True

    def list_executions_by_workspace(
        self, workspace_id: str, limit: int = 50
    ) -> List[PlaybookExecution]:
        """
        List playbook executions for a workspace

        Args:
            workspace_id: Workspace ID
            limit: Maximum number of results

        Returns:
            List of PlaybookExecution models
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM playbook_executions
                WHERE workspace_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            """,
                (workspace_id, limit),
            )

            executions = []
            for row in cursor.fetchall():
                executions.append(self._row_to_execution(row))
            return executions

    def list_executions_by_intent(
        self, intent_instance_id: str, limit: int = 50
    ) -> List[PlaybookExecution]:
        """
        List playbook executions for an intent instance

        Args:
            intent_instance_id: Intent instance ID
            limit: Maximum number of results

        Returns:
            List of PlaybookExecution models
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM playbook_executions
                WHERE intent_instance_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            """,
                (intent_instance_id, limit),
            )

            executions = []
            for row in cursor.fetchall():
                executions.append(self._row_to_execution(row))
            return executions

    def get_by_thread(
        self, workspace_id: str, thread_id: str, limit: Optional[int] = 20
    ) -> List[PlaybookExecution]:
        """
        Get playbook executions for a specific conversation thread

        Args:
            workspace_id: Workspace ID
            thread_id: Thread ID
            limit: Maximum number of executions to return (default: 20)

        Returns:
            List of executions for the thread, ordered by created_at DESC
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM playbook_executions WHERE workspace_id = ? AND thread_id = ? ORDER BY created_at DESC"
            params = [workspace_id, thread_id]

            if limit:
                query += " LIMIT ?"
                params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [self._row_to_execution(row) for row in rows]

    def update_execution_status(
        self, execution_id: str, status: str, phase: Optional[str] = None
    ) -> bool:
        """
        Update execution status

        Args:
            execution_id: Execution ID
            status: New status
            phase: Current phase (optional)

        Returns:
            True if updated, False if execution not found
        """
        with self.transaction() as conn:
            cursor = conn.cursor()
            update_fields = ["status = ?", "updated_at = ?"]
            update_values = [status, self.to_isoformat(_utc_now())]

            if phase is not None:
                update_fields.append("phase = ?")
                update_values.append(phase)

            update_values.append(execution_id)

            cursor.execute(
                f"""
                UPDATE playbook_executions
                SET {", ".join(update_fields)}
                WHERE id = ?
            """,
                update_values,
            )

            if cursor.rowcount == 0:
                return False

            logger.info(f"Updated status for execution: {execution_id} to {status}")
            return True

    def mark_stale_running_executions(self) -> int:
        """
        Mark all running executions as stale on startup.

        This should be called during backend startup to clean up orphaned
        executions that were interrupted by a restart.

        Returns:
            Number of executions marked as stale
        """
        with self.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE playbook_executions
                SET status = 'stale', updated_at = ?
                WHERE status IN ('running', 'pending', 'initializing')
            """,
                (self.to_isoformat(_utc_now()),),
            )

            count = cursor.rowcount
            if count > 0:
                logger.warning(
                    f"Marked {count} orphaned running execution(s) as stale on startup"
                )
            return count

    def update_execution_metadata(
        self, execution_id: str, metadata: Dict[str, Any]
    ) -> bool:
        """
        Update execution metadata with BYOP/BYOL fields

        Args:
            execution_id: Execution ID
            metadata: Metadata dictionary to update

        Returns:
            True if updated, False if execution not found
        """
        with self.transaction() as conn:
            cursor = conn.cursor()

            # Get existing metadata
            cursor.execute(
                "SELECT metadata FROM playbook_executions WHERE id = ?", (execution_id,)
            )
            row = cursor.fetchone()
            if not row:
                return False

            # Merge with existing metadata
            existing_metadata = self.deserialize_json(row[0]) if row[0] else {}
            if existing_metadata:
                existing_metadata.update(metadata)
                merged_metadata = existing_metadata
            else:
                merged_metadata = metadata

            # Update metadata
            cursor.execute(
                """
                UPDATE playbook_executions
                SET metadata = ?, updated_at = ?
                WHERE id = ?
            """,
                (
                    self.serialize_json(merged_metadata),
                    self.to_isoformat(_utc_now()),
                    execution_id,
                ),
            )

            if cursor.rowcount == 0:
                return False

            logger.info(f"Updated metadata for execution: {execution_id}")
            return True

    def get_playbook_workspace_stats(self, playbook_code: str) -> Dict[str, Any]:
        """
        Get usage statistics for a specific playbook across all workspaces

        Args:
            playbook_code: Playbook code

        Returns:
            Dictionary with usage statistics:
            {
                "playbook_code": str,
                "total_executions": int,
                "total_workspaces": int,
                "workspace_stats": [
                    {
                        "workspace_id": str,
                        "execution_count": int,
                        "success_count": int,
                        "failed_count": int,
                        "running_count": int,
                        "last_executed_at": str (ISO format) or None
                    }
                ]
            }
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Get all executions for this playbook
            cursor.execute(
                """
                SELECT
                    workspace_id,
                    status,
                    created_at,
                    updated_at
                FROM playbook_executions
                WHERE playbook_code = ?
                ORDER BY created_at DESC
            """,
                (playbook_code,),
            )

            rows = cursor.fetchall()

            # Aggregate statistics by workspace
            workspace_stats_map: Dict[str, Dict[str, Any]] = {}
            total_executions = len(rows)

            for row in rows:
                workspace_id = row[0]
                status = row[1]
                created_at = row[2]
                updated_at = row[3]

                if workspace_id not in workspace_stats_map:
                    workspace_stats_map[workspace_id] = {
                        "workspace_id": workspace_id,
                        "execution_count": 0,
                        "success_count": 0,
                        "failed_count": 0,
                        "running_count": 0,
                        "last_executed_at": None,
                    }

                stats = workspace_stats_map[workspace_id]
                stats["execution_count"] += 1

                # Count by status
                if status in ["completed", "success"]:
                    stats["success_count"] += 1
                elif status in ["failed", "error"]:
                    stats["failed_count"] += 1
                elif status in ["running", "pending", "initializing"]:
                    stats["running_count"] += 1

                # Track most recent execution time
                if created_at:
                    created_dt = datetime.fromisoformat(created_at)
                    if stats["last_executed_at"] is None:
                        stats["last_executed_at"] = created_at
                    else:
                        existing_dt = datetime.fromisoformat(stats["last_executed_at"])
                        if created_dt > existing_dt:
                            stats["last_executed_at"] = created_at

            # Convert to list and sort by execution count (descending)
            workspace_stats = list(workspace_stats_map.values())
            workspace_stats.sort(key=lambda x: x["execution_count"], reverse=True)

            return {
                "playbook_code": playbook_code,
                "total_executions": total_executions,
                "total_workspaces": len(workspace_stats),
                "workspace_stats": workspace_stats,
            }

    def _row_to_execution(self, row: Dict[str, Any]) -> PlaybookExecution:
        """
        Convert database row to PlaybookExecution model

        Args:
            row: Database row as dict

        Returns:
            PlaybookExecution model
        """
        return PlaybookExecution(
            id=row["id"],
            workspace_id=row["workspace_id"],
            playbook_code=row["playbook_code"],
            intent_instance_id=row["intent_instance_id"],
            thread_id=(
                str(row["thread_id"])
                if "thread_id" in row.keys() and row["thread_id"]
                else None
            ),
            status=row["status"],
            phase=row["phase"],
            last_checkpoint=row["last_checkpoint"],
            progress_log_path=row["progress_log_path"],
            feature_list_path=row["feature_list_path"],
            metadata=(
                self.deserialize_json(row["metadata"])
                if "metadata" in row.keys() and row["metadata"]
                else None
            ),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
