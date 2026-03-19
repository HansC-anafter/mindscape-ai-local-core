"""Runner worker — main loop coordinator.

This file was refactored from a 1150-line monolith into a slim coordinator
that delegates to focused sub-modules:

  utils.py          — _utc_now, _parse_utc_iso, _env_int
  concurrency.py    — _runner_id, _resolve_lock_key, _build_inputs
  lifecycle_hooks.py — _invoke_on_fail_hook
  reaper.py         — _reap_stale_running_tasks, _reap_redis_queues
  task_executor.py  — _child_execute_playbook, _run_single_task
  restart.py        — _check_restart_sentinel
"""

import asyncio
import logging
import os
import sys
from typing import Optional
from datetime import datetime

from backend.app.models.workspace import TaskStatus
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.stores.tasks_store import TasksStore

from backend.app.services.stores.redis.runner_queue_store import RedisRunnerQueueStore

# ── Sub-module imports ──
from backend.app.runner.utils import _utc_now, _parse_utc_iso, _env_int
from backend.app.runner.concurrency import (
    _runner_id,
    _resolve_lock_key,
    _build_inputs,
    _is_ig_playbook,
)
from backend.app.runner.lifecycle_hooks import _invoke_on_fail_hook
from backend.app.runner.reaper import (
    _reap_stale_running_tasks,
    _reap_redis_queues,
)
from backend.app.runner.task_executor import (
    _child_execute_playbook,
    _initialize_capability_packages_for_runner,
    _run_single_task,
)
from backend.app.runner.restart import (
    _check_restart_sentinel,
    _RESTART_SENTINEL_PATH,
    _RESTART_DRAIN_TIMEOUT_SECONDS,
)
from backend.app.runner.dependency_check import DependencyChecker

logger = logging.getLogger(__name__)

# Re-export all public symbols so existing imports (e.g. tests) keep working.
__all__ = [
    "_utc_now",
    "_parse_utc_iso",
    "_env_int",
    "_runner_id",
    "_resolve_lock_key",
    "_build_inputs",
    "_is_ig_playbook",
    "_invoke_on_fail_hook",
    "_reap_stale_running_tasks",
    "_reap_redis_queues",
    "_child_execute_playbook",
    "_initialize_capability_packages_for_runner",
    "_run_single_task",
    "_check_restart_sentinel",
    "_RESTART_SENTINEL_PATH",
    "_RESTART_DRAIN_TIMEOUT_SECONDS",
    "run_forever",
    "main",
]


# ============================================================
#  Startup backfill — Redis has no persistence, so after a
#  reboot / container restart every pending task vanishes from
#  the queue.  This one-shot function reads Postgres and re-
#  enqueues anything that is still PENDING.
# ============================================================


async def _backfill_pending_to_redis(
    tasks_store: TasksStore, redis_queue: RedisRunnerQueueStore
) -> None:
    """Re-enqueue all Postgres PENDING tasks into Redis (idempotent)."""
    try:
        pending = await asyncio.to_thread(
            tasks_store.list_tasks_by_workspace,
            workspace_id=None, status=TaskStatus.PENDING, limit=5000
        )
        if not pending:
            logger.info("[Backfill] No pending tasks in DB — nothing to enqueue.")
            return

        client = await redis_queue._get_client()
        if not client:
            logger.warning("[Backfill] Redis unavailable, skipping backfill.")
            return

        enqueued = 0
        for t in pending:
            tid = str(t.id)
            # Only enqueue if not already present in pending, processing, or delayed
            in_processing = await client.zscore(redis_queue.q_processing, tid)
            in_delayed = await client.zscore(redis_queue.q_delayed, tid)
            if in_processing is not None or in_delayed is not None:
                continue
            await client.lpush(redis_queue.q_pending, tid)
            enqueued += 1

        logger.info(
            f"[Backfill] Enqueued {enqueued}/{len(pending)} pending tasks into Redis."
        )
    except Exception as e:
        logger.warning(f"[Backfill] Failed: {e}", exc_info=True)


# ============================================================
#  Main runner loop
# ============================================================


async def _cleanup_stale_locks(
    redis_queue: RedisRunnerQueueStore, current_runner_id: str
) -> None:
    """Delete any concurrency locks not owned by the current runner.

    On restart, the previous runner's locks are stale (it's dead).
    We force-delete them so tasks aren't permanently blocked.
    """
    try:
        client = await redis_queue._get_client()
        if not client:
            return

        # Scan for all lock keys
        cleaned = 0
        for pattern in ["concurrency:*", "ig_profile:*"]:
            keys = []
            async for key in client.scan_iter(match=pattern):
                keys.append(key)
            for key in keys:
                owner = await client.get(key)
                if owner and owner != current_runner_id:
                    await client.delete(key)
                    cleaned += 1
                    logger.info(
                        f"[Startup] Cleaned stale lock {key} (owner={owner}, current={current_runner_id})"
                    )
        if cleaned:
            logger.info(f"[Startup] Cleaned {cleaned} stale lock(s)")
    except Exception as e:
        logger.warning(f"[Startup] Failed to cleanup stale locks: {e}")


async def run_forever() -> None:
    poll_interval_ms = _env_int("LOCAL_CORE_RUNNER_POLL_INTERVAL_MS", 1000)
    max_inflight = _env_int("LOCAL_CORE_RUNNER_MAX_INFLIGHT", 1)
    # Poll significantly more than inflight to prevent Head-of-Line Blocking
    # where many locked older tasks prevent newer ready tasks from being evaluated.
    batch_limit = _env_int(
        "LOCAL_CORE_RUNNER_POLL_BATCH_LIMIT", max(50, max_inflight * 10)
    )
    runner_id = _runner_id()

    store = MindscapeStore()
    tasks_store = TasksStore()
    redis_queue = RedisRunnerQueueStore()

    logger.info(
        f"Local-Core runner started runner_id={runner_id} poll_interval_ms={poll_interval_ms} max_inflight={max_inflight}"
    )

    # Ensure heartbeat table exists before entering the poll loop.
    try:
        tasks_store.ensure_runner_heartbeats_table()
    except Exception:
        pass

    # ── Startup backfill: recover pending tasks lost during restart ──
    await _backfill_pending_to_redis(tasks_store, redis_queue)

    # ── Startup lock cleanup: remove locks from dead runner instances ──
    await _cleanup_stale_locks(redis_queue, runner_id)

    inflight: set[asyncio.Task] = set()
    last_reap_at: Optional[datetime] = None
    reap_interval_seconds = _env_int("LOCAL_CORE_RUNNER_REAP_INTERVAL_SECONDS", 60)
    dep_checker = DependencyChecker(cache_ttl=5.0)

    while True:
        # Periodic reaping for runner restarts / orphaned tasks.
        try:
            now = _utc_now()
            if (last_reap_at is None) or (
                (now - last_reap_at).total_seconds() >= reap_interval_seconds
            ):
                _reap_stale_running_tasks(tasks_store, runner_id=runner_id, redis_queue=redis_queue)
                await _reap_redis_queues(tasks_store, redis_queue)
                last_reap_at = now
        except Exception as e:
            logger.warning(f"Failed to reap: {e}")

        # Runner liveness heartbeat via shared PostgreSQL.
        try:
            tasks_store.upsert_runner_heartbeat(runner_id)
        except Exception:
            pass

        # Restart sentinel: backend writes this when Device Node is unreachable.
        # Drain inflight tasks gracefully, then exit for Docker auto-restart.
        if _check_restart_sentinel():
            if inflight:
                logger.info(
                    "Restart sentinel: waiting for %d inflight tasks to drain "
                    "(max %ds)",
                    len(inflight),
                    _RESTART_DRAIN_TIMEOUT_SECONDS,
                )
                drain_deadline = (
                    asyncio.get_event_loop().time() + _RESTART_DRAIN_TIMEOUT_SECONDS
                )
                while inflight and asyncio.get_event_loop().time() < drain_deadline:
                    done = {t for t in inflight if t.done()}
                    for t in done:
                        inflight.discard(t)
                        try:
                            _ = t.result()
                        except Exception:
                            pass
                    if inflight:
                        await asyncio.sleep(1.0)
                if inflight:
                    logger.warning(
                        "Restart sentinel: %d tasks still inflight after drain timeout, "
                        "forcing exit",
                        len(inflight),
                    )
            logger.info("Runner exiting for restart (sentinel)")
            sys.exit(1)

        # Cleanup finished tasks
        try:
            done = {t for t in inflight if t.done()}
            for t in done:
                inflight.discard(t)
                try:
                    _ = t.result()
                except Exception:
                    pass
        except Exception:
            pass

        if len(inflight) >= max_inflight:
            await asyncio.sleep(poll_interval_ms / 1000)
            continue

        # ── 1. Redis Queue Dequeue ──
        # Blocking Pop from pending to processing (ZSET). This wait completely replaces DB polling.
        task_id = await redis_queue.dequeue_task_blocking(
            timeout=2, visibility_timeout_sec=180
        )

        if not task_id:
            continue

        from datetime import datetime, timedelta, timezone

        try:
            # Rehydrate task metadata from DB (as source of truth)
            # If the task doesn't exist or is deeply corrupt, deadletter it.
            t_data = await asyncio.to_thread(tasks_store.get_task, task_id)
            if not t_data:
                logger.error(
                    f"[Worker] Task {task_id} not found in DB but was in queue. Dropping from processing."
                )
                await redis_queue.ack_task(task_id)
                continue

            if t_data.status != TaskStatus.PENDING:
                logger.info(
                    f"[Worker] Task {task_id} popped but no longer PENDING (status: {t_data.status.value}). Dropping duplicate queue item."
                )
                await redis_queue.ack_task(task_id)
                continue

            # ── Per-task dependency check ──
            lock_ctx = (
                t_data.execution_context
                if isinstance(t_data.execution_context, dict)
                else {}
            )
            playbook_code = lock_ctx.get("playbook_code") or t_data.pack_id or ""
            unmet = await dep_checker.check_playbook_deps(playbook_code)

            if unmet:
                # Dependency unmet. Put back to delayed queue for 30 seconds.
                now_dt = datetime.now(timezone.utc)

                existing_hold = lock_ctx.get("dependency_hold")
                if not existing_hold or existing_hold.get("deps") != unmet:
                    ctx2 = dict(lock_ctx)
                    ctx2["dependency_hold"] = {
                        "deps": unmet,
                        "checked_at": now_dt.isoformat(),
                    }
                    await asyncio.to_thread(
                        tasks_store.update_task, t_data.id, execution_context=ctx2
                    )

                await redis_queue.nack_task_to_delayed(task_id, delay_sec=30)
                continue

            # ── 2. Lock BEFORE Claim ──
            lock_key = _resolve_lock_key(lock_ctx, t_data.pack_id)
            if lock_key:
                # Try acquire Lock exclusively on Redis
                acquired = await redis_queue.acquire_lock(
                    lock_key, runner_id, ttl_seconds=120
                )
                if not acquired:
                    # Concurrency locked -> Backoff defer directly into delayed queue
                    if (
                        lock_ctx.get("runner_skip_reason") != "concurrency_locked"
                        or lock_ctx.get("runner_skip_lock_key") != lock_key
                    ):
                        ctx2 = dict(lock_ctx)
                        ctx2["runner_skip_reason"] = "concurrency_locked"
                        ctx2["runner_skip_lock_key"] = lock_key
                        await asyncio.to_thread(
                            tasks_store.update_task, t_data.id, execution_context=ctx2
                        )
                    else:
                        # Still locked — refresh resume_after so UI shows fresh "last evaluated"
                        # resume_after lives inside execution_context JSON, NOT as a DB column.
                        ctx2 = dict(lock_ctx)
                        ctx2["resume_after"] = _utc_now().isoformat()
                        await asyncio.to_thread(
                            tasks_store.update_task, t_data.id,
                            execution_context=ctx2,
                        )

                    await redis_queue.nack_task_to_delayed(task_id, delay_sec=30)
                    continue

            # ── 3. Atomic DB Claim ──
            # Only status PENDING -> RUNNING. If rows_updated=0, it's a stolen pop or duplicate claim.
            claimed = await asyncio.to_thread(
                tasks_store.try_claim_task, t_data.id, runner_id=runner_id
            )
            if not claimed:
                logger.warning(
                    f"[Worker] DB claim failed for Task {task_id}. Ghost pop or duplicated. Acking."
                )
                if lock_key:
                    await redis_queue.release_lock(lock_key, runner_id)
                await redis_queue.ack_task(task_id)
                continue

            # ── 4. Dispatch Execution ──
            task_coro = _run_single_task(tasks_store, runner_id, t_data.id, redis_queue=redis_queue)
            inflight.add(asyncio.create_task(task_coro))

        except Exception as e:
            logger.warning(
                f"Runner task dispatch error for {task_id}: {e}", exc_info=True
            )
            # Failsafe in case of dispatch crash
            await redis_queue.nack_task_to_delayed(task_id, delay_sec=15)


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    _initialize_capability_packages_for_runner()
    try:
        store = MindscapeStore()
        tasks_store = TasksStore()
        rid = _runner_id()
        _reap_stale_running_tasks(tasks_store, runner_id=rid, redis_queue=RedisRunnerQueueStore())

    except Exception:
        pass
    asyncio.run(run_forever())


if __name__ == "__main__":
    main()
