"""
Task preference store for managing user preferences on task types and packs

Tracks user preferences to personalize task recommendations and
automatically adjust suggestion strategies based on feedback.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from .base import StoreBase, StoreNotFoundError
from ...models.workspace import (
    TaskPreference, TaskPreferenceAction, TaskFeedbackAction
)

logger = logging.getLogger(__name__)


class TaskPreferenceStore(StoreBase):
    """Store for managing task preference records"""

    def create_or_update_preference(
        self,
        preference: TaskPreference
    ) -> TaskPreference:
        """
        Create or update a preference record

        Uses INSERT OR REPLACE to handle unique constraint on (workspace_id, user_id, pack_id, task_type)

        Args:
            preference: TaskPreference model instance

        Returns:
            Created or updated preference
        """
        with self.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO task_preference (
                    id, workspace_id, user_id, pack_id, task_type, action,
                    auto_suggest, last_feedback, reject_count_30d, accept_count_30d,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                preference.id,
                preference.workspace_id,
                preference.user_id,
                preference.pack_id,
                preference.task_type,
                preference.action.value,
                1 if preference.auto_suggest else 0,
                preference.last_feedback.value if preference.last_feedback else None,
                preference.reject_count_30d,
                preference.accept_count_30d,
                self.to_isoformat(preference.created_at),
                self.to_isoformat(preference.updated_at)
            ))
            logger.info(
                f"Created/updated preference: {preference.id} "
                f"(workspace: {preference.workspace_id}, pack: {preference.pack_id}, "
                f"action: {preference.action.value})"
            )
            return preference

    def get_preference(
        self,
        workspace_id: str,
        user_id: str,
        pack_id: Optional[str] = None,
        task_type: Optional[str] = None
    ) -> Optional[TaskPreference]:
        """
        Get preference for a specific pack/task_type

        Args:
            workspace_id: Workspace ID
            user_id: User ID
            pack_id: Pack ID (optional)
            task_type: Task type (optional, more specific than pack_id)

        Returns:
            TaskPreference model or None if not found
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            if task_type:
                cursor.execute('''
                    SELECT * FROM task_preference
                    WHERE workspace_id = ? AND user_id = ? AND task_type = ?
                ''', (workspace_id, user_id, task_type))
            elif pack_id:
                cursor.execute('''
                    SELECT * FROM task_preference
                    WHERE workspace_id = ? AND user_id = ? AND pack_id = ? AND task_type IS NULL
                ''', (workspace_id, user_id, pack_id))
            else:
                return None

            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_preference(row)

    def list_preferences_by_workspace(
        self,
        workspace_id: str,
        user_id: Optional[str] = None,
        pack_id: Optional[str] = None,
        auto_suggest_only: bool = False
    ) -> List[TaskPreference]:
        """
        List preferences for a workspace

        Args:
            workspace_id: Workspace ID
            user_id: Filter by user ID (optional)
            pack_id: Filter by pack ID (optional)
            auto_suggest_only: Only return preferences with auto_suggest=True

        Returns:
            List of preferences
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            query = 'SELECT * FROM task_preference WHERE workspace_id = ?'
            params = [workspace_id]

            if user_id:
                query += ' AND user_id = ?'
                params.append(user_id)

            if pack_id:
                query += ' AND pack_id = ?'
                params.append(pack_id)

            if auto_suggest_only:
                query += ' AND auto_suggest = 1'

            query += ' ORDER BY updated_at DESC'

            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [self._row_to_preference(row) for row in rows]

    def update_preference_from_feedback(
        self,
        workspace_id: str,
        user_id: str,
        pack_id: str,
        task_type: Optional[str],
        feedback_action: TaskFeedbackAction
    ) -> TaskPreference:
        """
        Update preference based on user feedback

        Automatically updates reject_count_30d or accept_count_30d,
        and adjusts auto_suggest based on rejection rate.

        Args:
            workspace_id: Workspace ID
            user_id: User ID
            pack_id: Pack ID
            task_type: Task type (optional)
            feedback_action: Feedback action (accept/reject/dismiss)

        Returns:
            Updated preference
        """
        preference = self.get_preference(workspace_id, user_id, pack_id, task_type)

        if not preference:
            from ...models.workspace import TaskPreference
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
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )

        # Update counters
        if feedback_action == TaskFeedbackAction.REJECT:
            preference.reject_count_30d += 1
        elif feedback_action == TaskFeedbackAction.ACCEPT:
            preference.accept_count_30d += 1

        preference.last_feedback = feedback_action
        preference.updated_at = datetime.utcnow()

        # Auto-adjust auto_suggest based on rejection rate
        total_feedback = preference.reject_count_30d + preference.accept_count_30d
        if total_feedback >= 3:  # Need at least 3 feedback samples
            reject_rate = preference.reject_count_30d / total_feedback
            if reject_rate > 0.5:  # More than 50% rejection rate
                preference.auto_suggest = False
                preference.action = TaskPreferenceAction.MANUAL_ONLY
                logger.info(
                    f"Auto-disabled auto_suggest for pack {pack_id} "
                    f"(reject_rate: {reject_rate:.2f})"
                )
            elif reject_rate < 0.3:  # Less than 30% rejection rate
                preference.auto_suggest = True
                preference.action = TaskPreferenceAction.AUTO_SUGGEST
                logger.info(
                    f"Auto-enabled auto_suggest for pack {pack_id} "
                    f"(reject_rate: {reject_rate:.2f})"
                )

        return self.create_or_update_preference(preference)

    def should_auto_suggest(
        self,
        workspace_id: str,
        user_id: str,
        pack_id: str,
        task_type: Optional[str] = None
    ) -> bool:
        """
        Check if a pack/task_type should be auto-suggested

        Args:
            workspace_id: Workspace ID
            user_id: User ID
            pack_id: Pack ID
            task_type: Task type (optional)

        Returns:
            True if should auto-suggest, False otherwise
        """
        preference = self.get_preference(workspace_id, user_id, pack_id, task_type)

        if not preference:
            return True  # Default: auto-suggest if no preference

        return preference.auto_suggest

    def get_rejection_rate(
        self,
        workspace_id: str,
        user_id: str,
        pack_id: str,
        task_type: Optional[str] = None
    ) -> float:
        """
        Get rejection rate for a pack/task_type

        Args:
            workspace_id: Workspace ID
            user_id: User ID
            pack_id: Pack ID
            task_type: Task type (optional)

        Returns:
            Rejection rate (0.0 to 1.0), or 0.0 if no feedback
        """
        preference = self.get_preference(workspace_id, user_id, pack_id, task_type)

        if not preference:
            return 0.0

        total = preference.reject_count_30d + preference.accept_count_30d
        if total == 0:
            return 0.0

        return float(preference.reject_count_30d) / float(total)

    def cleanup_old_preferences(self, days: int = 90):
        """
        Clean up old preferences that haven't been updated

        Args:
            days: Number of days of inactivity before cleanup (default: 90)
        """
        with self.transaction() as conn:
            cursor = conn.cursor()
            threshold = datetime.utcnow() - timedelta(days=days)

            cursor.execute('''
                DELETE FROM task_preference
                WHERE updated_at < ? AND reject_count_30d = 0 AND accept_count_30d = 0
            ''', (self.to_isoformat(threshold),))

            deleted_count = cursor.rowcount
            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} old preferences")

    def _row_to_preference(self, row) -> TaskPreference:
        """Convert database row to TaskPreference model"""
        last_feedback = None
        if row['last_feedback']:
            try:
                last_feedback = TaskFeedbackAction(row['last_feedback'])
            except ValueError:
                logger.warning(f"Unknown last_feedback: {row['last_feedback']}")

        return TaskPreference(
            id=row['id'],
            workspace_id=row['workspace_id'],
            user_id=row['user_id'],
            pack_id=row['pack_id'],
            task_type=row['task_type'],
            action=TaskPreferenceAction(row['action']),
            auto_suggest=bool(row['auto_suggest']),
            last_feedback=last_feedback,
            reject_count_30d=row['reject_count_30d'],
            accept_count_30d=row['accept_count_30d'],
            created_at=self.from_isoformat(row['created_at']),
            updated_at=self.from_isoformat(row['updated_at'])
        )

