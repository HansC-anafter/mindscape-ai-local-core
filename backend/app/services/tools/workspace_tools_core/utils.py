"""Utility helpers for workspace tools."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .constants import RECENT_CANDIDATE_WINDOW
from .types import ExecutionCandidate


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


def task_to_payload(task: Any) -> dict[str, Any]:
    """Convert task-like objects into a JSON-serializable payload dict."""
    if hasattr(task, "model_dump"):
        return task.model_dump(mode="json")
    if isinstance(task, dict):
        return dict(task)
    if hasattr(task, "__dict__"):
        return dict(task.__dict__)
    return {}


def select_recent_candidates(
    candidates: list[ExecutionCandidate],
    *,
    now: datetime | None = None,
) -> list[ExecutionCandidate]:
    """Return candidates created within the configured recent window."""
    reference = now or utc_now()
    threshold = reference - RECENT_CANDIDATE_WINDOW
    recent_candidates: list[ExecutionCandidate] = []
    for candidate in candidates:
        created_at = candidate.get("created_at")
        if not created_at:
            continue
        try:
            if isinstance(created_at, str):
                created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            else:
                created_dt = created_at
            if created_dt > threshold:
                recent_candidates.append(candidate)
        except Exception:
            continue
    return recent_candidates
