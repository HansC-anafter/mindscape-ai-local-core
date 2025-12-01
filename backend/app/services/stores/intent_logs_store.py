"""
Intent logs store for Mindscape data persistence
Handles intent log CRUD operations for offline optimization
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from .base import StoreBase
from ...models.mindscape import IntentLog
import logging

logger = logging.getLogger(__name__)


class IntentLogsStore(StoreBase):
    """Store for managing intent logs"""

    def create_intent_log(self, intent_log: IntentLog) -> IntentLog:
        """
        Create a new intent log entry

        Args:
            intent_log: IntentLog to create

        Returns:
            Created IntentLog
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO intent_logs (
                    id, timestamp, raw_input, channel, profile_id, project_id, workspace_id,
                    pipeline_steps, final_decision, user_override, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                intent_log.id,
                self.to_isoformat(intent_log.timestamp),
                intent_log.raw_input,
                intent_log.channel,
                intent_log.profile_id,
                intent_log.project_id,
                intent_log.workspace_id,
                self.serialize_json(intent_log.pipeline_steps),
                self.serialize_json(intent_log.final_decision),
                self.serialize_json(intent_log.user_override) if intent_log.user_override else None,
                self.serialize_json(intent_log.metadata)
            ))
            conn.commit()
            return intent_log

    def get_intent_log(self, log_id: str) -> Optional[IntentLog]:
        """Get intent log by ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM intent_logs WHERE id = ?', (log_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_intent_log(row)

    def list_intent_logs(
        self,
        profile_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        has_override: Optional[bool] = None,
        limit: int = 100
    ) -> List[IntentLog]:
        """
        List intent logs with optional filters

        Args:
            profile_id: Optional profile filter
            start_time: Optional start time filter
            end_time: Optional end time filter
            has_override: Optional filter for logs with user override
            limit: Maximum number of logs to return

        Returns:
            List of IntentLog objects, ordered by timestamp DESC
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = 'SELECT * FROM intent_logs WHERE 1=1'
            params = []

            if profile_id:
                query += ' AND profile_id = ?'
                params.append(profile_id)

            if start_time:
                query += ' AND timestamp >= ?'
                params.append(self.to_isoformat(start_time))

            if end_time:
                query += ' AND timestamp <= ?'
                params.append(self.to_isoformat(end_time))

            if has_override is not None:
                if has_override:
                    query += ' AND user_override IS NOT NULL'
                else:
                    query += ' AND user_override IS NULL'

            query += ' ORDER BY timestamp DESC LIMIT ?'
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [self._row_to_intent_log(row) for row in rows]

    def update_intent_log_override(self, log_id: str, user_override: Dict[str, Any]) -> Optional[IntentLog]:
        """
        Update user override for an intent log

        Args:
            log_id: Log ID
            user_override: User override data

        Returns:
            Updated IntentLog or None if not found
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE intent_logs
                SET user_override = ?
                WHERE id = ?
            ''', (self.serialize_json(user_override), log_id))
            conn.commit()

            if cursor.rowcount > 0:
                return self.get_intent_log(log_id)
            return None

    def _row_to_intent_log(self, row) -> IntentLog:
        """Convert database row to IntentLog"""
        return IntentLog(
            id=row['id'],
            timestamp=self.from_isoformat(row['timestamp']),
            raw_input=row['raw_input'],
            channel=row['channel'],
            profile_id=row['profile_id'],
            project_id=row['project_id'] if row['project_id'] else None,
            workspace_id=row['workspace_id'] if row['workspace_id'] else None,
            pipeline_steps=self.deserialize_json(row['pipeline_steps'], {}),
            final_decision=self.deserialize_json(row['final_decision'], {}),
            user_override=self.deserialize_json(row['user_override']) if row['user_override'] else None,
            metadata=self.deserialize_json(row['metadata'], {})
        )
