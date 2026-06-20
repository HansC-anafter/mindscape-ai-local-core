"""Payload helpers for workspace execution activity read models."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional


FAILED_EXECUTION_STATUSES = ("failed", "cancelled", "cancelled_by_user", "expired")
COMPLETED_EXECUTION_STATUSES = ("succeeded", "completed")


def mapping_from_row(row: Any) -> Dict[str, Any]:
    if row is None:
        return {}
    if hasattr(row, "_mapping"):
        return dict(row._mapping)
    if isinstance(row, dict):
        return row
    return dict(row)


def as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def datetime_or_now(value: Optional[datetime]) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.now(timezone.utc)


def frontier_state(status: str) -> str:
    if status == "running":
        return "running"
    if status in {*COMPLETED_EXECUTION_STATUSES, *FAILED_EXECUTION_STATUSES}:
        return "done"
    return "ready"


def compact_execution_context(
    mapping: Dict[str, Any],
    compact_inputs: Dict[str, Any],
) -> Dict[str, Any]:
    context = {
        "project_id": mapping.get("project_id"),
        "status": mapping.get("status"),
        "summary": mapping.get("summary"),
    }
    if compact_inputs:
        context["inputs"] = compact_inputs
        for key in (
            "target_username",
            "target_handle",
            "reference_id",
            "source_handle",
        ):
            if compact_inputs.get(key):
                context[key] = compact_inputs.get(key)
    return {
        key: value
        for key, value in context.items()
        if value not in (None, "", [], {})
    }


def row_to_execution_payload(
    row: Any,
    *,
    input_overlay: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    mapping = mapping_from_row(row)
    status = str(mapping.get("status") or "")
    compact_inputs = as_dict(mapping.get("compact_inputs"))
    if input_overlay:
        compact_inputs = {**compact_inputs, **input_overlay}
    context = compact_execution_context(mapping, compact_inputs)
    return {
        "id": mapping.get("task_id"),
        "task_id": mapping.get("task_id"),
        "workspace_id": mapping.get("workspace_id"),
        "message_id": mapping.get("task_id"),
        "execution_id": mapping.get("execution_id"),
        "parent_execution_id": mapping.get("parent_execution_id"),
        "project_id": mapping.get("project_id"),
        "pack_id": mapping.get("pack_id") or "",
        "task_type": mapping.get("task_type"),
        "status": status,
        "params": compact_inputs,
        "result": None,
        "execution_context": context,
        "meeting_session_id": None,
        "storyline_tags": [],
        "created_at": datetime_or_now(mapping.get("created_at")),
        "next_eligible_at": datetime_or_now(mapping.get("next_eligible_at")),
        "blocked_reason": mapping.get("blocked_reason"),
        "blocked_payload": None,
        "queue_shard": mapping.get("queue_shard") or "default",
        "concurrency_key": mapping.get("dedupe_key"),
        "frontier_state": mapping.get("frontier_state") or frontier_state(status),
        "frontier_enqueued_at": mapping.get("frontier_enqueued_at"),
        "runner_id": None,
        "heartbeat_at": None,
        "started_at": mapping.get("started_at"),
        "completed_at": mapping.get("completed_at"),
        "error": mapping.get("error_summary"),
        "summary": mapping.get("summary"),
        "updated_at": mapping.get("updated_at"),
        "last_event_at": mapping.get("last_event_at"),
    }


def row_to_execution_group_payload(row: Any) -> Dict[str, Any]:
    mapping = mapping_from_row(row)
    return {
        "parent_execution_id": mapping.get("group_parent_execution_id"),
        "summary": {
            "total": int(mapping.get("total") or 0),
            "completed": int(mapping.get("completed") or 0),
            "failed": int(mapping.get("failed") or 0),
            "running": int(mapping.get("running") or 0),
            "pending": int(mapping.get("pending") or 0),
        },
        "latest_at": mapping.get("latest_at"),
        "representative": row_to_execution_payload(row),
    }
