"""Compile-session recovery helpers for handoff bundle intake."""

import json
from typing import Any, Dict, Optional

from backend.app.models.handoff import HandoffIn


def enum_value(value: Any) -> str:
    if hasattr(value, "value"):
        return str(value.value)
    return str(value or "")


def looks_like_orphan_compile_session(
    session: Any,
    existing_compile_job: Any,
) -> bool:
    """Return True when a compile session should not be reused."""
    if session is None:
        return False

    if existing_compile_job is None:
        return (
            int(getattr(session, "round_count", 0) or 0) == 0
            and not list(getattr(session, "action_items", []) or [])
        )

    compile_status = enum_value(getattr(existing_compile_job, "status", None)).lower()
    if compile_status not in {"accepted", "running"}:
        return False

    return True


def reuse_terminal_compile_result(
    session: Any,
    existing_compile_job: Any,
    *,
    incoming_handoff_id: Optional[str],
) -> Optional[Dict[str, Any]]:
    """Return an idempotent compile result for same-handoff re-entry."""
    if session is None or existing_compile_job is None:
        return None

    existing_handoff_id = getattr(existing_compile_job, "handoff_id", None)
    if incoming_handoff_id and existing_handoff_id != incoming_handoff_id:
        return None

    compile_status = enum_value(getattr(existing_compile_job, "status", None)).lower()
    if compile_status != "succeeded":
        return None

    result = getattr(existing_compile_job, "result", None) or {}
    if not isinstance(result, dict):
        result = {}

    reused_result = dict(result)
    reused_result.setdefault("status", "compiled")
    reused_result["compile_job_id"] = existing_compile_job.id
    reused_result["job_id"] = existing_compile_job.id
    reused_result["session_id"] = (
        reused_result.get("session_id")
        or getattr(session, "id", None)
        or getattr(existing_compile_job, "session_id", None)
    )
    reused_result.setdefault("persisted", False)
    reused_result["reused_compile_job"] = True
    return reused_result


def should_supersede_active_session(
    session: Any,
    existing_compile_job: Any,
    *,
    incoming_handoff_id: Optional[str],
) -> bool:
    """Return True when an active session should yield to a newer handoff."""
    if session is None or not getattr(session, "is_active", False):
        return False
    if not incoming_handoff_id:
        return False
    if existing_compile_job is None:
        return True

    existing_handoff_id = getattr(existing_compile_job, "handoff_id", None)
    if not isinstance(existing_handoff_id, str) or not existing_handoff_id.strip():
        return False
    return existing_handoff_id.strip() != incoming_handoff_id


def build_compile_job_recovery_request(
    *,
    handoff_in: HandoffIn,
    workspace_id: str,
    project_id: str,
    thread_id: str,
    profile_id: str,
    model_name: Optional[str],
    source_device_id: Optional[str],
) -> Dict[str, Any]:
    return {
        "handoff_payload": json.loads(handoff_in.model_dump_json()),
        "workspace_id": workspace_id,
        "project_id": project_id,
        "thread_id": thread_id,
        "profile_id": profile_id,
        "model_name": model_name,
        "source_device_id": source_device_id,
    }
