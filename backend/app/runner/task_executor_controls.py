"""Task executor lock, lease, and control signal helpers."""

from typing import Dict, Optional

from backend.app.models.workspace import Task, TaskStatus
from backend.app.services.runner_resources import (
    NodeBudgetReservation,
    release_task_resource_ownership,
)
from backend.app.services.stores.redis.runner_queue_store import RedisRunnerQueueStore


async def _release_task_locks(
    redis_queue: Optional[RedisRunnerQueueStore],
    lock_keys: list[str],
    lock_owner_id: str,
) -> None:
    if not redis_queue or not lock_keys:
        return
    for held_key in lock_keys:
        try:
            await redis_queue.release_lock(
                lock_key=held_key,
                owner_id=lock_owner_id,
            )
        except Exception:
            pass


async def _release_task_resource_leases(
    redis_queue: Optional[RedisRunnerQueueStore],
    resource_lease_keys: list[str],
    lock_owner_id: str,
    node_budget_reservation: Optional[NodeBudgetReservation] = None,
) -> None:
    if not redis_queue or not (resource_lease_keys or node_budget_reservation):
        return
    await release_task_resource_ownership(
        redis_queue,
        owner_id=lock_owner_id,
        lease_keys=resource_lease_keys,
        node_budget_reservation=node_budget_reservation,
    )


def _get_task_control_signal(task: Optional[Task]) -> Optional[Dict[str, str]]:
    """Return a runner control signal derived from task status/context."""
    if not task:
        return {"kind": "missing", "message": "Runner task record missing"}

    if task.status == TaskStatus.CANCELLED_BY_USER:
        return {"kind": "cancelled", "message": task.error or "Cancelled by user"}
    if task.status == TaskStatus.EXPIRED:
        return {"kind": "expired", "message": task.error or "Task expired externally"}

    ctx = task.execution_context if isinstance(task.execution_context, dict) else {}
    watchdog_abort = ctx.get("watchdog_abort")
    if not isinstance(watchdog_abort, dict):
        watchdog_abort = {}
    requested_at = ctx.get("watchdog_abort_requested_at") or watchdog_abort.get(
        "requested_at"
    )
    if requested_at:
        reason = (
            ctx.get("watchdog_abort_reason")
            or watchdog_abort.get("reason")
            or "Watchdog requested abort"
        )
        return {"kind": "watchdog_abort", "message": reason}
    return None
