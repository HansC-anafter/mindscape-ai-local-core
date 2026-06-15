from __future__ import annotations

import logging
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from ..postgres_base import PostgresStoreBase
from app.models.surface import Command, CommandStatus, SurfaceEvent
from app.models.workspace import ConversationThread, PlaybookExecution, ThreadReference
from app.models.lens_composition import LensComposition, LensReference

from .remaining_store_utils import _utc_now

logger = logging.getLogger(__name__)


# =================================================================================
# Commands Store
# =================================================================================
class PostgresCommandsStore(PostgresStoreBase):
    """Postgres implementation of CommandsStore."""

    def create_command(self, command: Command) -> Command:
        with self.transaction() as conn:
            query = text(
                """
                INSERT INTO commands (
                    command_id, workspace_id, actor_id, source_surface, intent_code,
                    parameters, requires_approval, status, execution_id,
                    thread_id, correlation_id, parent_command_id, metadata,
                    created_at, updated_at
                ) VALUES (
                    :command_id, :workspace_id, :actor_id, :source_surface, :intent_code,
                    :parameters, :requires_approval, :status, :execution_id,
                    :thread_id, :correlation_id, :parent_command_id, :metadata,
                    :created_at, :updated_at
                )
            """
            )
            params = {
                "command_id": command.command_id,
                "workspace_id": command.workspace_id,
                "actor_id": command.actor_id,
                "source_surface": command.source_surface,
                "intent_code": command.intent_code,
                "parameters": self.serialize_json(command.parameters),
                "requires_approval": command.requires_approval,  # Postgres handles bool
                "status": command.status.value,
                "execution_id": command.execution_id,
                "thread_id": command.thread_id,
                "correlation_id": command.correlation_id,
                "parent_command_id": command.parent_command_id,
                "metadata": self.serialize_json(command.metadata),
                "created_at": command.created_at or _utc_now(),
                "updated_at": command.updated_at or _utc_now(),
            }
            conn.execute(query, params)
            logger.info(f"Created Command: {command.command_id}")
            return command

    def get_command(self, command_id: str) -> Optional[Command]:
        with self.get_connection() as conn:
            query = text("SELECT * FROM commands WHERE command_id = :command_id")
            row = conn.execute(query, {"command_id": command_id}).fetchone()
            if not row:
                return None
            return self._row_to_command(row)

    def update_command(self, command_id: str, updates: dict) -> Optional[Command]:
        set_clauses = []
        params = {"command_id": command_id}

        if "status" in updates:
            set_clauses.append("status = :status")
            status = updates["status"]
            params["status"] = status.value if hasattr(status, "value") else status

        if "execution_id" in updates:
            set_clauses.append("execution_id = :execution_id")
            params["execution_id"] = updates["execution_id"]

        if "parameters" in updates:
            set_clauses.append("parameters = :parameters")
            params["parameters"] = self.serialize_json(updates["parameters"])

        if "metadata" in updates:
            set_clauses.append("metadata = :metadata")
            params["metadata"] = self.serialize_json(updates["metadata"])

        if not set_clauses:
            return self.get_command(command_id)

        set_clauses.append("updated_at = :updated_at")
        params["updated_at"] = _utc_now()

        with self.transaction() as conn:
            query = text(
                f"UPDATE commands SET {', '.join(set_clauses)} WHERE command_id = :command_id"
            )
            result = conn.execute(query, params)
            if result.rowcount == 0:
                return None

            logger.info(f"Updated Command: {command_id}")
            return self.get_command(command_id)

    def list_commands(
        self,
        workspace_id: Optional[str] = None,
        status: Optional[CommandStatus] = None,
        limit: int = 50,
    ) -> List[Command]:
        with self.get_connection() as conn:
            query_str = "SELECT * FROM commands WHERE 1=1"
            params = {}

            if workspace_id:
                query_str += " AND workspace_id = :workspace_id"
                params["workspace_id"] = workspace_id

            if status:
                query_str += " AND status = :status"
                params["status"] = status.value

            query_str += " ORDER BY created_at DESC LIMIT :limit"
            params["limit"] = limit

            rows = conn.execute(text(query_str), params).fetchall()
            return [self._row_to_command(row) for row in rows]

    def _row_to_command(self, row) -> Command:
        return Command(
            command_id=row.command_id,
            workspace_id=row.workspace_id,
            actor_id=row.actor_id,
            source_surface=row.source_surface,
            intent_code=row.intent_code,
            parameters=self.deserialize_json(row.parameters, default={}),
            requires_approval=(
                row.requires_approval if row.requires_approval is not None else False
            ),
            status=CommandStatus(row.status),
            execution_id=row.execution_id,
            thread_id=row.thread_id,
            correlation_id=row.correlation_id,
            parent_command_id=row.parent_command_id,
            metadata=self.deserialize_json(row.metadata, default={}),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
