"""PostgreSQL store for Meeting Workbench command-ledger rows."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from backend.app.models.meeting_command import (
    MeetingCommandRecord,
    MeetingCommandStatus,
    MeetingRequestedAction,
)
from backend.app.models.object_runtime import ObjectRoleEntry
from backend.app.services.stores.postgres_base import PostgresStoreBase

logger = logging.getLogger(__name__)


TABLE_DDL = """
CREATE TABLE IF NOT EXISTS meeting_commands (
    command_id        TEXT PRIMARY KEY,
    workspace_id      TEXT NOT NULL,
    meeting_id        TEXT NOT NULL,
    thread_id         TEXT,
    client_draft_id   TEXT,
    origin_surface    TEXT NOT NULL,
    actor             TEXT NOT NULL,
    intent_text       TEXT NOT NULL,
    context_objects   JSONB DEFAULT '[]',
    requested_action  JSONB DEFAULT '{}',
    expected_outputs  JSONB DEFAULT '[]',
    write_mode        TEXT NOT NULL DEFAULT 'recommendation_only',
    status            TEXT NOT NULL DEFAULT 'accepted',
    accepted_task_id  TEXT,
    metadata          JSONB DEFAULT '{}',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

INDEX_DDL = [
    "CREATE INDEX IF NOT EXISTS idx_meeting_commands_ws_meeting ON meeting_commands(workspace_id, meeting_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_meeting_commands_ws_thread ON meeting_commands(workspace_id, thread_id)",
    "CREATE INDEX IF NOT EXISTS idx_meeting_commands_client_draft ON meeting_commands(workspace_id, meeting_id, client_draft_id)",
]


class MeetingCommandStore(PostgresStoreBase):
    """Store for durable meeting command ledger rows."""

    _table_ensured = False

    def __init__(self, db_role: str = "core"):
        super().__init__(db_role=db_role)
        # Schema ownership belongs to Alembic.  ``ensure_table`` remains an
        # explicit repair/tooling hook and is never called on request startup.

    def ensure_table(self) -> None:
        with self.transaction() as conn:
            conn.execute(text(TABLE_DDL))
            for index_ddl in INDEX_DDL:
                conn.execute(text(index_ddl))
        logger.info("meeting_commands table ensured")

    def save(self, command: MeetingCommandRecord) -> MeetingCommandRecord:
        now = datetime.now(timezone.utc)
        if command.created_at is None:
            command.created_at = now
        command.updated_at = now
        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO meeting_commands (
                        command_id, workspace_id, meeting_id, thread_id,
                        client_draft_id, origin_surface, actor, intent_text,
                        context_objects, requested_action, expected_outputs,
                        write_mode, status, accepted_task_id, metadata,
                        created_at, updated_at
                    ) VALUES (
                        :command_id, :workspace_id, :meeting_id, :thread_id,
                        :client_draft_id, :origin_surface, :actor, :intent_text,
                        :context_objects, :requested_action, :expected_outputs,
                        :write_mode, :status, :accepted_task_id, :metadata,
                        :created_at, :updated_at
                    )
                    ON CONFLICT (command_id) DO UPDATE SET
                        thread_id = EXCLUDED.thread_id,
                        client_draft_id = EXCLUDED.client_draft_id,
                        origin_surface = EXCLUDED.origin_surface,
                        actor = EXCLUDED.actor,
                        intent_text = EXCLUDED.intent_text,
                        context_objects = EXCLUDED.context_objects,
                        requested_action = EXCLUDED.requested_action,
                        expected_outputs = EXCLUDED.expected_outputs,
                        write_mode = EXCLUDED.write_mode,
                        status = EXCLUDED.status,
                        accepted_task_id = EXCLUDED.accepted_task_id,
                        metadata = EXCLUDED.metadata,
                        updated_at = EXCLUDED.updated_at
                    """
                ),
                self._command_params(command),
            )
        return command

    def get(self, command_id: str) -> Optional[MeetingCommandRecord]:
        with self.get_connection() as conn:
            row = conn.execute(
                text("SELECT * FROM meeting_commands WHERE command_id = :command_id"),
                {"command_id": command_id},
            ).fetchone()
        if not row:
            return None
        return self._row_to_command(row)

    def list_by_meeting(
        self,
        *,
        workspace_id: str,
        meeting_id: str,
        limit: int = 100,
    ) -> List[MeetingCommandRecord]:
        with self.get_connection() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT * FROM meeting_commands
                    WHERE workspace_id = :workspace_id
                      AND meeting_id = :meeting_id
                    ORDER BY created_at ASC
                    LIMIT :limit
                    """
                ),
                {
                    "workspace_id": workspace_id,
                    "meeting_id": meeting_id,
                    "limit": limit,
                },
            ).fetchall()
        return [self._row_to_command(row) for row in rows]

    def _command_params(self, command: MeetingCommandRecord) -> Dict[str, Any]:
        requested_action = (
            command.requested_action.model_dump(exclude_none=True)
            if command.requested_action
            else {}
        )
        return {
            "command_id": command.command_id,
            "workspace_id": command.workspace_id,
            "meeting_id": command.meeting_id,
            "thread_id": command.thread_id,
            "client_draft_id": command.client_draft_id,
            "origin_surface": command.origin_surface,
            "actor": command.actor,
            "intent_text": command.intent_text,
            "context_objects": self.serialize_json(
                [entry.model_dump(exclude_none=True) for entry in command.context_objects]
            ),
            "requested_action": self.serialize_json(requested_action),
            "expected_outputs": self.serialize_json(command.expected_outputs),
            "write_mode": command.write_mode,
            "status": command.status.value,
            "accepted_task_id": command.accepted_task_id,
            "metadata": self.serialize_json(command.metadata),
            "created_at": command.created_at,
            "updated_at": command.updated_at,
        }

    @staticmethod
    def _row_data(row: Any) -> Dict[str, Any]:
        return row._mapping if hasattr(row, "_mapping") else row

    def _row_to_command(self, row: Any) -> MeetingCommandRecord:
        data = self._row_data(row)
        requested_action_payload = self.deserialize_json(
            data.get("requested_action"),
            {},
        )
        requested_action = (
            MeetingRequestedAction.model_validate(requested_action_payload)
            if requested_action_payload
            else None
        )
        return MeetingCommandRecord(
            command_id=data["command_id"],
            workspace_id=data["workspace_id"],
            meeting_id=data["meeting_id"],
            thread_id=data.get("thread_id"),
            client_draft_id=data.get("client_draft_id"),
            origin_surface=data["origin_surface"],
            actor=data["actor"],
            intent_text=data["intent_text"],
            context_objects=[
                ObjectRoleEntry.model_validate(entry)
                for entry in self.deserialize_json(data.get("context_objects"), [])
            ],
            requested_action=requested_action,
            expected_outputs=self.deserialize_json(data.get("expected_outputs"), []),
            write_mode=data.get("write_mode", "recommendation_only"),
            status=MeetingCommandStatus(data.get("status", "accepted")),
            accepted_task_id=data.get("accepted_task_id"),
            metadata=self.deserialize_json(data.get("metadata"), {}),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )
