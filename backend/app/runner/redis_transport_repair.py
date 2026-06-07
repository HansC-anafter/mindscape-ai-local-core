"""Redis runner transport repair helpers."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Awaitable, Callable, Optional

from backend.app.models.workspace import TaskStatus
from backend.app.services.stores.redis.runner_queue_store import RedisRunnerQueueStore

TERMINAL_TASK_STATUSES = {
    TaskStatus.SUCCEEDED,
    TaskStatus.FAILED,
    TaskStatus.CANCELLED_BY_USER,
    TaskStatus.EXPIRED,
}


def normalize_task_id(raw_value: object) -> str:
    if isinstance(raw_value, bytes):
        return raw_value.decode()
    return str(raw_value)


def resolve_transport_queue_store(
    redis_queue: RedisRunnerQueueStore,
    queue_shard: Optional[str],
) -> RedisRunnerQueueStore:
    normalized_shard = str(queue_shard or "").strip()
    if not normalized_shard or normalized_shard == redis_queue.pack_id:
        return redis_queue
    return RedisRunnerQueueStore(pack_id=normalized_shard)


async def reconcile_transport_membership(
    redis_queue: RedisRunnerQueueStore,
    *,
    task_id: str,
    reenqueue_pending: bool,
) -> None:
    client = await redis_queue._get_client()
    if not client:
        return
    normalized_task_id = str(task_id or "").strip()
    if not normalized_task_id:
        return

    pipe = client.pipeline()
    pipe.lrem(redis_queue.q_pending, 0, normalized_task_id)
    pipe.lrem(redis_queue.q_temp, 0, normalized_task_id)
    pipe.zrem(redis_queue.q_processing, normalized_task_id)
    pipe.zrem(redis_queue.q_delayed, normalized_task_id)
    if reenqueue_pending:
        pipe.lpush(redis_queue.q_pending, normalized_task_id)
    await pipe.execute()


def task_is_runnable_pending(task: Any) -> bool:
    if getattr(task, "status", None) != TaskStatus.PENDING:
        return False
    if getattr(task, "blocked_reason", None):
        return False
    return getattr(task, "frontier_state", "ready") == "ready"


def task_context(task: Any) -> dict[str, Any]:
    ctx = getattr(task, "execution_context", None)
    return ctx if isinstance(ctx, dict) else {}


def task_heartbeat_is_fresh(
    task: Any,
    ctx: dict[str, Any],
    *,
    stale_limit: datetime,
    effective_heartbeat_at: Callable[[Any, dict[str, Any]], Optional[datetime]],
) -> bool:
    heartbeat_at = effective_heartbeat_at(task, ctx)
    return bool(heartbeat_at and heartbeat_at > stale_limit)


async def recycle_visibility_timeout_item(
    *,
    tasks_store: Any,
    redis_queue: RedisRunnerQueueStore,
    task_id: str,
    now_dt: datetime,
    stale_limit: datetime,
    effective_heartbeat_at: Callable[[Any, dict[str, Any]], Optional[datetime]],
    reconcile_membership: Callable[..., Awaitable[None]],
) -> str:
    task = await asyncio.to_thread(tasks_store.get_task, task_id)
    if not task:
        await reconcile_membership(
            redis_queue,
            task_id=task_id,
            queue_shard=getattr(redis_queue, "pack_id", None),
            reenqueue_pending=False,
        )
        return "acked_missing"

    status = getattr(task, "status", None)
    if status in TERMINAL_TASK_STATUSES:
        await reconcile_membership(
            redis_queue,
            task_id=task_id,
            queue_shard=getattr(task, "queue_shard", None),
            reenqueue_pending=False,
        )
        return "acked_terminal"

    if status == TaskStatus.PENDING and not task_is_runnable_pending(task):
        await reconcile_membership(
            redis_queue,
            task_id=task_id,
            queue_shard=getattr(task, "queue_shard", None),
            reenqueue_pending=False,
        )
        return "acked_non_runnable"

    ctx = task_context(task)
    if status == TaskStatus.RUNNING and task_heartbeat_is_fresh(
        task,
        ctx,
        stale_limit=stale_limit,
        effective_heartbeat_at=effective_heartbeat_at,
    ):
        await redis_queue.touch_visibility_timeout(task_id, 180)
        return "touched_fresh"

    ctx2 = dict(ctx)
    ctx2.pop("runner_id", None)
    ctx2.pop("heartbeat_at", None)
    ctx2["status"] = "queued"
    await asyncio.to_thread(
        tasks_store.update_task,
        task_id,
        execution_context=ctx2,
        status=TaskStatus.PENDING,
        started_at=None,
        next_eligible_at=now_dt,
        blocked_reason=None,
        blocked_payload=None,
        runner_id=None,
        heartbeat_at=None,
        frontier_state="ready",
        frontier_enqueued_at=now_dt,
    )
    await reconcile_membership(
        redis_queue,
        task_id=task_id,
        queue_shard=getattr(task, "queue_shard", None),
        reenqueue_pending=True,
    )
    return "requeued"
