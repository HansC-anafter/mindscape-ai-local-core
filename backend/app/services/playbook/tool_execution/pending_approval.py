"""
Pending tool-approval helpers for execution-chat governance.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from backend.app.models.surface import Command, CommandStatus
from backend.app.services.stores.postgres.remaining_stores import PostgresCommandsStore


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ToolApprovalRequiredError(Exception):
    def __init__(self, approval_request: dict[str, Any]):
        self.approval_request = approval_request
        super().__init__(
            approval_request.get("user_message")
            or approval_request.get("reason")
            or "Tool execution requires approval."
        )


class PendingToolApprovalService:
    def __init__(self, store: Optional[PostgresCommandsStore] = None):
        self.store = store or PostgresCommandsStore()

    def create_pending_tool_approval(
        self,
        *,
        workspace_id: str,
        tool_fqn: str,
        parameters: dict[str, Any],
        reason: str,
        user_message: Optional[str] = None,
        execution_id: Optional[str] = None,
        thread_id: Optional[str] = None,
        actor_id: Optional[str] = None,
        source_surface: Optional[str] = None,
        correlation_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        command_id = f"cmd_{uuid.uuid4().hex}"
        now = _utc_now()
        command = Command(
            command_id=command_id,
            workspace_id=workspace_id,
            actor_id=actor_id or "system",
            source_surface=source_surface or "tool_execution",
            intent_code=f"tool_approval:{tool_fqn}",
            parameters={
                "tool_fqn": tool_fqn,
                "tool_parameters": parameters,
                "execution_id": execution_id,
            },
            requires_approval=True,
            status=CommandStatus.PENDING,
            execution_id=execution_id,
            thread_id=thread_id,
            correlation_id=correlation_id or execution_id,
            metadata={
                "proposal_kind": "tool_approval",
                "tool_fqn": tool_fqn,
                "reason": reason,
                **(metadata or {}),
            },
            created_at=now,
            updated_at=now,
        )
        self.store.create_command(command)
        return {
            "command_id": command_id,
            "status": "pending",
            "workspace_id": workspace_id,
            "execution_id": execution_id,
            "tool_fqn": tool_fqn,
            "tool_parameters": parameters,
            "reason": reason,
            "user_message": user_message
            or f"Tool `{tool_fqn}` requires approval before execution.",
            "metadata": command.metadata,
        }
