"""
ToolCalls Store Service

Handles storage and retrieval of ToolCall records for playbook execution tracking.
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

from sqlalchemy import text

from app.services.stores.postgres_base import PostgresStoreBase

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
        created_at: datetime,
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


class ToolCallsStore(PostgresStoreBase):
    """Store for ToolCall records (Postgres)."""

    def __init__(self, db_path: Optional[str] = None, db_role: str = "core"):
        super().__init__(db_role=db_role)
        self.db_path = db_path

    def create_tool_call(self, tool_call: ToolCall) -> ToolCall:
        """Create a new ToolCall record"""
        try:
            with self.transaction() as conn:
                conn.execute(
                    text(
                        """
                        INSERT INTO tool_calls (
                            id, execution_id, step_id, tool_name, tool_id,
                            parameters, response, status, error, duration_ms,
                            factory_cluster, started_at, completed_at, created_at
                        ) VALUES (
                            :id, :execution_id, :step_id, :tool_name, :tool_id,
                            :parameters, :response, :status, :error, :duration_ms,
                            :factory_cluster, :started_at, :completed_at, :created_at
                        )
                    """
                    ),
                    {
                        "id": tool_call.id,
                        "execution_id": tool_call.execution_id,
                        "step_id": tool_call.step_id,
                        "tool_name": tool_call.tool_name,
                        "tool_id": tool_call.tool_id,
                        "parameters": self.serialize_json(tool_call.parameters),
                        "response": self.serialize_json(tool_call.response)
                        if tool_call.response
                        else None,
                        "status": tool_call.status,
                        "error": tool_call.error,
                        "duration_ms": tool_call.duration_ms,
                        "factory_cluster": tool_call.factory_cluster,
                        "started_at": tool_call.started_at,
                        "completed_at": tool_call.completed_at,
                        "created_at": tool_call.created_at,
                    },
                )
                logger.debug(
                    f"Created ToolCall {tool_call.id} for tool {tool_call.tool_name}"
                )
                return tool_call
        except Exception as e:
            logger.error(f"Failed to create ToolCall: {e}", exc_info=True)
            raise

    def get_tool_call(self, tool_call_id: str) -> Optional[ToolCall]:
        """Get ToolCall by ID"""
        try:
            with self.get_connection() as conn:
                row = conn.execute(
                    text("SELECT * FROM tool_calls WHERE id = :id"),
                    {"id": tool_call_id},
                ).fetchone()

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
        limit: int = 100,
    ) -> List[ToolCall]:
        """List ToolCalls with filters"""
        try:
            with self.get_connection() as conn:
                query = "SELECT * FROM tool_calls WHERE 1=1"
                params: Dict[str, Any] = {"limit": limit}

                if execution_id:
                    query += " AND execution_id = :execution_id"
                    params["execution_id"] = execution_id
                if step_id:
                    query += " AND step_id = :step_id"
                    params["step_id"] = step_id
                if tool_name:
                    query += " AND tool_name = :tool_name"
                    params["tool_name"] = tool_name

                query += " ORDER BY created_at DESC LIMIT :limit"

                rows = conn.execute(text(query), params).fetchall()
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
        completed_at: Optional[datetime] = None,
    ) -> bool:
        """Update ToolCall status and response"""
        try:
            with self.transaction() as conn:
                update_fields = ["status = :status"]
                params: Dict[str, Any] = {
                    "status": status,
                    "id": tool_call_id,
                }

                if response is not None:
                    update_fields.append("response = :response")
                    params["response"] = self.serialize_json(response)

                if error is not None:
                    update_fields.append("error = :error")
                    params["error"] = error

                if completed_at:
                    update_fields.append("completed_at = :completed_at")
                    params["completed_at"] = completed_at

                    row = conn.execute(
                        text("SELECT started_at FROM tool_calls WHERE id = :id"),
                        {"id": tool_call_id},
                    ).fetchone()
                    if row and row._mapping.get("started_at"):
                        started = row._mapping["started_at"]
                        duration_ms = int(
                            (completed_at - started).total_seconds() * 1000
                        )
                        update_fields.append("duration_ms = :duration_ms")
                        params["duration_ms"] = duration_ms

                query = text(
                    f"UPDATE tool_calls SET {', '.join(update_fields)} WHERE id = :id"
                )
                result = conn.execute(query, params)
                return result.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to update ToolCall status: {e}", exc_info=True)
            return False

    def _row_to_tool_call(self, row) -> ToolCall:
        """Convert database row to ToolCall"""
        data = row._mapping if hasattr(row, "_mapping") else row
        response = None
        if data["response"] is not None:
            response = self.deserialize_json(data["response"], None)

        return ToolCall(
            id=data["id"],
            execution_id=data["execution_id"],
            step_id=data["step_id"],
            tool_name=data["tool_name"],
            tool_id=data["tool_id"],
            parameters=self.deserialize_json(data["parameters"], {}),
            response=response,
            status=data["status"],
            error=data["error"],
            duration_ms=data["duration_ms"],
            factory_cluster=data["factory_cluster"],
            started_at=data["started_at"],
            completed_at=data["completed_at"],
            created_at=data["created_at"],
        )
