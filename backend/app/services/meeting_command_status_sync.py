"""Best-effort Meeting Workbench command-ledger status sync from runtime tasks."""

from __future__ import annotations

import logging
from typing import Any, Optional

from backend.app.models.meeting_command import MeetingCommandStatus

logger = logging.getLogger(__name__)

SUCCESS_TASK_STATUSES = {"succeeded"}
FAILED_TASK_STATUSES = {"failed", "cancelled_by_user", "expired"}
RUNNING_TASK_STATUSES = {"running"}
ACCEPTED_TASK_STATUSES = {"pending"}


def _raw_status(status: Any) -> str:
    if hasattr(status, "value"):
        return str(status.value).strip().lower()
    return str(status or "").strip().lower()


def map_task_status_to_command_status(status: Any) -> Optional[MeetingCommandStatus]:
    """Map workspace task statuses onto the durable command lifecycle."""

    raw = _raw_status(status)
    if raw in SUCCESS_TASK_STATUSES:
        return MeetingCommandStatus.COMPLETED
    if raw in FAILED_TASK_STATUSES:
        return MeetingCommandStatus.FAILED
    if raw in RUNNING_TASK_STATUSES:
        return MeetingCommandStatus.RUNNING
    if raw in ACCEPTED_TASK_STATUSES:
        return MeetingCommandStatus.ACCEPTED
    return None


def _read_mapping(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    return None


def _first_text(*values: Any) -> Optional[str]:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _find_command_id(value: Any, *, depth: int = 0) -> Optional[str]:
    if depth > 5:
        return None
    if not isinstance(value, dict):
        return None
    direct = _first_text(
        value.get("command_id"),
        value.get("meeting_command_id"),
    )
    if direct:
        return direct
    for key in (
        "request_context",
        "action_params",
        "inputs",
        "input_params",
        "params",
        "object_action_plan",
        "command",
        "metadata",
    ):
        nested = _find_command_id(_read_mapping(value, key), depth=depth + 1)
        if nested:
            return nested
    return None


def extract_command_id_from_task(task: Any) -> Optional[str]:
    """Find the command id carried by a task's runtime payloads."""

    return _first_text(
        _find_command_id(getattr(task, "params", None)),
        _find_command_id(getattr(task, "result", None)),
        _find_command_id(getattr(task, "execution_context", None)),
    )


def _task_runtime_id(task: Any) -> Optional[str]:
    return _first_text(getattr(task, "execution_id", None), getattr(task, "id", None))


def _iso_or_none(value: Any) -> Optional[str]:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def sync_meeting_command_from_task(task: Any, *, store: Any = None):
    """Best-effort sync of one task status into the meeting command ledger."""

    command_id = extract_command_id_from_task(task)
    if not command_id:
        return None
    command_status = map_task_status_to_command_status(getattr(task, "status", None))
    if command_status is None:
        return None

    if store is None:
        from backend.app.services.stores.meeting_command_store import (
            MeetingCommandStore,
        )

        store = MeetingCommandStore()

    command = store.get(command_id)
    if command is None:
        return None

    runtime_id = _task_runtime_id(task)
    accepted_task_id = command.accepted_task_id
    if runtime_id and (not accepted_task_id or accepted_task_id == command.command_id):
        accepted_task_id = runtime_id

    raw_status = _raw_status(getattr(task, "status", None))
    command.status = command_status
    command.accepted_task_id = accepted_task_id
    command.metadata = {
        **command.metadata,
        "dispatch_status": (
            "completed"
            if command_status == MeetingCommandStatus.COMPLETED
            else "failed"
            if command_status == MeetingCommandStatus.FAILED
            else raw_status
        ),
        "runtime_task": {
            "task_id": getattr(task, "id", None),
            "execution_id": getattr(task, "execution_id", None),
            "status": raw_status,
            "pack_id": getattr(task, "pack_id", None),
            "task_type": getattr(task, "task_type", None),
            "completed_at": _iso_or_none(getattr(task, "completed_at", None)),
            "error": getattr(task, "error", None),
        },
    }
    return store.save(command)


def sync_meeting_command_from_task_safely(task: Any) -> None:
    """Never let ledger sync failures break task status updates."""

    try:
        sync_meeting_command_from_task(task)
    except Exception as exc:
        logger.debug("Meeting command status sync skipped: %s", exc, exc_info=True)
