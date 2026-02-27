"""PostgreSQL implementation of IntentLogsStore."""

from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy import text
from backend.app.services.stores.postgres_base import PostgresStoreBase
from backend.app.models.mindscape import IntentLog
import logging

logger = logging.getLogger(__name__)


class PostgresIntentLogsStore(PostgresStoreBase):
    """Postgres implementation of IntentLogsStore."""

    def create_intent_log(self, intent_log: IntentLog) -> IntentLog:
        """Create a new intent log entry."""
        query = text(
            """
            INSERT INTO intent_logs (
                id, timestamp, raw_input, channel, profile_id, project_id, workspace_id,
                pipeline_steps, final_decision, user_override, metadata
            ) VALUES (
                :id, :timestamp, :raw_input, :channel, :profile_id, :project_id, :workspace_id,
                :pipeline_steps, :final_decision, :user_override, :metadata
            )
        """
        )
        params = {
            "id": intent_log.id,
            "timestamp": intent_log.timestamp,
            "raw_input": intent_log.raw_input,
            "channel": intent_log.channel,
            "profile_id": intent_log.profile_id,
            "project_id": intent_log.project_id,
            "workspace_id": intent_log.workspace_id,
            "pipeline_steps": self.serialize_json(intent_log.pipeline_steps),
            "final_decision": self.serialize_json(intent_log.final_decision),
            "user_override": (
                self.serialize_json(intent_log.user_override)
                if intent_log.user_override
                else None
            ),
            "metadata": self.serialize_json(intent_log.metadata),
        }
        with self.transaction() as conn:
            conn.execute(query, params)
        return intent_log

    def get_intent_log(self, log_id: str) -> Optional[IntentLog]:
        """Get intent log by ID."""
        query = text("SELECT * FROM intent_logs WHERE id = :id")
        with self.get_connection() as conn:
            result = conn.execute(query, {"id": log_id})
            row = result.fetchone()
            if not row:
                return None
            return self._row_to_intent_log(row)

    def list_intent_logs(
        self,
        profile_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        project_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        has_override: Optional[bool] = None,
        limit: int = 100,
    ) -> List[IntentLog]:
        """List intent logs with optional filters."""
        base_query = "SELECT * FROM intent_logs WHERE 1=1"
        params: Dict[str, Any] = {}

        if profile_id:
            base_query += " AND profile_id = :profile_id"
            params["profile_id"] = profile_id

        if workspace_id:
            base_query += " AND workspace_id = :workspace_id"
            params["workspace_id"] = workspace_id

        if project_id:
            base_query += " AND project_id = :project_id"
            params["project_id"] = project_id

        if start_time:
            base_query += " AND timestamp >= :start_time"
            params["start_time"] = start_time

        if end_time:
            base_query += " AND timestamp <= :end_time"
            params["end_time"] = end_time

        if has_override is not None:
            if has_override:
                base_query += " AND user_override IS NOT NULL"
            else:
                base_query += " AND user_override IS NULL"

        base_query += " ORDER BY timestamp DESC LIMIT :limit"
        params["limit"] = limit

        with self.get_connection() as conn:
            result = conn.execute(text(base_query), params)
            rows = result.fetchall()
            return [self._row_to_intent_log(row) for row in rows]

    def update_intent_log_override(
        self, log_id: str, user_override: Dict[str, Any]
    ) -> Optional[IntentLog]:
        """Update user override for an intent log."""
        query = text(
            """
            UPDATE intent_logs
            SET user_override = :user_override
            WHERE id = :id
        """
        )
        with self.transaction() as conn:
            result = conn.execute(
                query,
                {
                    "user_override": self.serialize_json(user_override),
                    "id": log_id,
                },
            )
            if result.rowcount > 0:
                return self.get_intent_log(log_id)
            return None

    def _row_to_intent_log(self, row) -> IntentLog:
        """Convert database row to IntentLog."""
        return IntentLog(
            id=row.id,
            timestamp=row.timestamp,
            raw_input=row.raw_input,
            channel=row.channel,
            profile_id=row.profile_id,
            project_id=row.project_id,
            workspace_id=row.workspace_id,
            pipeline_steps=self.deserialize_json(row.pipeline_steps, default={}),
            final_decision=self.deserialize_json(row.final_decision, default={}),
            user_override=(
                self.deserialize_json(row.user_override) if row.user_override else None
            ),
            metadata=self.deserialize_json(row.metadata, default={}),
        )
