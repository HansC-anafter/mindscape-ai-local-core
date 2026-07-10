"""Read-only observation of a task claimed through the canonical runner path."""

from __future__ import annotations

import time
from typing import Any

from .envelope_classifier import classify_task_envelope


class NaturalClaimObservationError(RuntimeError):
    """Raised when a natural claim cannot be attributed without ambiguity."""


def select_fresh_running_task(
    rows: list[dict[str, Any]],
    *,
    observer_started_epoch: float,
) -> dict[str, Any] | None:
    fresh = [
        row
        for row in rows
        if float(row.get("started_at_epoch") or 0) >= float(observer_started_epoch)
    ]
    if len(fresh) > 1:
        ids = sorted(str(row.get("id") or "") for row in fresh)
        raise NaturalClaimObservationError(f"multiple_fresh_browser_claims:{','.join(ids)}")
    return fresh[0] if fresh else None


def validate_live_owner(task: dict[str, Any], live_owner: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    task_id = str(task.get("id") or "").strip()
    runner_id = str(task.get("runner_id") or "").strip()
    if str(live_owner.get("task_id") or "").strip() != task_id:
        failures.append("live_owner_task_mismatch")
    if str(live_owner.get("runner_id") or "").strip() != runner_id:
        failures.append("live_owner_runner_mismatch")
    if int(live_owner.get("ttl_seconds_remaining") or 0) <= 0:
        failures.append("live_owner_ttl_expired")
    return failures


def wait_for_natural_claim(
    collector: Any,
    *,
    observer_started_epoch: float,
    timeout_seconds: int,
    poll_interval_seconds: float = 1.0,
) -> dict[str, Any]:
    deadline = time.monotonic() + max(1, int(timeout_seconds))
    last_owner_failures: list[str] = []
    while time.monotonic() < deadline:
        list_live_owners = getattr(collector, "list_live_browser_owners", None)
        collect_running_task = getattr(
            collector,
            "collect_running_browser_task",
            None,
        )
        if callable(list_live_owners) and callable(collect_running_task):
            owners = list_live_owners()
            if len(owners) > 1:
                ids = sorted(str(row.get("task_id") or "") for row in owners)
                raise NaturalClaimObservationError(
                    f"multiple_fresh_browser_claims:{','.join(ids)}"
                )
            task = (
                collect_running_task(str(owners[0].get("task_id") or ""))
                if owners
                else None
            )
            if task and float(task.get("started_at_epoch") or 0) < float(
                observer_started_epoch
            ):
                task = None
        else:
            rows = collector.list_running_browser_tasks_started_after(
                observer_started_epoch
            )
            task = select_fresh_running_task(
                rows,
                observer_started_epoch=observer_started_epoch,
            )
        if task is None:
            time.sleep(max(0.1, float(poll_interval_seconds)))
            continue
        live_owner = collector.read_live_owner(str(task.get("id") or ""))
        last_owner_failures = validate_live_owner(task, live_owner)
        if last_owner_failures:
            time.sleep(max(0.1, float(poll_interval_seconds)))
            continue
        classification = classify_task_envelope(task)
        return {
            "task": task,
            "live_owner": live_owner,
            "classification": classification,
        }
    detail = ",".join(last_owner_failures) if last_owner_failures else "no_fresh_claim"
    raise NaturalClaimObservationError(f"natural_claim_timeout:{detail}")


__all__ = [
    "NaturalClaimObservationError",
    "select_fresh_running_task",
    "validate_live_owner",
    "wait_for_natural_claim",
]
