"""
ToolCalls Store Service

Handles storage and retrieval of ToolCall records for playbook execution tracking.
"""

import json
import sqlite3
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class ToolCall:
    """ToolCall model for database operations"""
    def __init__(
        self,
        id: str,
        execution_id: str,
        step_id: Optional[str],
        tool_name: str,
        tool_id: Optional[str],
        parameters: Dict[str, Any],
        response: Optional[Dict[str, Any]],
        status: str,
        error: Optional[str],
        duration_ms: Optional[int],
        factory_cluster: Optional[str],
        started_at: Optional[datetime],
        completed_at: Optional[datetime],
        created_at: datetime
    ):
        self.id = id
        self.execution_id = execution_id
        self.step_id = step_id
        self.tool_name = tool_name
        self.tool_id = tool_id
        self.parameters = parameters
        self.response = response
        self.status = status
        self.error = error
        self.duration_ms = duration_ms
        self.factory_cluster = factory_cluster
        self.started_at = started_at
        self.completed_at = completed_at
        self.created_at = created_at


class ToolCallsStore:
    """Store for ToolCall records"""

    def __init__(self, db_path: str):
        """
        Initialize ToolCallsStore

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path

    def create_tool_call(self, tool_call: ToolCall) -> ToolCall:
        """
        Create a new ToolCall record

        Args:
            tool_call: ToolCall instance

        Returns:
            Created ToolCall
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                cursor.execute('''
                    INSERT INTO tool_calls (
                        id, execution_id, step_id, tool_name, tool_id,
                        parameters, response, status, error, duration_ms,
                        factory_cluster, started_at, completed_at, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    tool_call.id,
                    tool_call.execution_id,
                    tool_call.step_id,
                    tool_call.tool_name,
                    tool_call.tool_id,
                    json.dumps(tool_call.parameters),
                    json.dumps(tool_call.response) if tool_call.response else None,
                    tool_call.status,
                    tool_call.error,
                    tool_call.duration_ms,
                    tool_call.factory_cluster,
                    tool_call.started_at.isoformat() if tool_call.started_at else None,
                    tool_call.completed_at.isoformat() if tool_call.completed_at else None,
                    tool_call.created_at.isoformat()
                ))

                conn.commit()
                logger.debug(f"Created ToolCall {tool_call.id} for tool {tool_call.tool_name}")
                return tool_call
        except Exception as e:
            logger.error(f"Failed to create ToolCall: {e}", exc_info=True)
            raise

    def get_tool_call(self, tool_call_id: str) -> Optional[ToolCall]:
        """Get ToolCall by ID"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                cursor.execute('SELECT * FROM tool_calls WHERE id = ?', (tool_call_id,))
                row = cursor.fetchone()

                if not row:
                    return None

                return self._row_to_tool_call(row)
        except Exception as e:
            logger.error(f"Failed to get ToolCall {tool_call_id}: {e}", exc_info=True)
            return None

    def list_tool_calls(
        self,
        execution_id: Optional[str] = None,
        step_id: Optional[str] = None,
        tool_name: Optional[str] = None,
        limit: int = 100
    ) -> List[ToolCall]:
        """List ToolCalls with filters"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                query = 'SELECT * FROM tool_calls WHERE 1=1'
                params = []

                if execution_id:
                    query += ' AND execution_id = ?'
                    params.append(execution_id)
                if step_id:
                    query += ' AND step_id = ?'
                    params.append(step_id)
                if tool_name:
                    query += ' AND tool_name = ?'
                    params.append(tool_name)

                query += ' ORDER BY created_at DESC LIMIT ?'
                params.append(limit)

                cursor.execute(query, params)
                rows = cursor.fetchall()

                return [self._row_to_tool_call(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to list ToolCalls: {e}", exc_info=True)
            return []

    def update_tool_call_status(
        self,
        tool_call_id: str,
        status: str,
        response: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        completed_at: Optional[datetime] = None
    ) -> bool:
        """Update ToolCall status and response"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                update_fields = ['status = ?']
                params = [status]

                if response is not None:
                    update_fields.append('response = ?')
                    params.append(json.dumps(response))

                if error is not None:
                    update_fields.append('error = ?')
                    params.append(error)

                if completed_at:
                    update_fields.append('completed_at = ?')
                    params.append(completed_at.isoformat())

                    # Calculate duration if we have started_at
                    cursor.execute('SELECT started_at FROM tool_calls WHERE id = ?', (tool_call_id,))
                    row = cursor.fetchone()
                    if row and row[0]:
                        started = datetime.fromisoformat(row[0])
                        duration_ms = int((completed_at - started).total_seconds() * 1000)
                        update_fields.append('duration_ms = ?')
                        params.append(duration_ms)

                params.append(tool_call_id)

                cursor.execute(
                    f'UPDATE tool_calls SET {", ".join(update_fields)} WHERE id = ?',
                    params
                )

                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to update ToolCall status: {e}", exc_info=True)
            return False

    def _row_to_tool_call(self, row: sqlite3.Row) -> ToolCall:
        """Convert database row to ToolCall"""
        parameters = {}
        if row['parameters']:
            try:
                parameters = json.loads(row['parameters'])
            except Exception:
                pass

        response = None
        if row['response']:
            try:
                response = json.loads(row['response'])
            except Exception:
                pass

        return ToolCall(
            id=row['id'],
            execution_id=row['execution_id'],
            step_id=row['step_id'],
            tool_name=row['tool_name'],
            tool_id=row['tool_id'],
            parameters=parameters,
            response=response,
            status=row['status'],
            error=row['error'],
            duration_ms=row['duration_ms'],
            factory_cluster=row['factory_cluster'],
            started_at=datetime.fromisoformat(row['started_at']) if row['started_at'] else None,
            completed_at=datetime.fromisoformat(row['completed_at']) if row['completed_at'] else None,
            created_at=datetime.fromisoformat(row['created_at'])
        )

