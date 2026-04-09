"""Shared helpers for user-reserved task pause semantics."""

from typing import Any, Dict


USER_PAUSE_RESERVED_BLOCKED_REASON = "user_pause_reserved"
USER_PAUSE_RESERVED_MODE = "user_reserved"
PAUSE_REQUESTED_TRANSITION = "pause"


def as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def normalize_status(value: Any) -> str:
    if hasattr(value, "value"):
        value = value.value
    return str(value or "").strip().lower()


def get_control_context(execution_context: Any) -> Dict[str, Any]:
    return as_dict(as_dict(execution_context).get("control"))


def is_user_pause_requested(execution_context: Any) -> bool:
    control = get_control_context(execution_context)
    requested_transition = normalize_status(control.get("requested_transition"))
    pause_mode = normalize_status(
        control.get("pause_mode") or as_dict(execution_context).get("pause_mode")
    )
    return (
        requested_transition == PAUSE_REQUESTED_TRANSITION
        and pause_mode == USER_PAUSE_RESERVED_MODE
    )


def is_user_pause_reserved_state(
    *,
    status: Any,
    blocked_reason: Any,
    execution_context: Any,
) -> bool:
    return (
        normalize_status(status) == "pending"
        and normalize_status(blocked_reason) == USER_PAUSE_RESERVED_BLOCKED_REASON
        and normalize_status(as_dict(execution_context).get("status")) == "paused"
    )


def is_user_pause_reserved_task(task_like: Any) -> bool:
    if task_like is None:
        return False
    if isinstance(task_like, dict):
        status = task_like.get("status")
        blocked_reason = task_like.get("blocked_reason")
        execution_context = task_like.get("execution_context")
    else:
        status = getattr(task_like, "status", None)
        blocked_reason = getattr(task_like, "blocked_reason", None)
        execution_context = getattr(task_like, "execution_context", None)
    return is_user_pause_reserved_state(
        status=status,
        blocked_reason=blocked_reason,
        execution_context=execution_context,
    )


def project_task_status(task_payload: Dict[str, Any]) -> str:
    if is_user_pause_reserved_task(task_payload):
        return "paused"
    return normalize_status(task_payload.get("status"))
