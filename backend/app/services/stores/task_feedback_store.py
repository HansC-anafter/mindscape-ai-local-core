"""
Task feedback store for managing user feedback on AI-generated tasks

Tracks user rejections, dismissals, and acceptances to improve
task recommendation strategies and personalize preferences.
"""

import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from .base import StoreBase, StoreNotFoundError
from ...models.workspace import TaskFeedback, TaskFeedbackAction, TaskFeedbackReasonCode

logger = logging.getLogger(__name__)


class TaskFeedbackStore(StoreBase):
    """Store for managing task feedback records"""

    def create_feedback(self, feedback: TaskFeedback) -> TaskFeedback:
        """
        Create a new feedback record

        Args:
            feedback: TaskFeedback model instance

        Returns:
            Created feedback
        """
        with self.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO task_feedback (
                    id, task_id, workspace_id, user_id, action,
                    reason_code, comment, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                feedback.id,
                feedback.task_id,
                feedback.workspace_id,
                feedback.user_id,
                feedback.action.value,
                feedback.reason_code.value if feedback.reason_code else None,
                feedback.comment,
                self.to_isoformat(feedback.created_at)
            ))
            logger.info(f"Created feedback: {feedback.id} (task: {feedback.task_id}, action: {feedback.action.value})")
            return feedback

    def get_feedback(self, feedback_id: str) -> Optional[TaskFeedback]:
        """
        Get feedback by ID

        Args:
            feedback_id: Feedback ID

        Returns:
            TaskFeedback model or None if not found
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM task_feedback WHERE id = ?', (feedback_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_feedback(row)

    def get_feedback_by_task(self, task_id: str) -> Optional[TaskFeedback]:
        """
        Get feedback for a specific task (most recent)

        Args:
            task_id: Task ID

        Returns:
            Most recent TaskFeedback or None if not found
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT * FROM task_feedback WHERE task_id = ? ORDER BY created_at DESC LIMIT 1',
                (task_id,)
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_feedback(row)

    def list_feedback_by_workspace(
        self,
        workspace_id: str,
        action: Optional[TaskFeedbackAction] = None,
        pack_id: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[TaskFeedback]:
        """
        List feedback records for a workspace

        Args:
            workspace_id: Workspace ID
            action: Filter by action type (optional)
            pack_id: Filter by pack_id (requires join with tasks table, optional)
            limit: Maximum number of records to return (optional)

        Returns:
            List of feedback records
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            if pack_id:
                query = '''
                    SELECT tf.* FROM task_feedback tf
                    INNER JOIN tasks t ON tf.task_id = t.id
                    WHERE tf.workspace_id = ? AND t.pack_id = ?
                '''
                params = [workspace_id, pack_id]
            else:
                query = 'SELECT * FROM task_feedback WHERE workspace_id = ?'
                params = [workspace_id]

            if action:
                query += ' AND action = ?'
                params.append(action.value)

            query += ' ORDER BY created_at DESC'

            if limit:
                query += ' LIMIT ?'
                params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [self._row_to_feedback(row) for row in rows]

    def get_reject_count_by_pack(
        self,
        workspace_id: str,
        pack_id: str,
        days: int = 30
    ) -> int:
        """
        Get count of rejections for a specific pack within time window

        Args:
            workspace_id: Workspace ID
            pack_id: Pack ID
            days: Number of days to look back (default: 30)

        Returns:
            Count of rejections
        """
        from datetime import timedelta
        with self.get_connection() as conn:
            cursor = conn.cursor()

            time_threshold = datetime.utcnow() - timedelta(days=days)

            query = '''
                SELECT COUNT(*) FROM task_feedback tf
                INNER JOIN tasks t ON tf.task_id = t.id
                WHERE tf.workspace_id = ?
                AND t.pack_id = ?
                AND tf.action = ?
                AND tf.created_at >= ?
            '''

            cursor.execute(query, (
                workspace_id,
                pack_id,
                TaskFeedbackAction.REJECT.value,
                self.to_isoformat(time_threshold)
            ))

            row = cursor.fetchone()
            return row[0] if row else 0

    def get_reject_rate_by_pack(
        self,
        workspace_id: str,
        pack_id: str,
        days: int = 30
    ) -> float:
        """
        Get rejection rate for a specific pack within time window

        Args:
            workspace_id: Workspace ID
            pack_id: Pack ID
            days: Number of days to look back (default: 30)

        Returns:
            Rejection rate (0.0 to 1.0), or 0.0 if no feedback
        """
        from datetime import timedelta
        with self.get_connection() as conn:
            cursor = conn.cursor()

            time_threshold = datetime.utcnow() - timedelta(days=days)

            query = '''
                SELECT
                    SUM(CASE WHEN tf.action = ? THEN 1 ELSE 0 END) as reject_count,
                    COUNT(*) as total_count
                FROM task_feedback tf
                INNER JOIN tasks t ON tf.task_id = t.id
                WHERE tf.workspace_id = ?
                AND t.pack_id = ?
                AND tf.created_at >= ?
            '''

            cursor.execute(query, (
                TaskFeedbackAction.REJECT.value,
                workspace_id,
                pack_id,
                self.to_isoformat(time_threshold)
            ))

            row = cursor.fetchone()
            if not row or row[1] == 0:
                return 0.0

            return float(row[0]) / float(row[1])

    def _row_to_feedback(self, row) -> TaskFeedback:
        """Convert database row to TaskFeedback model"""
        reason_code = None
        if row['reason_code']:
            try:
                reason_code = TaskFeedbackReasonCode(row['reason_code'])
            except ValueError:
                logger.warning(f"Unknown reason_code: {row['reason_code']}")

        return TaskFeedback(
            id=row['id'],
            task_id=row['task_id'],
            workspace_id=row['workspace_id'],
            user_id=row['user_id'],
            action=TaskFeedbackAction(row['action']),
            reason_code=reason_code,
            comment=row['comment'],
            created_at=self.from_isoformat(row['created_at'])
        )

