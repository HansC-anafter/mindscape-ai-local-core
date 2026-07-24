"""Synchronous dispatch for bounded browser-owned Meeting client actions."""

from __future__ import annotations

from typing import Any, Mapping

from backend.app.models.meeting_command import (
    MeetingCommandEnvelope,
    MeetingCommandRecord,
    MeetingCommandStatus,
)
from backend.app.services.orchestration.meeting.voice_client_actions import (
    CLIENT_ACTION_SCHEMA_VERSION,
)


def _client_action_payload(canonical: MeetingCommandEnvelope) -> dict[str, Any]:
    requested = canonical.requested_action
    raw = requested.parameters.get("client_action") if requested else None
    if not isinstance(raw, Mapping):
        raise ValueError("route_client_action requires requested_action.parameters.client_action")
    payload = dict(raw)
    if payload.get("schema_version") != CLIENT_ACTION_SCHEMA_VERSION:
        raise ValueError("unsupported client_action schema_version")
    if not str(payload.get("pack_code") or "").strip():
        raise ValueError("client_action pack_code is required")
    if not str(payload.get("action_code") or "").strip():
        raise ValueError("client_action action_code is required")
    if requested and requested.pack_code != payload.get("pack_code"):
        raise ValueError("client_action pack_code does not match requested_action")
    return payload


async def dispatch_client_action_for_command(
    *,
    command: MeetingCommandRecord,
    canonical: MeetingCommandEnvelope,
) -> tuple[MeetingCommandRecord, dict[str, Any]]:
    client_action = _client_action_payload(canonical)
    command.status = MeetingCommandStatus.COMPLETED
    command.metadata = {
        **command.metadata,
        "dispatch_status": "completed",
        "dispatch_mode": "route_client_action",
        "client_action": client_action,
    }
    return command, {"client_action": client_action}


__all__ = ["dispatch_client_action_for_command"]
