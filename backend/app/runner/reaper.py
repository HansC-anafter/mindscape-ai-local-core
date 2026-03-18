"""Runner reaper — cleans up stale tasks and orphaned locks."""

import logging
from datetime import timedelta
from typing import Optional

from sqlalchemy import text

from backend.app.models.workspace import TaskStatus
from backend.app.services.stores.tasks_store import TasksStore
from backend.app.services.stores.redis.runner_queue_store import RedisRunnerQueueStore

from backend.app.runner.lifecycle_hooks import _invoke_on_fail_hook
from backend.app.runner.utils import _env_int, _parse_utc_iso, _utc_now

logger = logging.getLogger(__name__)


def _reap_stale_running_tasks(tasks_store: TasksStore, runner_id: str) -> None:
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
            logger.info(
                f"Reaper checked task_id={t.id} - status={t.status} - heartbeat_at={ctx.get('heartbeat_at')} - Threshold={threshold.isoformat()}"
            )
        except Exception as e:
            logger.warning(f"Failed to reap stale task {getattr(t,'id',None)}: {e}")



async def _reap_redis_queues(tasks_store: TasksStore, redis_queue: RedisRunnerQueueStore) -> None:
    """Orchestrator background loop for Redis Queue reliability guarantees."""
    try:
        client = await redis_queue._get_client()
        if not client:
            return
            
        now_ts = redis_queue._utc_now_timestamp()
        
        # 1. Delayed Queue Mover
        delayed_items = await client.zrangebyscore(redis_queue.q_delayed, "-inf", now_ts)
        for task_id in delayed_items:
            try:
                pipe = client.pipeline()
                pipe.lpush(redis_queue.q_pending, task_id)
                pipe.zrem(redis_queue.q_delayed, task_id)
                await pipe.execute()
                logger.info(f"[Bridge] Moved task {task_id} from delayed to pending queue.")
            except Exception as e:
                logger.warning(f"Failed to move delayed task {task_id}: {e}")

        # 2. Visibility Timeout Recycler
        stale_items = await client.zrangebyscore(redis_queue.q_processing, "-inf", now_ts)
        for task_id in stale_items:
            try:
                import asyncio
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
                    started_at=None
                )
                
                pipe = client.pipeline()
                pipe.lpush(redis_queue.q_pending, task_id)
                pipe.zrem(redis_queue.q_processing, task_id)
                await pipe.execute()
                
            except Exception as e:
                logger.error(f"Failed to recycle visibility task {task_id}: {e}")

        # 3. DB Bridge Sync (Eventual Consistency Repair)
        try:
            import asyncio
            pending_tasks = await asyncio.to_thread(
                tasks_store.list_runnable_playbook_execution_tasks, limit=500
            ) # list_runnable_playbook_execution_tasks filters by PENDING status
            
            for t in pending_tasks:
                task_id = t.id
                # Check all queues (O(1) / O(N) operations via LPOS)
                in_pending = await client.lpos(redis_queue.q_pending, task_id)
                if in_pending is not None: continue
                
                if await client.zscore(redis_queue.q_processing, task_id) is not None: continue
                if await client.zscore(redis_queue.q_delayed, task_id) is not None: continue
                
                logger.warning(f"[Bridge] PENDING DB Task {task_id} missing from all Redis queues. Best-effort repair Enqueueing.")
                await redis_queue.enqueue_task(task_id)
                
        except Exception as e:
            logger.error(f"[Bridge] DB Bridge sync failed: {e}")

    except Exception as e:
        logger.error(f"Failed to reap Redis queues: {e}", exc_info=True)

