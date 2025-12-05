"""
PlaybookExecutions store for managing playbook execution records

Provides persistent storage for playbook executions with checkpoint/resume support.
"""

import logging
from datetime import datetime
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
            cursor.execute('''
                INSERT INTO playbook_executions (
                    id, workspace_id, playbook_code, intent_instance_id,
                    status, phase, last_checkpoint, progress_log_path,
                    feature_list_path, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                execution.id,
                execution.workspace_id,
                execution.playbook_code,
                execution.intent_instance_id,
                execution.status,
                execution.phase,
                execution.last_checkpoint,
                execution.progress_log_path,
                execution.feature_list_path,
                self.to_isoformat(execution.created_at),
                self.to_isoformat(execution.updated_at)
            ))
            logger.info(f"Created playbook execution: {execution.id} (workspace: {execution.workspace_id}, playbook: {execution.playbook_code})")
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
            cursor.execute('SELECT * FROM playbook_executions WHERE id = ?', (execution_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_execution(row)

    def update_checkpoint(self, execution_id: str, checkpoint_data: str, phase: Optional[str] = None) -> bool:
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
            update_values = [checkpoint_data, self.to_isoformat(datetime.utcnow())]

            if phase is not None:
                update_fields.append("phase = ?")
                update_values.append(phase)

            update_values.append(execution_id)

            cursor.execute(f'''
                UPDATE playbook_executions
                SET {", ".join(update_fields)}
                WHERE id = ?
            ''', update_values)

            if cursor.rowcount == 0:
                return False

            logger.info(f"Updated checkpoint for execution: {execution_id}")
            return True

    def add_phase_summary(self, execution_id: str, phase: str, summary_data: Dict[str, Any]) -> bool:
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
            cursor.execute('''
                UPDATE playbook_executions
                SET updated_at = ?
                WHERE id = ?
            ''', (self.to_isoformat(datetime.utcnow()), execution_id))

            logger.info(f"Added phase summary for execution: {execution_id}, phase: {phase}")
            return True

    def list_executions_by_workspace(self, workspace_id: str, limit: int = 50) -> List[PlaybookExecution]:
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
            cursor.execute('''
                SELECT * FROM playbook_executions
                WHERE workspace_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            ''', (workspace_id, limit))

            executions = []
            for row in cursor.fetchall():
                executions.append(self._row_to_execution(row))
            return executions

    def list_executions_by_intent(self, intent_instance_id: str, limit: int = 50) -> List[PlaybookExecution]:
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
            cursor.execute('''
                SELECT * FROM playbook_executions
                WHERE intent_instance_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            ''', (intent_instance_id, limit))

            executions = []
            for row in cursor.fetchall():
                executions.append(self._row_to_execution(row))
            return executions

    def update_execution_status(self, execution_id: str, status: str, phase: Optional[str] = None) -> bool:
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
            update_values = [status, self.to_isoformat(datetime.utcnow())]

            if phase is not None:
                update_fields.append("phase = ?")
                update_values.append(phase)

            update_values.append(execution_id)

            cursor.execute(f'''
                UPDATE playbook_executions
                SET {", ".join(update_fields)}
                WHERE id = ?
            ''', update_values)

            if cursor.rowcount == 0:
                return False

            logger.info(f"Updated status for execution: {execution_id} to {status}")
            return True

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
            status=row["status"],
            phase=row["phase"],
            last_checkpoint=row["last_checkpoint"],
            progress_log_path=row["progress_log_path"],
            feature_list_path=row["feature_list_path"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"])
        )
