"""Exact state transition tables for the three workflow kinds."""

from __future__ import annotations

INITIAL_STATES = {
    "execution": "pending",
    "product_iteration": "draft",
    "product_release": "draft",
}

TRANSITIONS = {
    "execution": {
        "pending": frozenset({"running", "waiting", "cancelled"}),
        "running": frozenset(
            {"waiting", "succeeded", "failed", "cancelled", "escalated"}
        ),
        "waiting": frozenset({"running", "cancelled", "escalated"}),
        "succeeded": frozenset(),
        "failed": frozenset(),
        "cancelled": frozenset(),
        "escalated": frozenset(),
    },
    "product_iteration": {
        "draft": frozenset({"admitted", "cancelled", "superseded"}),
        "admitted": frozenset({"collecting", "cancelled", "superseded"}),
        "collecting": frozenset(
            {"evidence_ready", "inconclusive", "cancelled", "superseded"}
        ),
        "evidence_ready": frozenset(
            {"decision_pending", "inconclusive", "cancelled", "superseded"}
        ),
        "decision_pending": frozenset(
            {"promoted", "rejected", "inconclusive", "cancelled", "superseded"}
        ),
        "promoted": frozenset(),
        "rejected": frozenset(),
        "inconclusive": frozenset(),
        "cancelled": frozenset(),
        "superseded": frozenset(),
    },
    "product_release": {
        "draft": frozenset({"observing"}),
        "observing": frozenset({"healthy", "rollback_required", "inconclusive"}),
        "rollback_required": frozenset(
            {"rollback_authorized", "rollback_blocked"}
        ),
        "rollback_authorized": frozenset({"rollback_effect_pending"}),
        "rollback_effect_pending": frozenset(
            {"rollback_completed", "rollback_failed"}
        ),
        "healthy": frozenset(),
        "inconclusive": frozenset(),
        "rollback_blocked": frozenset(),
        "rollback_completed": frozenset(),
        "rollback_failed": frozenset(),
    },
}


class InvalidTransition(ValueError):
    """Raised when a durable transition is not in the versioned table."""


def initial_state(workflow_kind: str) -> str:
    try:
        return INITIAL_STATES[workflow_kind]
    except KeyError as exc:
        raise InvalidTransition(f"unknown workflow kind: {workflow_kind}") from exc


def require_transition(workflow_kind: str, current: str, target: str) -> bool:
    allowed = TRANSITIONS.get(workflow_kind, {}).get(current)
    if allowed is None or target not in allowed:
        raise InvalidTransition(
            f"{workflow_kind} transition {current!r} -> {target!r} is forbidden"
        )
    return not TRANSITIONS[workflow_kind][target]
