"""Redis transport repair and frontier refill helpers for the runner reaper."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Awaitable, Callable, Optional

from backend.app.models.workspace import Task, TaskStatus
from backend.app.services.stores.tasks_store import TasksStore
from backend.app.services.stores.redis.runner_queue_store import RedisRunnerQueueStore
from backend.app.services.host_resources.route_identity_projection import (
    build_route_identity_projection,
    read_route_identity_projections,
)
from backend.app.runner.concurrency import _resolve_lock_keys
from backend.app.runner.redis_transport_repair import (
    TERMINAL_TASK_STATUSES,
    reconcile_transport_membership,
    recycle_visibility_timeout_item,
    resolve_transport_queue_store,
    task_is_runnable_pending,
)
from backend.app.runner.reaper_context import (
    _BROWSER_LOCAL_QUEUE_SHARD,
    _BROWSER_PEER_FRONTIER_LANES,
    _browser_peer_frontier_refill_limit,
    _effective_task_heartbeat_at,
    _normalize_task_id,
    logger,
)
from backend.app.runner.utils import _env_int, _utc_now

async def _mark_frontier_ready(
    tasks_store: TasksStore,
    task_ids: list[str],
    *,
    queue_shard: str,
) -> None:
    """Mirror Redis ready-enqueue into DB scheduler fields for observability."""
    if not task_ids:
        return

    enqueued_at = _utc_now()
    for task_id in task_ids:
        try:
            await asyncio.to_thread(
                tasks_store.update_task,
                task_id,
                blocked_reason=None,
                blocked_payload=None,
                queue_shard=queue_shard,
                frontier_state="ready",
                frontier_enqueued_at=enqueued_at,
                next_eligible_at=enqueued_at,
                return_updated=False,
            )
        except Exception as e:
            logger.warning(
                f"[Bridge] Failed to mirror ready frontier state for task {task_id}: {e}"
            )

async def _queued_transport_task_ids(
    queue_family: list[RedisRunnerQueueStore],
) -> list[str]:
    queued: list[str] = []
    for queue_store in queue_family:
        queue_client = await queue_store._get_client()
        if not queue_client:
            continue
        pending_members = await queue_client.lrange(queue_store.q_pending, 0, -1)
        temp_members = await queue_client.lrange(queue_store.q_temp, 0, -1)
        processing_members = await queue_client.zrange(queue_store.q_processing, 0, -1)
        delayed_members = await queue_client.zrange(queue_store.q_delayed, 0, -1)
        queued.extend(_normalize_task_id(task_id) for task_id in pending_members)
        queued.extend(_normalize_task_id(task_id) for task_id in temp_members)
        queued.extend(_normalize_task_id(task_id) for task_id in processing_members)
        queued.extend(_normalize_task_id(task_id) for task_id in delayed_members)
    return list(dict.fromkeys(queued))

def _browser_lane_key_from_task(task: Task) -> Optional[str]:
    try:
        from backend.app.runner.browser_fair_candidate_scheduler import (
            normalize_browser_lane_key,
        )

        ctx = task.execution_context if isinstance(task.execution_context, dict) else {}
        return normalize_browser_lane_key(
            getattr(task, "pack_id", None),
            ctx.get("playbook_code"),
        )
    except Exception:
        return None

async def _queued_browser_peer_lanes(
    client: Any,
    queued_task_ids: list[str],
) -> set[str]:
    if not queued_task_ids:
        return set()
    try:
        from backend.app.runner.browser_fair_candidate_scheduler import (
            normalize_browser_lane_key,
        )

        scan_limit = max(
            1,
            _env_int("LOCAL_CORE_RUNNER_BROWSER_PEER_SCAN_LIMIT", 512),
        )
        projections = await read_route_identity_projections(
            client,
            queued_task_ids[:scan_limit],
        )
        lanes: set[str] = set()
        for projection in projections.values():
            lane_key = normalize_browser_lane_key(
                projection.get("pack_id"),
                projection.get("playbook_code"),
            )
            if lane_key in _BROWSER_PEER_FRONTIER_LANES:
                lanes.add(lane_key)
        return lanes
    except Exception:
        return set()

async def _refill_browser_peer_frontier(
    tasks_store: TasksStore,
    redis_queue: RedisRunnerQueueStore,
    *,
    all_queues: Optional[list[RedisRunnerQueueStore]] = None,
) -> int:
    """Keep browser peer playbooks visible even when the hot queue is full."""
    if redis_queue.pack_id != _BROWSER_LOCAL_QUEUE_SHARD:
        return 0

    refill_limit = _browser_peer_frontier_refill_limit()
    if refill_limit <= 0:
        return 0

    client = await redis_queue._get_client()
    if not client:
        return 0

    queue_family = all_queues or [redis_queue]
    queued_task_ids = await _queued_transport_task_ids(queue_family)
    queued_task_id_set = set(queued_task_ids)
    queued_lanes = await _queued_browser_peer_lanes(client, queued_task_ids)
    if _BROWSER_PEER_FRONTIER_LANES.issubset(queued_lanes):
        return 0

    candidate_limit = max(refill_limit * 8, refill_limit)
    pending_tasks = await asyncio.to_thread(
        tasks_store.list_runnable_playbook_execution_tasks,
        None,
        candidate_limit,
        redis_queue.pack_id,
    )

    selected_tasks: list[Task] = []
    selected_lanes: set[str] = set()
    for task in pending_tasks:
        task_id = str(getattr(task, "id", "") or "").strip()
        if not task_id or task_id in queued_task_id_set:
            continue
        lane_key = _browser_lane_key_from_task(task)
        if lane_key not in _BROWSER_PEER_FRONTIER_LANES:
            continue
        if lane_key in queued_lanes or lane_key in selected_lanes:
            continue
        selected_tasks.append(task)
        selected_lanes.add(lane_key)
        if len(selected_tasks) >= refill_limit:
            break

    if not selected_tasks:
        return 0

    for task in selected_tasks:
        await redis_queue.enqueue_task(
            str(task.id),
            route_identity=build_route_identity_projection(task),
        )

    await _mark_frontier_ready(
        tasks_store,
        [str(task.id) for task in selected_tasks],
        queue_shard=redis_queue.pack_id,
    )
    logger.warning(
        "[Bridge] Refilled browser peer frontier with %d task(s) lanes=%s.",
        len(selected_tasks),
        ",".join(sorted(selected_lanes)),
    )
    return len(selected_tasks)

def _force_release_lock(
    task_ctx: dict,
    pack_id: str,
    redis_queue: Optional[RedisRunnerQueueStore],
    persisted_concurrency_key: Optional[str] = None,
    event_loop: Optional[asyncio.AbstractEventLoop] = None,
) -> None:
    """Force-delete the concurrency lock for a reaped task.

    The owning runner is dead, so we can't use compare-and-delete.
    We just DEL the key directly.
    Called from sync code inside an async event loop.
    """
    if not redis_queue:
        return
    lock_keys = _resolve_lock_keys(
        task_ctx,
        pack_id,
        persisted_concurrency_key=persisted_concurrency_key,
    )
    if not lock_keys:
        return
    try:
        loop = event_loop
        if loop is None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
        if loop is None or not loop.is_running():
            logger.warning(
                "[Reaper] No running event loop available to release lock(s) %s",
                lock_keys,
            )
            return
        for lock_key in lock_keys:
            asyncio.run_coroutine_threadsafe(
                _async_force_release(redis_queue, lock_key),
                loop,
            )
    except Exception as e:
        logger.warning(f"[Reaper] Failed to schedule lock release for {lock_keys}: {e}")

async def _async_force_release(
    redis_queue: RedisRunnerQueueStore, lock_key: str
) -> None:
    """Async helper to force-delete a lock key."""
    try:
        client = await redis_queue._get_client()
        if client:
            deleted = await client.delete(lock_key)
            if deleted:
                logger.info(f"[Reaper] Force-released lock {lock_key}")
    except Exception as e:
        logger.warning(f"[Reaper] Failed to force-release lock {lock_key}: {e}")

def _resolve_transport_queue_store(
    redis_queue: RedisRunnerQueueStore,
    queue_shard: Optional[str],
) -> RedisRunnerQueueStore:
    return resolve_transport_queue_store(redis_queue, queue_shard)

async def _async_reconcile_transport_membership(
    redis_queue: RedisRunnerQueueStore,
    *,
    task_id: str,
    queue_shard: Optional[str],
    reenqueue_pending: bool,
    resolve_transport_queue_store_func: Callable[
        [RedisRunnerQueueStore, Optional[str]], RedisRunnerQueueStore
    ] = _resolve_transport_queue_store,
) -> None:
    target_queue = resolve_transport_queue_store_func(redis_queue, queue_shard)
    if target_queue is not redis_queue:
        await reconcile_transport_membership(
            redis_queue,
            task_id=task_id,
            reenqueue_pending=False,
        )
    await reconcile_transport_membership(
        target_queue,
        task_id=task_id,
        reenqueue_pending=reenqueue_pending,
    )

async def _recycle_visibility_timeout_item(
    *,
    tasks_store: TasksStore,
    redis_queue: RedisRunnerQueueStore,
    client: Any,
    task_id: str,
    now_dt: datetime,
    stale_limit: datetime,
    effective_task_heartbeat_at: Callable[
        [Any, dict[str, Any]], Optional[datetime]
    ] = _effective_task_heartbeat_at,
    reconcile_transport_membership: Callable[..., Awaitable[None]] = _async_reconcile_transport_membership,
) -> str:
    return await recycle_visibility_timeout_item(
        tasks_store=tasks_store,
        redis_queue=redis_queue,
        task_id=task_id,
        now_dt=now_dt,
        stale_limit=stale_limit,
        effective_heartbeat_at=effective_task_heartbeat_at,
        reconcile_membership=reconcile_transport_membership,
    )

async def _reconcile_temp_transport_items(
    tasks_store: TasksStore,
    redis_queue: RedisRunnerQueueStore,
    client: Any,
    *,
    scan_limit: int,
) -> int:
    if scan_limit <= 0:
        return 0
    temp_items = await client.lrange(redis_queue.q_temp, 0, max(0, scan_limit - 1))
    repaired = 0
    for raw_task_id in temp_items:
        task_id = _normalize_task_id(raw_task_id).strip()
        if not task_id:
            continue
        task = await asyncio.to_thread(tasks_store.get_task, task_id)
        if not task:
            await _async_reconcile_transport_membership(
                redis_queue,
                task_id=task_id,
                queue_shard=redis_queue.pack_id,
                reenqueue_pending=False,
            )
            repaired += 1
            continue
        status = getattr(task, "status", None)
        if status in TERMINAL_TASK_STATUSES or status == TaskStatus.RUNNING:
            await _async_reconcile_transport_membership(
                redis_queue,
                task_id=task_id,
                queue_shard=getattr(task, "queue_shard", None),
                reenqueue_pending=False,
            )
            repaired += 1
            continue
        await _async_reconcile_transport_membership(
            redis_queue,
            task_id=task_id,
            queue_shard=getattr(task, "queue_shard", None),
            reenqueue_pending=task_is_runnable_pending(task),
        )
        repaired += 1
    return repaired

async def _scrub_processing_terminal_items(
    tasks_store: TasksStore,
    redis_queue: RedisRunnerQueueStore,
    client: Any,
    *,
    skip_task_ids: set[str],
    scan_limit: int,
) -> int:
    if scan_limit <= 0:
        return 0
    processing_items = await client.zrange(
        redis_queue.q_processing,
        0,
        max(0, scan_limit - 1),
    )
    repaired = 0
    for raw_task_id in processing_items:
        task_id = _normalize_task_id(raw_task_id).strip()
        if not task_id or task_id in skip_task_ids:
            continue
        task = await asyncio.to_thread(tasks_store.get_task, task_id)
        if not task:
            await _async_reconcile_transport_membership(
                redis_queue,
                task_id=task_id,
                queue_shard=redis_queue.pack_id,
                reenqueue_pending=False,
            )
            repaired += 1
            continue
        status = getattr(task, "status", None)
        if status in TERMINAL_TASK_STATUSES or (
            status == TaskStatus.PENDING and not task_is_runnable_pending(task)
        ):
            await _async_reconcile_transport_membership(
                redis_queue,
                task_id=task_id,
                queue_shard=getattr(task, "queue_shard", None),
                reenqueue_pending=False,
            )
            repaired += 1
    return repaired
