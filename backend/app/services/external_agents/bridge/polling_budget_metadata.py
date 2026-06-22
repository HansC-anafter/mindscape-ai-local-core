"""Polling transport budget metadata helpers."""

from __future__ import annotations

from typing import Any, Mapping


def _coerce_int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_float(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def build_polling_budget_metadata(
    *,
    reason: str,
    client: Any | None = None,
    reserve_limit: int = 1,
    lease_seconds: float | None = None,
    wait_seconds: float | None = None,
    heartbeat_interval_seconds: float | None = None,
    wait_slice_seconds: float | None = None,
    active_tasks: int | None = None,
) -> dict[str, Any]:
    """Describe the bounded polling budget without mutating runtime behavior."""

    if client is not None:
        lease_seconds = lease_seconds if lease_seconds is not None else getattr(
            client,
            "POLLING_LEASE_SECONDS",
            None,
        )
        wait_seconds = wait_seconds if wait_seconds is not None else getattr(
            client,
            "POLLING_WAIT_SECONDS",
            None,
        )
        heartbeat_interval_seconds = (
            heartbeat_interval_seconds
            if heartbeat_interval_seconds is not None
            else getattr(client, "POLLING_HEARTBEAT_INTERVAL", None)
        )
        active_tasks = active_tasks if active_tasks is not None else getattr(
            client,
            "_active_tasks",
            None,
        )

    metadata = {
        "bounded": True,
        "reason": reason,
        "reserve_limit": _coerce_int(reserve_limit, default=1),
    }
    if lease_seconds is not None:
        metadata["lease_seconds"] = _coerce_float(lease_seconds, default=0.0)
    if wait_seconds is not None:
        metadata["wait_seconds"] = _coerce_float(wait_seconds, default=0.0)
    if heartbeat_interval_seconds is not None:
        metadata["heartbeat_interval_seconds"] = _coerce_float(
            heartbeat_interval_seconds,
            default=0.0,
        )
    if wait_slice_seconds is not None:
        metadata["wait_slice_seconds"] = _coerce_float(
            wait_slice_seconds,
            default=0.0,
        )
    if active_tasks is not None:
        metadata["active_tasks"] = max(0, _coerce_int(active_tasks, default=0))
    return metadata


def attach_polling_budget_metadata(
    metadata: Mapping[str, Any] | None,
    *,
    reason: str,
    client: Any | None = None,
    reserve_limit: int = 1,
    lease_seconds: float | None = None,
    wait_seconds: float | None = None,
    heartbeat_interval_seconds: float | None = None,
    wait_slice_seconds: float | None = None,
    active_tasks: int | None = None,
) -> dict[str, Any]:
    """Return metadata with bounded polling budget observability attached."""

    result = dict(metadata or {})
    result["polling_budget"] = build_polling_budget_metadata(
        reason=reason,
        client=client,
        reserve_limit=reserve_limit,
        lease_seconds=lease_seconds,
        wait_seconds=wait_seconds,
        heartbeat_interval_seconds=heartbeat_interval_seconds,
        wait_slice_seconds=wait_slice_seconds,
        active_tasks=active_tasks,
    )
    return result
