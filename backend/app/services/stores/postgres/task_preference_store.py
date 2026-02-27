"""PostgreSQL implementation of TaskPreferenceStore."""

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any
from sqlalchemy import text
from backend.app.services.stores.postgres_base import PostgresStoreBase
from backend.app.models.workspace import (
    TaskPreference,
    TaskPreferenceAction,
    TaskFeedbackAction,
)

logger = logging.getLogger(__name__)


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


class PostgresTaskPreferenceStore(PostgresStoreBase):
    """Postgres implementation of TaskPreferenceStore."""

    def create_or_update_preference(self, preference: TaskPreference) -> TaskPreference:
        """Create or update a preference record."""
        query = text(
            """
            INSERT INTO task_preference (
                id, workspace_id, user_id, pack_id, task_type, action,
                auto_suggest, last_feedback, reject_count_30d, accept_count_30d,
                created_at, updated_at
            ) VALUES (
                :id, :workspace_id, :user_id, :pack_id, :task_type, :action,
                :auto_suggest, :last_feedback, :reject_count_30d, :accept_count_30d,
                :created_at, :updated_at
            )
            ON CONFLICT (id) DO UPDATE SET
                action = EXCLUDED.action,
                auto_suggest = EXCLUDED.auto_suggest,
                last_feedback = EXCLUDED.last_feedback,
                reject_count_30d = EXCLUDED.reject_count_30d,
                accept_count_30d = EXCLUDED.accept_count_30d,
                updated_at = EXCLUDED.updated_at
        """
        )
        with self.transaction() as conn:
            conn.execute(
                query,
                {
                    "id": preference.id,
                    "workspace_id": preference.workspace_id,
                    "user_id": preference.user_id,
                    "pack_id": preference.pack_id,
                    "task_type": preference.task_type,
                    "action": preference.action.value,
                    "auto_suggest": preference.auto_suggest,
                    "last_feedback": (
                        preference.last_feedback.value
                        if preference.last_feedback
                        else None
                    ),
                    "reject_count_30d": preference.reject_count_30d,
                    "accept_count_30d": preference.accept_count_30d,
                    "created_at": preference.created_at,
                    "updated_at": preference.updated_at,
                },
            )
        return preference

    def get_preference(
        self,
        workspace_id: str,
        user_id: str,
        pack_id: Optional[str] = None,
        task_type: Optional[str] = None,
    ) -> Optional[TaskPreference]:
        """Get preference for a specific pack/task_type."""
        if task_type:
            query = text(
                "SELECT * FROM task_preference "
                "WHERE workspace_id = :workspace_id AND user_id = :user_id "
                "AND task_type = :task_type"
            )
            params = {
                "workspace_id": workspace_id,
                "user_id": user_id,
                "task_type": task_type,
            }
        elif pack_id:
            query = text(
                "SELECT * FROM task_preference "
                "WHERE workspace_id = :workspace_id AND user_id = :user_id "
                "AND pack_id = :pack_id AND task_type IS NULL"
            )
            params = {
                "workspace_id": workspace_id,
                "user_id": user_id,
                "pack_id": pack_id,
            }
        else:
            return None

        with self.get_connection() as conn:
            result = conn.execute(query, params)
            row = result.fetchone()
            if not row:
                return None
            return self._row_to_preference(row)

    def list_preferences_by_workspace(
        self,
        workspace_id: str,
        user_id: Optional[str] = None,
        pack_id: Optional[str] = None,
        auto_suggest_only: bool = False,
    ) -> List[TaskPreference]:
        """List preferences for a workspace."""
        base_query = "SELECT * FROM task_preference WHERE workspace_id = :workspace_id"
        params: Dict[str, Any] = {"workspace_id": workspace_id}

        if user_id:
            base_query += " AND user_id = :user_id"
            params["user_id"] = user_id

        if pack_id:
            base_query += " AND pack_id = :pack_id"
            params["pack_id"] = pack_id

        if auto_suggest_only:
            base_query += " AND auto_suggest = true"

        base_query += " ORDER BY updated_at DESC"

        with self.get_connection() as conn:
            result = conn.execute(text(base_query), params)
            rows = result.fetchall()
            return [self._row_to_preference(row) for row in rows]

    def update_preference_from_feedback(
        self,
        workspace_id: str,
        user_id: str,
        pack_id: str,
        task_type: Optional[str],
        feedback_action: TaskFeedbackAction,
    ) -> TaskPreference:
        """Update preference based on user feedback."""
        preference = self.get_preference(workspace_id, user_id, pack_id, task_type)

        if not preference:
            import uuid

            preference = TaskPreference(
                id=str(uuid.uuid4()),
                workspace_id=workspace_id,
                user_id=user_id,
                pack_id=pack_id,
                task_type=task_type,
                action=TaskPreferenceAction.AUTO_SUGGEST,
                auto_suggest=True,
                last_feedback=None,
                reject_count_30d=0,
                accept_count_30d=0,
                created_at=_utc_now(),
                updated_at=_utc_now(),
            )

        if feedback_action == TaskFeedbackAction.REJECT:
            preference.reject_count_30d += 1
        elif feedback_action == TaskFeedbackAction.ACCEPT:
            preference.accept_count_30d += 1

        preference.last_feedback = feedback_action
        preference.updated_at = _utc_now()

        total_feedback = preference.reject_count_30d + preference.accept_count_30d
        if total_feedback >= 3:
            reject_rate = preference.reject_count_30d / total_feedback
            if reject_rate > 0.5:
                preference.auto_suggest = False
                preference.action = TaskPreferenceAction.MANUAL_ONLY
            elif reject_rate < 0.3:
                preference.auto_suggest = True
                preference.action = TaskPreferenceAction.AUTO_SUGGEST

        return self.create_or_update_preference(preference)

    def should_auto_suggest(
        self,
        workspace_id: str,
        user_id: str,
        pack_id: str,
        task_type: Optional[str] = None,
    ) -> bool:
        """Check if a pack/task_type should be auto-suggested."""
        preference = self.get_preference(workspace_id, user_id, pack_id, task_type)
        if not preference:
            return True
        return preference.auto_suggest

    def get_rejection_rate(
        self,
        workspace_id: str,
        user_id: str,
        pack_id: str,
        task_type: Optional[str] = None,
    ) -> float:
        """Get rejection rate for a pack/task_type."""
        preference = self.get_preference(workspace_id, user_id, pack_id, task_type)
        if not preference:
            return 0.0
        total = preference.reject_count_30d + preference.accept_count_30d
        if total == 0:
            return 0.0
        return float(preference.reject_count_30d) / float(total)

    def cleanup_old_preferences(self, days: int = 90):
        """Clean up old preferences that haven't been updated."""
        threshold = _utc_now() - timedelta(days=days)
        query = text(
            "DELETE FROM task_preference "
            "WHERE updated_at < :threshold AND reject_count_30d = 0 AND accept_count_30d = 0"
        )
        with self.transaction() as conn:
            result = conn.execute(query, {"threshold": threshold})
            if result.rowcount > 0:
                logger.info(f"Cleaned up {result.rowcount} old preferences")

    def _row_to_preference(self, row) -> TaskPreference:
        """Convert database row to TaskPreference."""
        last_feedback = None
        if row.last_feedback:
            try:
                last_feedback = TaskFeedbackAction(row.last_feedback)
            except ValueError:
                logger.warning(f"Unknown last_feedback: {row.last_feedback}")

        return TaskPreference(
            id=row.id,
            workspace_id=row.workspace_id,
            user_id=row.user_id,
            pack_id=row.pack_id,
            task_type=row.task_type,
            action=TaskPreferenceAction(row.action),
            auto_suggest=bool(row.auto_suggest),
            last_feedback=last_feedback,
            reject_count_30d=row.reject_count_30d,
            accept_count_30d=row.accept_count_30d,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
