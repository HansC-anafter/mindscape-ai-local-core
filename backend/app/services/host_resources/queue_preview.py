"""Read-only queue preview for host resource route reservations."""

from __future__ import annotations

import asyncio
from typing import Any

from backend.app.models.workspace import TaskStatus
from backend.app.services.runner_topology import RUNNER_READY_QUEUE_ORDER
from backend.app.services.stores.redis.runner_queue_store import RedisRunnerQueueStore
from backend.app.services.stores.tasks_store import TasksStore

from . import route_gate


def _normalize_task_id(raw_value: object) -> str:
    if isinstance(raw_value, bytes):
        return raw_value.decode()
    return str(raw_value)


def _task_status_value(task: Any) -> str:
    status = getattr(task, "status", "")
    return str(getattr(status, "value", status))


def _task_summary(
    task: Any,
    *,
    queue_name: str,
    queue_position: int,
    score: int,
    reservation_id: str,
) -> dict[str, Any]:
    identity = route_gate.task_route_identity(task)
    return {
        "task_id": str(getattr(task, "id", "")),
        "queue": queue_name,
        "queue_position": queue_position,
        "score": score,
        "reservation_id": reservation_id,
        "pack_id": getattr(task, "pack_id", None),
        "task_type": getattr(task, "task_type", None),
        "workspace_id": getattr(task, "workspace_id", None),
        "blocked_reason": getattr(task, "blocked_reason", None),
        "route_identity": identity,
    }


async def _pending_task_ids(queue_store: Any, *, scan_limit: int) -> list[str]:
    client = await queue_store._get_client()
    if not client:
        return []
    raw_ids = await client.lrange(queue_store.q_pending, 0, max(0, scan_limit - 1))
    return [_normalize_task_id(raw).strip() for raw in raw_ids if _normalize_task_id(raw).strip()]


def _default_queue_stores() -> list[RedisRunnerQueueStore]:
    return [
        RedisRunnerQueueStore(pack_id=partition)
        for partition in RUNNER_READY_QUEUE_ORDER
    ]


async def build_route_reservation_candidate_previews(
    reservations: list[dict[str, Any]],
    *,
    scan_limit: int = 25,
    tasks_store: Any | None = None,
    queue_stores: list[Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Scan ready queues and summarize candidates for each route reservation.

    This is intentionally read-only. The worker still owns actual promotion.
    """

    tasks_store = tasks_store or TasksStore()
    queue_stores = queue_stores if queue_stores is not None else _default_queue_stores()
    scan_limit = max(1, min(int(scan_limit or 25), 200))
    previews: dict[str, dict[str, Any]] = {}
    active_reservations = [
        reservation
        for reservation in reservations
        if isinstance(reservation, dict)
        and reservation.get("state") in {"reserved_waiting", "permitted"}
    ]

    for reservation in reservations:
        reservation_id = str(reservation.get("reservation_id") or "")
        if not reservation_id:
            continue
        previews[reservation_id] = {
            "reservation_id": reservation_id,
            "state": "inactive" if reservation not in active_reservations else "scanned",
            "scan_limit": scan_limit,
            "queues_scanned": 0,
            "tasks_scanned": 0,
            "matching_count": 0,
            "selected_candidate": None,
            "matching_candidates": [],
        }

    if not active_reservations:
        return previews

    for queue_store in queue_stores:
        queue_name = str(getattr(queue_store, "pack_id", "") or getattr(queue_store, "q_pending", ""))
        try:
            task_ids = await _pending_task_ids(queue_store, scan_limit=scan_limit)
        except Exception as exc:
            for reservation in active_reservations:
                reservation_id = str(reservation.get("reservation_id") or "")
                if reservation_id in previews:
                    previews[reservation_id].setdefault("errors", []).append(
                        {
                            "queue": queue_name,
                            "error": str(exc),
                        }
                    )
            continue

        for reservation in active_reservations:
            reservation_id = str(reservation.get("reservation_id") or "")
            if reservation_id in previews:
                previews[reservation_id]["queues_scanned"] += 1
                previews[reservation_id]["tasks_scanned"] += len(task_ids)

        seen: set[str] = set()
        for position, task_id in enumerate(task_ids):
            if task_id in seen:
                continue
            seen.add(task_id)
            try:
                task = await asyncio.to_thread(tasks_store.get_task, task_id)
            except Exception:
                continue
            if not task or _task_status_value(task) != TaskStatus.PENDING.value:
                continue

            for reservation in active_reservations:
                reservation_id = str(reservation.get("reservation_id") or "")
                if not reservation_id or reservation_id not in previews:
                    continue
                decision = route_gate.evaluate_route_candidate(
                    task,
                    active_reservations=[reservation],
                )
                if not decision.permit:
                    continue
                preview = previews[reservation_id]
                summary = _task_summary(
                    task,
                    queue_name=queue_name,
                    queue_position=position,
                    score=decision.score,
                    reservation_id=reservation_id,
                )
                preview["matching_count"] += 1
                if len(preview["matching_candidates"]) < 5:
                    preview["matching_candidates"].append(summary)
                selected = preview.get("selected_candidate")
                if not selected or int(summary["score"]) > int(selected.get("score") or 0):
                    preview["selected_candidate"] = summary

    return previews
