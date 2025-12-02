"""
Agent executions store for Mindscape data persistence
Handles agent execution record CRUD operations
"""

from typing import List, Optional
from backend.app.services.stores.base import StoreBase
from ...models.mindscape import AgentExecution
import logging

logger = logging.getLogger(__name__)


class AgentExecutionsStore(StoreBase):
    """Store for managing agent executions"""

    def create_agent_execution(self, execution: AgentExecution) -> AgentExecution:
        """Create a new agent execution record"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO agent_executions (
                    id, profile_id, agent_type, task, intent_ids, status,
                    started_at, completed_at, duration_seconds, output,
                    error_message, used_profile, used_intents, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                execution.id,
                execution.profile_id,
                execution.agent_type,
                execution.task,
                self.serialize_json(execution.intent_ids),
                execution.status,
                self.to_isoformat(execution.started_at),
                self.to_isoformat(execution.completed_at),
                execution.duration_seconds,
                execution.output,
                execution.error_message,
                self.serialize_json(execution.used_profile) if execution.used_profile else None,
                self.serialize_json(execution.used_intents) if execution.used_intents else None,
                self.serialize_json(execution.metadata)
            ))
            conn.commit()
            return execution

    def get_agent_execution(self, execution_id: str) -> Optional[AgentExecution]:
        """Get agent execution by ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM agent_executions WHERE id = ?', (execution_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_agent_execution(row)

    def list_agent_executions(self, profile_id: str, limit: int = 50) -> List[AgentExecution]:
        """List recent agent executions for a profile"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM agent_executions
                WHERE profile_id = ?
                ORDER BY started_at DESC
                LIMIT ?
            ''', (profile_id, limit))
            rows = cursor.fetchall()
            return [self._row_to_agent_execution(row) for row in rows]

    def _row_to_agent_execution(self, row) -> AgentExecution:
        """Convert database row to AgentExecution"""
        return AgentExecution(
            id=row['id'],
            profile_id=row['profile_id'],
            agent_type=row['agent_type'],
            task=row['task'],
            intent_ids=self.deserialize_json(row['intent_ids'], []),
            status=row['status'],
            started_at=self.from_isoformat(row['started_at']),
            completed_at=self.from_isoformat(row['completed_at']),
            duration_seconds=row['duration_seconds'],
            output=row['output'],
            error_message=row['error_message'],
            used_profile=self.deserialize_json(row['used_profile']) if row['used_profile'] else None,
            used_intents=self.deserialize_json(row['used_intents']) if row['used_intents'] else None,
            metadata=self.deserialize_json(row['metadata'], {})
        )
