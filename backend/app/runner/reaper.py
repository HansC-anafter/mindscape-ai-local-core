"""Runner reaper — cleans up stale tasks and orphaned locks."""

import asyncio
import logging
from datetime import timedelta
from typing import Optional

from sqlalchemy import text

from backend.app.models.workspace import TaskStatus
from backend.app.services.stores.tasks_store import TasksStore
from backend.app.services.stores.redis.runner_queue_store import RedisRunnerQueueStore
from backend.app.services.task_admission_service import (
    ADMISSION_DEFERRED_REASON,
    TASK_ADMISSION_SERVICE,
)

from backend.app.runner.concurrency import _resolve_lock_keys
from backend.app.runner.lifecycle_hooks import _invoke_on_fail_hook
from backend.app.runner.utils import _env_int, _parse_utc_iso, _utc_now

logger = logging.getLogger(__name__)


def _normalize_task_id(raw_value: object) -> str:
    if isinstance(raw_value, bytes):
        return raw_value.decode()
    return str(raw_value)


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
            )
        except Exception as e:
            logger.warning(
                f"[Bridge] Failed to mirror ready frontier state for task {task_id}: {e}"
            )


def _force_release_lock(
    task_ctx: dict,
    pack_id: str,
    redis_queue: Optional[RedisRunnerQueueStore],
) -> None:
    """Force-delete the concurrency lock for a reaped task.

    The owning runner is dead, so we can't use compare-and-delete.
    We just DEL the key directly.
    Called from sync code inside an async event loop.
    """
    if not redis_queue:
        return
    lock_keys = _resolve_lock_keys(task_ctx, pack_id)
    if not lock_keys:
        return
    try:
        loop = asyncio.get_event_loop()
        for lock_key in lock_keys:
            loop.create_task(_async_force_release(redis_queue, lock_key))
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


def _reap_stale_running_tasks(
    tasks_store: TasksStore,
    runner_id: str,
    redis_queue: Optional[RedisRunnerQueueStore] = None,
) -> None:
    stale_seconds = _env_int("LOCAL_CORE_RUNNER_STALE_TASK_SECONDS", 180)
    threshold = _utc_now() - timedelta(seconds=stale_seconds)

    try:
        running = tasks_store.list_running_playbook_execution_tasks(
            workspace_id=None, limit=500
        )
    except Exception as e:
        logger.warning(f"Runner stale-task scan failed: {e}")
        return

    for t in running:
        try:
            ctx = t.execution_context if isinstance(t.execution_context, dict) else {}
            ctx_runner_id = ctx.get("runner_id")
            heartbeat_at = _parse_utc_iso(ctx.get("heartbeat_at"))

            if not ctx_runner_id:
                continue

            # Only reap tasks that were executed in runner mode (or clearly runner-owned).
            if ctx.get("execution_mode") not in (None, "runner"):
                continue

            if heartbeat_at and heartbeat_at > threshold:
                # Even if heartbeat is fresh, if runner_id doesn't match
                # current runner, this task may be orphaned.  Give it a
                # grace period (half stale window) to avoid killing tasks
                # during rolling restarts.
                if ctx_runner_id == runner_id:
                    continue
                grace_threshold = _utc_now() - timedelta(seconds=stale_seconds // 2)
                if heartbeat_at > grace_threshold:
                    continue

            msg = f"Runner heartbeat stale (previous_runner_id={ctx_runner_id}, heartbeat_at={ctx.get('heartbeat_at')})"
            ctx2 = dict(ctx)
            ctx2["runner_reaper"] = {
                "runner_id": runner_id,
                "stale_seconds": stale_seconds,
                "action": None,
                "reason": msg,
            }

            # If the task is still queued, re-queue it so a healthy runner can claim it.
            # IMPORTANT:
            # - Do NOT use sandbox_id/current_step_index as "started" heuristics; some runner tasks
            #   execute in-process and may never set sandbox_id even after making real progress.
            if ctx2.get("status") == "queued":
                # Track re-queue count to prevent infinite crash loops
                requeue_count = 0
                if isinstance(ctx.get("runner_reaper"), dict):
                    requeue_count = ctx["runner_reaper"].get("requeue_count", 0)

                if requeue_count >= 3:
                    # Too many re-queues — fail permanently
                    ctx2["status"] = "failed"
                    ctx2["error"] = f"Exceeded max re-queue attempts ({requeue_count})"
                    ctx2["runner_reaper"]["action"] = "fail_max_requeue"
                    ctx2["runner_reaper"]["requeue_count"] = requeue_count
                    tasks_store.update_task(
                        t.id,
                        execution_context=ctx2,
                        status=TaskStatus.FAILED,
                        completed_at=_utc_now(),
                        error=ctx2["error"],
                    )
                    logger.warning(
                        f"Failed task after {requeue_count} re-queues task_id={t.id} ({msg})"
                    )
                else:
                    ctx2.pop("runner_id", None)
                    ctx2.pop("heartbeat_at", None)
                    ctx2["status"] = "queued"
                    ctx2["runner_reaper"]["action"] = "requeue"
                    ctx2["runner_reaper"]["requeue_count"] = requeue_count + 1
                    ctx2["runner_reaper"]["requeued_at"] = _utc_now().isoformat()
                    tasks_store.update_task(
                        t.id,
                        execution_context=ctx2,
                        status=TaskStatus.PENDING,
                        error=None,
                    )
                    _force_release_lock(ctx, t.pack_id, redis_queue)
                    logger.warning(
                        f"Re-queued stale runner task task_id={t.id} (attempt {requeue_count + 1}/3) ({msg})"
                    )
            else:
                # If the task is running but heartbeat is stale, mark failed.
                # Try on_fail lifecycle hook first (declared in playbook spec).
                hook_handled = False
                try:
                    hook_handled = _invoke_on_fail_hook(ctx2, msg, t.id)
                except Exception as hook_err:
                    logger.warning(f"Reaper on_fail hook error for {t.id}: {hook_err}")

                if hook_handled:
                    ctx2["runner_reaper"]["action"] = "lifecycle_hook_on_fail"
                    logger.warning(
                        f"Reaped + on_fail hook invoked for stale task task_id={t.id} ({msg})"
                    )

                # ALWAYS ensure task reaches terminal state, regardless of hook result.
                # Re-read to check if hook already marked it FAILED.
                refreshed = tasks_store.get_task(t.id)
                if refreshed and refreshed.status not in (
                    TaskStatus.FAILED,
                    TaskStatus.CANCELLED_BY_USER,
                    TaskStatus.SUCCEEDED,
                    TaskStatus.EXPIRED,
                ):
                    ctx2["status"] = "failed"
                    ctx2["error"] = msg
                    ctx2["failed_at"] = _utc_now().isoformat()
                    if not hook_handled:
                        ctx2["runner_reaper"]["action"] = "fail"
                    tasks_store.update_task(
                        t.id,
                        execution_context=ctx2,
                        status=TaskStatus.FAILED,
                        completed_at=_utc_now(),
                        error=msg,
                    )
                    logger.warning(f"Reaped stale running task task_id={t.id} ({msg})")
                    _force_release_lock(ctx, t.pack_id, redis_queue)
            logger.info(
                f"Reaper checked task_id={t.id} - status={t.status} - heartbeat_at={ctx.get('heartbeat_at')} - Threshold={threshold.isoformat()}"
            )
        except Exception as e:
            logger.warning(f"Failed to reap stale task {getattr(t,'id',None)}: {e}")



async def _reap_redis_queues(
    tasks_store: TasksStore,
    redis_queue: RedisRunnerQueueStore,
    *,
    ready_target_override: Optional[int] = None,
    all_queues: Optional[list[RedisRunnerQueueStore]] = None,
) -> None:
    """Orchestrator background loop for Redis Queue reliability guarantees."""
    try:
        client = await redis_queue._get_client()
        if not client:
            return
            
        now_ts = redis_queue._utc_now_timestamp()
        ready_target = ready_target_override or _env_int("LOCAL_CORE_RUNNER_READY_TARGET", 64)
        delayed_move_limit = _env_int("LOCAL_CORE_RUNNER_DELAYED_MOVE_LIMIT", 100)
        
        # 1. Delayed Queue Mover — move in small pipeline batches to avoid
        #    blocking Redis single-threaded processing (SLOWLOG showed 17ms for 688-item pipeline).
        _PIPELINE_BATCH = 100
        delayed_items = await client.zrangebyscore(
            redis_queue.q_delayed, "-inf", now_ts, start=0, num=delayed_move_limit
        )
        if delayed_items:
            try:
                moved = 0
                for i in range(0, len(delayed_items), _PIPELINE_BATCH):
                    batch = delayed_items[i:i + _PIPELINE_BATCH]
                    pipe = client.pipeline()
                    for task_id in batch:
                        pipe.lpush(redis_queue.q_pending, task_id)
                        pipe.zrem(redis_queue.q_delayed, task_id)
                    await pipe.execute()
                    moved += len(batch)
                    # Yield so Redis can serve other clients between batches
                    if i + _PIPELINE_BATCH < len(delayed_items):
                        await asyncio.sleep(0)
                await _mark_frontier_ready(
                    tasks_store,
                    [str(task_id) for task_id in delayed_items],
                    queue_shard=redis_queue.pack_id,
                )
                logger.info(f"[Bridge] Moved {moved} tasks from delayed to pending queue.")
            except Exception as e:
                logger.warning(f"Failed to batch move delayed tasks: {e}")

        # 2. Visibility Timeout Recycler
        stale_items = await client.zrangebyscore(redis_queue.q_processing, "-inf", now_ts)
        for task_id in stale_items:
            try:
                t_data = await asyncio.to_thread(tasks_store.get_task, task_id)
                if not t_data:
                    await redis_queue.ack_task(task_id)
                    continue
                
                # Check actual DB Truth
                if t_data.status not in (TaskStatus.PENDING, TaskStatus.RUNNING):
                    await redis_queue.ack_task(task_id)
                    continue
                
                ctx = t_data.execution_context if isinstance(t_data.execution_context, dict) else {}
                ctx_heartbeat = _parse_utc_iso(ctx.get('heartbeat_at'))
                stale_limit = _utc_now() - timedelta(seconds=_env_int("LOCAL_CORE_RUNNER_STALE_TASK_SECONDS", 180))
                
                if ctx_heartbeat and ctx_heartbeat > stale_limit:
                    # DB heartbeat is fresh, touching visibility and skipping
                    await redis_queue.touch_visibility_timeout(task_id, 180)
                    continue
                
                # Genuinely abandoned
                logger.warning(f"[Bridge] Task {task_id} visibility timeout expired. Reverting to queue.")
                ctx2 = dict(ctx)
                ctx2.pop('runner_id', None)
                ctx2.pop('heartbeat_at', None)
                ctx2["status"] = "queued"
                await asyncio.to_thread(
                    tasks_store.update_task, 
                    task_id, 
                    execution_context=ctx2, 
                    status=TaskStatus.PENDING, 
                    started_at=None,
                    next_eligible_at=_utc_now(),
                    blocked_reason=None,
                    blocked_payload=None,
                    frontier_state="ready",
                    frontier_enqueued_at=_utc_now(),
                )
                
                pipe = client.pipeline()
                pipe.lpush(redis_queue.q_pending, task_id)
                pipe.zrem(redis_queue.q_processing, task_id)
                await pipe.execute()
                
            except Exception as e:
                logger.error(f"Failed to recycle visibility task {task_id}: {e}")

        ready_depth = await client.llen(redis_queue.q_pending)
        release_limit = max(0, ready_target - ready_depth)
        released_count = await _release_admission_deferred_tasks(
            tasks_store,
            redis_queue,
            release_limit=release_limit,
        )
        ready_depth += released_count

        # 3. DB Bridge Sync (Eventual Consistency Repair)
        #    Keep only a bounded ready frontier in Redis. Do not materialize
        #    the full runnable backlog into the hot queue.
        try:
            refill_limit = max(0, ready_target - ready_depth)
            if refill_limit <= 0:
                return

            queue_family = all_queues or [redis_queue]
            all_queued = set()
            for queue_store in queue_family:
                queue_client = client if queue_store is redis_queue else await queue_store._get_client()
                if not queue_client:
                    continue
                pending_members = await queue_client.lrange(queue_store.q_pending, 0, -1)
                processing_members = await queue_client.zrange(
                    queue_store.q_processing, 0, -1
                )
                delayed_members = await queue_client.zrange(
                    queue_store.q_delayed, 0, -1
                )
                all_queued.update(_normalize_task_id(task_id) for task_id in pending_members)
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
            for t in pending_tasks:
                if t.id not in all_queued:
                    missing_tasks.append(t.id)
                if len(missing_tasks) >= refill_limit:
                    break

            if missing_tasks:
                for i in range(0, len(missing_tasks), _PIPELINE_BATCH):
                    batch = missing_tasks[i:i + _PIPELINE_BATCH]
                    pipe = client.pipeline()
                    for task_id in batch:
                        pipe.lpush(redis_queue.q_pending, task_id)
                    await pipe.execute()
                    if i + _PIPELINE_BATCH < len(missing_tasks):
                        await asyncio.sleep(0)
                await _mark_frontier_ready(
                    tasks_store,
                    [str(task_id) for task_id in missing_tasks],
                    queue_shard=redis_queue.pack_id,
                )
                logger.warning(
                    f"[Bridge] Refilled ready frontier with {len(missing_tasks)} task(s) (ready_depth={ready_depth}, ready_target={ready_target})."
                )
                
        except Exception as e:
            logger.error(f"[Bridge] DB Bridge sync failed: {e}")

    except Exception as e:
        logger.error(f"Failed to reap Redis queues: {e}", exc_info=True)


async def _release_admission_deferred_tasks(
    tasks_store: TasksStore,
    redis_queue: RedisRunnerQueueStore,
    *,
    release_limit: int,
) -> int:
    if release_limit <= 0:
        return 0

    due_tasks = await asyncio.to_thread(
        tasks_store.list_due_admission_deferred_tasks,
        queue_shard=redis_queue.pack_id,
        limit=max(release_limit * 4, release_limit),
    )
    if not due_tasks:
        return 0

    client = await redis_queue._get_client()
    if not client:
        return 0

    now = _utc_now()
    released_task_ids: list[str] = []

    for task in due_tasks:
        if len(released_task_ids) >= release_limit:
            break

        try:
            decision = await asyncio.to_thread(
                TASK_ADMISSION_SERVICE.evaluate_on_release,
                tasks_store,
                task,
            )
            if decision.allow:
                await asyncio.to_thread(
                    tasks_store.update_task,
                    task.id,
                    execution_context=decision.execution_context,
                    next_eligible_at=now,
                    blocked_reason=None,
                    blocked_payload=None,
                    queue_shard=decision.queue_shard or redis_queue.pack_id,
                    frontier_state="ready",
                    frontier_enqueued_at=now,
                )
                released_task_ids.append(task.id)
                continue

            await asyncio.to_thread(
                tasks_store.update_task,
                task.id,
                execution_context=decision.execution_context,
                next_eligible_at=decision.next_eligible_at,
                blocked_reason=ADMISSION_DEFERRED_REASON,
                blocked_payload=decision.blocked_payload,
                queue_shard=decision.queue_shard or redis_queue.pack_id,
                frontier_state="cold",
                frontier_enqueued_at=None,
            )
        except Exception as exc:
            logger.warning(
                "[Admission] Failed to evaluate deferred task %s on shard %s: %s",
                getattr(task, "id", None),
                redis_queue.pack_id,
                exc,
            )

    if not released_task_ids:
        return 0

    try:
        pipe = client.pipeline()
        for task_id in released_task_ids:
            pipe.lpush(redis_queue.q_pending, task_id)
        await pipe.execute()
    except Exception as exc:
        logger.warning(
            "[Admission] Failed to enqueue %d released task(s) for shard %s: %s",
            len(released_task_ids),
            redis_queue.pack_id,
            exc,
        )

    return len(released_task_ids)
