from typing import List, Optional
from sqlalchemy import text
from app.services.stores.postgres_base import PostgresStoreBase
from app.models.mindscape import AgentExecution
import logging

logger = logging.getLogger(__name__)


class PostgresAgentExecutionsStore(PostgresStoreBase):
    """Postgres implementation of AgentExecutionsStore."""

    def create_agent_execution(self, execution: AgentExecution) -> AgentExecution:
        """Create a new agent execution record"""
        query = text(
            """
            INSERT INTO agent_executions (
                id, profile_id, agent_type, task, intent_ids, status,
                started_at, completed_at, duration_seconds, output,
                error_message, used_profile, used_intents, metadata
            ) VALUES (
                :id, :profile_id, :agent_type, :task, :intent_ids, :status,
                :started_at, :completed_at, :duration_seconds, :output,
                :error_message, :used_profile, :used_intents, :metadata
            )
        """
        )
        params = {
            "id": execution.id,
            "profile_id": execution.profile_id,
            "agent_type": execution.agent_type,
            "task": execution.task,
            "intent_ids": self.serialize_json(execution.intent_ids),
            "status": execution.status,
            "started_at": execution.started_at,
            "completed_at": execution.completed_at,
            "duration_seconds": execution.duration_seconds,
            "output": execution.output,
            "error_message": execution.error_message,
            "used_profile": self.serialize_json(execution.used_profile),
            "used_intents": self.serialize_json(execution.used_intents),
            "metadata": self.serialize_json(execution.metadata),
        }
        with self.transaction() as conn:
            conn.execute(query, params)
        return execution

    def get_agent_execution(self, execution_id: str) -> Optional[AgentExecution]:
        """Get agent execution by ID"""
        query = text("SELECT * FROM agent_executions WHERE id = :id")
        with self.get_connection() as conn:
            result = conn.execute(query, {"id": execution_id})
            row = result.fetchone()
            if not row:
                return None
            return self._row_to_agent_execution(row)

    def list_agent_executions(
        self, profile_id: str, limit: int = 50
    ) -> List[AgentExecution]:
        """List recent agent executions for a profile"""
        query = text(
            """
            SELECT * FROM agent_executions
            WHERE profile_id = :profile_id
            ORDER BY started_at DESC
            LIMIT :limit
        """
        )
        with self.get_connection() as conn:
            result = conn.execute(query, {"profile_id": profile_id, "limit": limit})
            rows = result.fetchall()
            return [self._row_to_agent_execution(row) for row in rows]

    def _row_to_agent_execution(self, row) -> AgentExecution:
        """Convert database row to AgentExecution"""
        return AgentExecution(
            id=row.id,
            profile_id=row.profile_id,
            agent_type=row.agent_type,
            task=row.task,
            intent_ids=self.deserialize_json(row.intent_ids, default=[]),
            status=row.status,
            started_at=row.started_at,
            completed_at=row.completed_at,
            duration_seconds=row.duration_seconds,
            output=row.output,
            error_message=row.error_message,
            used_profile=self.deserialize_json(row.used_profile, default=None),
            used_intents=self.deserialize_json(row.used_intents, default=[]),
            metadata=self.deserialize_json(row.metadata, default={}),
        )
