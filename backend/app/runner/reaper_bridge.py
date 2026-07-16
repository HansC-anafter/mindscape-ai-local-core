"""Redis bridge orchestration for the runner reaper."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Awaitable, Callable, Optional

from backend.app.models.workspace import TaskStatus
from backend.app.services.stores.tasks_store import TasksStore
from backend.app.services.stores.tasks_store._crud_helpers import (
    normalize_task_status_value,
)
from backend.app.services.stores.redis.runner_queue_store import RedisRunnerQueueStore
from backend.app.services.host_resources.route_identity_projection import (
    build_route_identity_projection,
)
from backend.app.runner.database_backoff import is_database_recovery_error
from backend.app.runner.reaper_context import (
    _BROWSER_LOCAL_QUEUE_SHARD,
    _DEFAULT_LOCAL_BROWSER_QUEUE_SHARD,
    _blocked_release_limit,
    _normalize_task_id,
    logger,
)
from backend.app.runner.utils import _env_int, _utc_now

_PIPELINE_BATCH = 100
_BROWSER_LOCAL_RESOURCE_WAIT_RELEASE_MINIMUM = 4


async def _refill_ready_frontier_from_db(
    tasks_store: TasksStore,
    redis_queue: RedisRunnerQueueStore,
    *,
    client,
    ready_depth: int,
    ready_target: int,
    all_queues: Optional[list[RedisRunnerQueueStore]],
    mark_frontier_ready: Callable[..., Awaitable[None]],
    build_route_identity_projection_func: Callable[..., dict],
) -> int:
    """Refill Redis from already-runnable DB frontier before releasing parked work."""

    refill_limit = max(0, ready_target - ready_depth)
    if refill_limit <= 0:
        return 0

    queue_family = all_queues or [redis_queue]
    all_queued = set()
    for queue_store in queue_family:
        queue_client = client if queue_store is redis_queue else await queue_store._get_client()
        if not queue_client:
            continue
        pending_members = await queue_client.lrange(queue_store.q_pending, 0, -1)
        temp_members = await queue_client.lrange(queue_store.q_temp, 0, -1)
        processing_members = await queue_client.zrange(
            queue_store.q_processing, 0, -1
        )
        delayed_members = await queue_client.zrange(
            queue_store.q_delayed, 0, -1
        )
        all_queued.update(_normalize_task_id(task_id) for task_id in pending_members)
        all_queued.update(_normalize_task_id(task_id) for task_id in temp_members)
        all_queued.update(
            _normalize_task_id(task_id) for task_id in processing_members
        )
        all_queued.update(_normalize_task_id(task_id) for task_id in delayed_members)

    pending_tasks = await asyncio.to_thread(
        tasks_store.list_runnable_playbook_execution_tasks,
        None,
        max(refill_limit * 4, refill_limit),
        redis_queue.pack_id,
    )

    missing_tasks = []
    for task in pending_tasks:
        if str(task.id) not in all_queued:
            missing_tasks.append(task)
        if len(missing_tasks) >= refill_limit:
            break

    if not missing_tasks:
        return 0

    for i in range(0, len(missing_tasks), _PIPELINE_BATCH):
        batch = missing_tasks[i:i + _PIPELINE_BATCH]
        for task in batch:
            await redis_queue.enqueue_task(
                str(task.id),
                route_identity=build_route_identity_projection_func(task),
            )
        if i + _PIPELINE_BATCH < len(missing_tasks):
            await asyncio.sleep(0)
    await mark_frontier_ready(
        tasks_store,
        [str(task.id) for task in missing_tasks],
        queue_shard=redis_queue.pack_id,
    )
    logger.warning(
        "[Bridge] Refilled ready frontier with %d task(s) "
        "(ready_depth=%s, ready_target=%s).",
        len(missing_tasks),
        ready_depth,
        ready_target,
    )
    return len(missing_tasks)


async def _reap_redis_queues(
    tasks_store: TasksStore,
    redis_queue: RedisRunnerQueueStore,
    *,
    ready_target_override: Optional[int] = None,
    all_queues: Optional[list[RedisRunnerQueueStore]] = None,
    mark_frontier_ready: Callable[..., Awaitable[None]],
    reconcile_temp_transport_items: Callable[..., Awaitable[int]],
    scrub_processing_terminal_items: Callable[..., Awaitable[int]],
    recycle_visibility_timeout_item: Callable[..., Awaitable[str]],
    release_concurrency_locked_tasks: Callable[..., Awaitable[int]],
    release_dependency_hold_tasks: Callable[..., Awaitable[int]],
    release_resource_wait_tasks: Callable[..., Awaitable[int]],
    release_workspace_quota_tasks: Callable[..., Awaitable[int]],
    release_admission_deferred_tasks: Callable[..., Awaitable[int]],
    release_unblocked_cold_tasks: Callable[..., Awaitable[int]],
    refill_browser_peer_frontier: Callable[..., Awaitable[int]],
    build_route_identity_projection_func: Callable[..., dict],
) -> None:
    """Orchestrator background loop for Redis Queue reliability guarantees."""
    try:
        client = await redis_queue._get_client()
        if not client:
            return
            
        now_ts = redis_queue._utc_now_timestamp()
        ready_target = ready_target_override or _env_int("LOCAL_CORE_RUNNER_READY_TARGET", 64)
        delayed_move_limit = _env_int("LOCAL_CORE_RUNNER_DELAYED_MOVE_LIMIT", 100)
        transport_repair_limit = _env_int("LOCAL_CORE_RUNNER_TRANSPORT_REPAIR_LIMIT", 100)
        
        # 1. Delayed Queue Mover — move in small pipeline batches to avoid
        #    blocking Redis single-threaded processing (SLOWLOG showed 17ms for 688-item pipeline).
        delayed_items = await client.zrangebyscore(
            redis_queue.q_delayed, "-inf", now_ts, start=0, num=delayed_move_limit
        )
        if delayed_items:
            try:
                moved_task_ids: list[str] = []
                for i in range(0, len(delayed_items), _PIPELINE_BATCH):
                    batch = delayed_items[i:i + _PIPELINE_BATCH]
                    for task_id in batch:
                        normalized_task_id = _normalize_task_id(task_id)
                        try:
                            task = await asyncio.to_thread(
                                tasks_store.get_task,
                                normalized_task_id,
                            )
                        except ValueError as task_status_error:
                            logger.warning(
                                "[Bridge] Dropping unreadable delayed queue item task_id=%s shard=%s: %s",
                                normalized_task_id,
                                redis_queue.pack_id,
                                task_status_error,
                            )
                            await client.zrem(redis_queue.q_delayed, task_id)
                            continue
                        if task is None:
                            await client.zrem(redis_queue.q_delayed, task_id)
                            continue
                        status_raw = normalize_task_status_value(getattr(task, "status", None))
                        if status_raw != TaskStatus.PENDING.value:
                            await client.zrem(redis_queue.q_delayed, task_id)
                            continue
                        try:
                            route_identity = build_route_identity_projection_func(task)
                        except ValueError as task_status_error:
                            logger.warning(
                                "[Bridge] Dropping delayed queue item with invalid route projection task_id=%s shard=%s: %s",
                                normalized_task_id,
                                redis_queue.pack_id,
                                task_status_error,
                            )
                            await client.zrem(redis_queue.q_delayed, task_id)
                            continue
                        await redis_queue.enqueue_task(
                            normalized_task_id,
                            route_identity=route_identity,
                        )
                        await client.zrem(redis_queue.q_delayed, task_id)
                        moved_task_ids.append(normalized_task_id)
                    # Yield so Redis can serve other clients between batches
                    if i + _PIPELINE_BATCH < len(delayed_items):
                        await asyncio.sleep(0)
                if moved_task_ids:
                    await mark_frontier_ready(
                        tasks_store,
                        moved_task_ids,
                        queue_shard=redis_queue.pack_id,
                    )
                logger.info(f"[Bridge] Moved {len(moved_task_ids)} tasks from delayed to pending queue.")
            except Exception as e:
                logger.warning(f"Failed to batch move delayed tasks: {e}")

        temp_repaired = await reconcile_temp_transport_items(
            tasks_store,
            redis_queue,
            client,
            scan_limit=transport_repair_limit,
        )
        if temp_repaired:
            logger.warning(
                "[Bridge] Repaired %d temp transport member(s) on shard %s.",
                temp_repaired,
                redis_queue.pack_id,
            )

        # 2. Visibility Timeout Recycler
        stale_items = await client.zrangebyscore(redis_queue.q_processing, "-inf", now_ts)
        stale_item_ids = {_normalize_task_id(task_id) for task_id in stale_items}
        scrubbed_count = await scrub_processing_terminal_items(
            tasks_store,
            redis_queue,
            client,
            skip_task_ids=stale_item_ids,
            scan_limit=transport_repair_limit,
        )
        if scrubbed_count:
            logger.warning(
                "[Bridge] Scrubbed %d invalid processing transport member(s) on shard %s.",
                scrubbed_count,
                redis_queue.pack_id,
            )
        for task_id in stale_items:
            try:
                result = await recycle_visibility_timeout_item(
                    tasks_store=tasks_store,
                    redis_queue=redis_queue,
                    client=client,
                    task_id=_normalize_task_id(task_id),
                    now_dt=_utc_now(),
                    stale_limit=_utc_now()
                    - timedelta(
                        seconds=_env_int("LOCAL_CORE_RUNNER_STALE_TASK_SECONDS", 180)
                    ),
                )
                if result == "requeued":
                    logger.warning(
                        "[Bridge] Task %s visibility timeout expired. Reverting to queue.",
                        _normalize_task_id(task_id),
                    )
            except Exception as e:
                logger.error(f"Failed to recycle visibility task {task_id}: {e}")

        ready_depth = await client.llen(redis_queue.q_pending)
        try:
            ready_refilled_count = await _refill_ready_frontier_from_db(
                tasks_store,
                redis_queue,
                client=client,
                ready_depth=ready_depth,
                ready_target=ready_target,
                all_queues=all_queues,
                mark_frontier_ready=mark_frontier_ready,
                build_route_identity_projection_func=build_route_identity_projection_func,
            )
            if ready_refilled_count:
                ready_depth += ready_refilled_count
                if redis_queue.pack_id not in {
                    _BROWSER_LOCAL_QUEUE_SHARD,
                    _DEFAULT_LOCAL_BROWSER_QUEUE_SHARD,
                }:
                    return
        except Exception as e:
            logger.error(f"[Bridge] DB ready frontier refill failed: {e}")

        release_limit = _blocked_release_limit(ready_target, ready_depth)
        concurrency_released_count = await release_concurrency_locked_tasks(
            tasks_store,
            redis_queue,
            release_limit=release_limit,
        )
        ready_depth += concurrency_released_count

        release_limit = _blocked_release_limit(ready_target, ready_depth)
        dependency_released_count = await release_dependency_hold_tasks(
            tasks_store,
            redis_queue,
            release_limit=release_limit,
        )
        ready_depth += dependency_released_count

        release_limit = _blocked_release_limit(ready_target, ready_depth)
        if redis_queue.pack_id == _BROWSER_LOCAL_QUEUE_SHARD:
            release_limit = max(
                release_limit,
                _BROWSER_LOCAL_RESOURCE_WAIT_RELEASE_MINIMUM,
            )
        resource_released_count = await release_resource_wait_tasks(
            tasks_store,
            redis_queue,
            release_limit=release_limit,
        )
        ready_depth += resource_released_count

        release_limit = max(0, ready_target - ready_depth)
        workspace_quota_released_count = await release_workspace_quota_tasks(
            tasks_store,
            redis_queue,
            release_limit=release_limit,
        )
        ready_depth += workspace_quota_released_count

        release_limit = max(0, ready_target - ready_depth)
        released_count = await release_admission_deferred_tasks(
            tasks_store,
            redis_queue,
            release_limit=release_limit,
        )
        ready_depth += released_count

        release_limit = max(0, ready_target - ready_depth)
        cold_released_count = await release_unblocked_cold_tasks(
            tasks_store,
            redis_queue,
            release_limit=release_limit,
        )
        ready_depth += cold_released_count

        peer_refilled_count = await refill_browser_peer_frontier(
            tasks_store,
            redis_queue,
            all_queues=all_queues,
        )
        ready_depth += peer_refilled_count

        # 3. DB Bridge Sync (Eventual Consistency Repair)
        #    Keep only a bounded ready frontier in Redis. Do not materialize
        #    the full runnable backlog into the hot queue.
        try:
            await _refill_ready_frontier_from_db(
                tasks_store,
                redis_queue,
                client=client,
                ready_depth=ready_depth,
                ready_target=ready_target,
                all_queues=all_queues,
                mark_frontier_ready=mark_frontier_ready,
                build_route_identity_projection_func=build_route_identity_projection_func,
            )
                
        except Exception as e:
            logger.error(f"[Bridge] DB Bridge sync failed: {e}")

    except Exception as e:
        if is_database_recovery_error(e):
            logger.warning(
                "Runner Redis bridge paused while PostgreSQL is recovering."
            )
            return
        logger.error(f"Failed to reap Redis queues: {e}", exc_info=True)
