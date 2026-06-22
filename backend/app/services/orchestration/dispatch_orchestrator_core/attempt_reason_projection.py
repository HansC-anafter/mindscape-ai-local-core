"""Human-readable dispatch attempt reason projection."""

from __future__ import annotations

from typing import Any, Mapping


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _attempt_status(attempt: Any) -> str | None:
    status = getattr(attempt, "status", None)
    raw = getattr(status, "value", status)
    return _text(raw)


def build_attempt_reason_projection(
    *,
    phase: Any,
    action_item: Mapping[str, Any],
    attempt: Any,
    engine: str | None,
    target_workspace_id: str | None,
    status: str,
    reason: str | None = None,
    playbook_code: str | None = None,
    result: Any = None,
    error: str | None = None,
) -> dict[str, Any]:
    action_title = action_item.get("title") or action_item.get("action")
    execution_id = result.get("execution_id") if isinstance(result, Mapping) else None
    reason_code = (
        reason
        or error
        or action_item.get("landing_status")
        or _attempt_status(attempt)
        or status
    )
    return {
        "phase_id": _text(getattr(phase, "id", None)),
        "phase_name": _text(getattr(phase, "name", None)) or _text(action_title),
        "status": status,
        "reason": _text(reason_code),
        "attempt_status": _attempt_status(attempt),
        "engine": _text(engine),
        "playbook_code": _text(playbook_code),
        "target_workspace_id": _text(target_workspace_id),
        "execution_id": _text(execution_id),
        "idempotency_key": _text(getattr(attempt, "idempotency_key", None)),
        "attempt_number": getattr(attempt, "attempt_number", None),
    }


def attach_attempt_reason_projection(
    payload: Mapping[str, Any],
    **projection_kwargs: Any,
) -> dict[str, Any]:
    payload = dict(payload)
    payload["dispatch_attempt_reason"] = build_attempt_reason_projection(
        **projection_kwargs
    )
    return payload
