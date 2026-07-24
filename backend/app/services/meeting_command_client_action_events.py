"""Durable workspace events for browser-owned Meeting client actions."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Mapping

from backend.app.models.meeting_command import MeetingCommandRecord
from backend.app.models.mindscape import EventActor, EventType, MindEvent


CLIENT_ACTION_READY_EVENT_CODE = "aol_client_action_ready"


def emit_meeting_client_action_ready_event(
    *,
    command: MeetingCommandRecord,
    client_action: Mapping[str, Any],
    workspace: Any,
    session: Any,
    mindscape_store: Any,
) -> MindEvent:
    """Commit the action notification before the HTTP caller may act on it."""

    event = MindEvent(
        id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc),
        actor=EventActor.SYSTEM,
        channel="meeting",
        profile_id=str(getattr(workspace, "owner_user_id", "") or "system"),
        project_id=getattr(session, "project_id", None),
        workspace_id=command.workspace_id,
        thread_id=command.thread_id or command.meeting_id,
        event_type=EventType.CAPABILITY_EVENT,
        payload={
            "event_code": CLIENT_ACTION_READY_EVENT_CODE,
            "meeting_session_id": command.meeting_id,
            "command_id": command.command_id,
            "client_action": dict(client_action),
        },
        entity_ids=[command.command_id, command.meeting_id],
        metadata={
            "meeting_session_id": command.meeting_id,
            "meeting_command_id": command.command_id,
            "source": "meeting_command_ledger",
        },
    )
    return mindscape_store.create_event(event, generate_embedding=False)


__all__ = [
    "CLIENT_ACTION_READY_EVENT_CODE",
    "emit_meeting_client_action_ready_event",
]
