"""Stale runner task ownership recovery."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Optional

from backend.app.models.workspace import Task, TaskStatus
from backend.app.services.runner_live_state import RunnerLiveStateStore
from backend.app.services.stores.tasks_store import TasksStore
from backend.app.services.stores.redis.runner_queue_store import RedisRunnerQueueStore
from backend.app.runner.lifecycle_hooks import _invoke_on_fail_hook_sync
from backend.app.runner.reaper_context import (
    _effective_task_heartbeat_at,
    _emit_run_state_changed_for_task,
    _heartbeat_log_value,
    _is_stale_started_task,
    _task_runner_id,
    logger,
)
from backend.app.runner.reaper_transport import _force_release_lock
from backend.app.runner.utils import _env_int, _utc_now

def _requeue_stale_queued_task(
    tasks_store: TasksStore,
    task: Task,
    ctx: dict,
    *,
    runner_id: str,
    stale_seconds: int,
    reason: str,
    action: str,
    redis_queue: Optional[RedisRunnerQueueStore],
    event_loop: Optional[asyncio.AbstractEventLoop] = None,
) -> None:
    requeue_count = 0
    if isinstance(ctx.get("runner_reaper"), dict):
        requeue_count = ctx["runner_reaper"].get("requeue_count", 0)

    ctx2 = dict(ctx)
    ctx2.pop("runner_id", None)
    ctx2.pop("heartbeat_at", None)
    ctx2["status"] = "queued"
    ctx2["runner_reaper"] = {
        "runner_id": runner_id,
        "stale_seconds": stale_seconds,
        "action": action,
        "reason": reason,
        "requeue_count": requeue_count + 1,
        "requeued_at": _utc_now().isoformat(),
    }
    now = _utc_now()
    tasks_store.update_task(
        task.id,
        execution_context=ctx2,
        status=TaskStatus.PENDING,
        started_at=None,
        next_eligible_at=now,
        blocked_reason=None,
        blocked_payload=None,
        runner_id=None,
        heartbeat_at=None,
        frontier_state="ready",
        frontier_enqueued_at=now,
        error=None,
    )
    _force_release_lock(
        ctx,
        task.pack_id,
        redis_queue,
        persisted_concurrency_key=getattr(task, "concurrency_key", None),
        event_loop=event_loop,
    )

def _reap_stale_running_tasks(
    tasks_store: TasksStore,
    runner_id: str,
    redis_queue: Optional[RedisRunnerQueueStore] = None,
    event_loop: Optional[asyncio.AbstractEventLoop] = None,
    live_state_store: Optional[RunnerLiveStateStore] = None,
) -> None:
    stale_seconds = _env_int("LOCAL_CORE_RUNNER_STALE_TASK_SECONDS", 180)
    threshold = _utc_now() - timedelta(seconds=stale_seconds)

    try:
        running = tasks_store.list_running_playbook_execution_tasks(
            workspace_id=None, limit=500
        )
        list_frontier_running_pending_tasks = getattr(
            tasks_store,
            "list_frontier_running_pending_tasks",
            None,
        )
        if callable(list_frontier_running_pending_tasks):
            running.extend(
                list_frontier_running_pending_tasks(workspace_id=None, limit=500)
            )
    except Exception as e:
        logger.warning(f"Runner stale-task scan failed: {e}")
        return

    seen_task_ids: set[str] = set()
    for t in running:
        if t.id in seen_task_ids:
            continue
        seen_task_ids.add(t.id)
        try:
            ctx = t.execution_context if isinstance(t.execution_context, dict) else {}
            ctx_runner_id = _task_runner_id(t, ctx)
            heartbeat_at = _effective_task_heartbeat_at(t, ctx, live_state_store)

            # Only reap tasks that were executed in runner mode (or clearly runner-owned).
            if ctx.get("execution_mode") not in (None, "runner"):
                continue

            if not ctx_runner_id:
                if (
                    t.status == TaskStatus.PENDING
                    and ctx.get("status") == "queued"
                    and _is_stale_started_task(t, threshold)
                ):
                    msg = (
                        "Runner ownership missing for stale queued task "
                        f"(started_at={getattr(t, 'started_at', None)})"
                    )
                    _requeue_stale_queued_task(
                        tasks_store,
                        t,
                        ctx,
                        runner_id=runner_id,
                        stale_seconds=stale_seconds,
                        reason=msg,
                        action="requeue_orphan_no_runner",
                        redis_queue=redis_queue,
                        event_loop=event_loop,
                    )
                    logger.warning(
                        f"Re-queued stale runner task without owner task_id={t.id} ({msg})"
                    )
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

            heartbeat_log = _heartbeat_log_value(heartbeat_at, ctx)
            msg = f"Runner heartbeat stale (previous_runner_id={ctx_runner_id}, heartbeat_at={heartbeat_log})"
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
                        runner_id=None,
                        heartbeat_at=None,
                    )
                    _emit_run_state_changed_for_task(
                        t,
                        previous_state="RUNNING",
                        new_state="FAILED",
                        reason=ctx2["error"],
                    )
                    logger.warning(
                        f"Failed task after {requeue_count} re-queues task_id={t.id} ({msg})"
                    )
                else:
                    _requeue_stale_queued_task(
                        tasks_store,
                        t,
                        ctx,
                        runner_id=runner_id,
                        stale_seconds=stale_seconds,
                        reason=msg,
                        action="requeue",
                        redis_queue=redis_queue,
                        event_loop=event_loop,
                    )
                    logger.warning(
                        f"Re-queued stale runner task task_id={t.id} (attempt {requeue_count + 1}/3) ({msg})"
                    )
            else:
                # If the task is running but heartbeat is stale, mark failed.
                # Try on_fail lifecycle hook first (declared in playbook spec).
                hook_handled = False
                try:
                    hook_handled = _invoke_on_fail_hook_sync(ctx2, msg, t.id)
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
                        runner_id=None,
                        heartbeat_at=None,
                    )
                    _emit_run_state_changed_for_task(
                        t,
                        previous_state="RUNNING",
                        new_state="FAILED",
                        reason=msg,
                    )
                    logger.warning(f"Reaped stale running task task_id={t.id} ({msg})")
                    _force_release_lock(
                        ctx,
                        t.pack_id,
                        redis_queue,
                        persisted_concurrency_key=getattr(t, "concurrency_key", None),
                        event_loop=event_loop,
                    )
            logger.info(
                f"Reaper checked task_id={t.id} - status={t.status} - heartbeat_at={heartbeat_log} - Threshold={threshold.isoformat()}"
            )
        except Exception as e:
            logger.warning(f"Failed to reap stale task {getattr(t,'id',None)}: {e}")
