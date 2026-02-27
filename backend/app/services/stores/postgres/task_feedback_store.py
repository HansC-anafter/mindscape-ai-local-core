"""PostgreSQL implementation of TaskFeedbackStore."""

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any
from sqlalchemy import text
from backend.app.services.stores.postgres_base import PostgresStoreBase
from backend.app.models.workspace import (
    TaskFeedback,
    TaskFeedbackAction,
    TaskFeedbackReasonCode,
)

logger = logging.getLogger(__name__)


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


class PostgresTaskFeedbackStore(PostgresStoreBase):
    """Postgres implementation of TaskFeedbackStore."""

    def create_feedback(self, feedback: TaskFeedback) -> TaskFeedback:
        """Create a new feedback record."""
        query = text(
            """
            INSERT INTO task_feedback (
                id, task_id, workspace_id, user_id, action,
                reason_code, comment, created_at
            ) VALUES (
                :id, :task_id, :workspace_id, :user_id, :action,
                :reason_code, :comment, :created_at
            )
        """
        )
        with self.transaction() as conn:
            conn.execute(
                query,
                {
                    "id": feedback.id,
                    "task_id": feedback.task_id,
                    "workspace_id": feedback.workspace_id,
                    "user_id": feedback.user_id,
                    "action": feedback.action.value,
                    "reason_code": (
                        feedback.reason_code.value if feedback.reason_code else None
                    ),
                    "comment": feedback.comment,
                    "created_at": feedback.created_at,
                },
            )
        return feedback

    def get_feedback(self, feedback_id: str) -> Optional[TaskFeedback]:
        """Get feedback by ID."""
        query = text("SELECT * FROM task_feedback WHERE id = :id")
        with self.get_connection() as conn:
            result = conn.execute(query, {"id": feedback_id})
            row = result.fetchone()
            if not row:
                return None
            return self._row_to_feedback(row)

    def get_feedback_by_task(self, task_id: str) -> Optional[TaskFeedback]:
        """Get feedback for a specific task (most recent)."""
        query = text(
            "SELECT * FROM task_feedback WHERE task_id = :task_id "
            "ORDER BY created_at DESC LIMIT 1"
        )
        with self.get_connection() as conn:
            result = conn.execute(query, {"task_id": task_id})
            row = result.fetchone()
            if not row:
                return None
            return self._row_to_feedback(row)

    def list_feedback_by_workspace(
        self,
        workspace_id: str,
        action: Optional[TaskFeedbackAction] = None,
        pack_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[TaskFeedback]:
        """List feedback records for a workspace."""
        params: Dict[str, Any] = {"workspace_id": workspace_id}

        if pack_id:
            base_query = (
                "SELECT tf.* FROM task_feedback tf "
                "INNER JOIN tasks t ON tf.task_id = t.id "
                "WHERE tf.workspace_id = :workspace_id AND t.pack_id = :pack_id"
            )
            params["pack_id"] = pack_id
        else:
            base_query = (
                "SELECT * FROM task_feedback WHERE workspace_id = :workspace_id"
            )

        if action:
            base_query += " AND action = :action"
            params["action"] = action.value

        base_query += " ORDER BY created_at DESC"

        if limit:
            base_query += " LIMIT :limit"
            params["limit"] = limit

        with self.get_connection() as conn:
            result = conn.execute(text(base_query), params)
            rows = result.fetchall()
            return [self._row_to_feedback(row) for row in rows]

    def get_reject_count_by_pack(
        self, workspace_id: str, pack_id: str, days: int = 30
    ) -> int:
        """Get count of rejections for a specific pack within time window."""
        threshold = _utc_now() - timedelta(days=days)
        query = text(
            """
            SELECT COUNT(*) as cnt FROM task_feedback tf
            INNER JOIN tasks t ON tf.task_id = t.id
            WHERE tf.workspace_id = :workspace_id
            AND t.pack_id = :pack_id
            AND tf.action = :action
            AND tf.created_at >= :threshold
        """
        )
        with self.get_connection() as conn:
            result = conn.execute(
                query,
                {
                    "workspace_id": workspace_id,
                    "pack_id": pack_id,
                    "action": TaskFeedbackAction.REJECT.value,
                    "threshold": threshold,
                },
            )
            row = result.fetchone()
            return row.cnt if row else 0

    def get_reject_rate_by_pack(
        self, workspace_id: str, pack_id: str, days: int = 30
    ) -> float:
        """Get rejection rate for a specific pack within time window."""
        threshold = _utc_now() - timedelta(days=days)
        query = text(
            """
            SELECT
                SUM(CASE WHEN tf.action = :reject_action THEN 1 ELSE 0 END) as reject_count,
                COUNT(*) as total_count
            FROM task_feedback tf
            INNER JOIN tasks t ON tf.task_id = t.id
            WHERE tf.workspace_id = :workspace_id
            AND t.pack_id = :pack_id
            AND tf.created_at >= :threshold
        """
        )
        with self.get_connection() as conn:
            result = conn.execute(
                query,
                {
                    "reject_action": TaskFeedbackAction.REJECT.value,
                    "workspace_id": workspace_id,
                    "pack_id": pack_id,
                    "threshold": threshold,
                },
            )
            row = result.fetchone()
            if not row or row.total_count == 0:
                return 0.0
            return float(row.reject_count) / float(row.total_count)

    def _row_to_feedback(self, row) -> TaskFeedback:
        """Convert database row to TaskFeedback."""
        reason_code = None
        if row.reason_code:
            try:
                reason_code = TaskFeedbackReasonCode(row.reason_code)
            except ValueError:
                logger.warning(f"Unknown reason_code: {row.reason_code}")

        return TaskFeedback(
            id=row.id,
            task_id=row.task_id,
            workspace_id=row.workspace_id,
            user_id=row.user_id,
            action=TaskFeedbackAction(row.action),
            reason_code=reason_code,
            comment=row.comment,
            created_at=row.created_at,
        )
