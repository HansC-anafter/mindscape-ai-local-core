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
from datetime import datetime, timedelta, timezone

from backend.app.models.workspace import TaskStatus
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.stores.tasks_store import TasksStore

from backend.app.services.stores.redis.runner_queue_store import RedisRunnerQueueStore

# ── Sub-module imports ──
from backend.app.runner.utils import _utc_now, _parse_utc_iso, _env_int
from backend.app.runner.concurrency import (
    _runner_id,
    _resolve_lock_key,
    _resolve_lock_keys,
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

_RUNNER_READY_SHARDS = {
    "ig_analyze_pinned_reference": "ig_analysis",
    "ig_batch_pin_references": "ig_browser",
    "ig_analyze_following": "ig_browser",
}
_RUNNER_READY_QUEUE_ORDER = ("ig_analysis", "ig_browser", "default")

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


async def _reset_orphaned_running_tasks(
    tasks_store: TasksStore, current_runner_id: str
) -> None:
    """Reset running tasks from dead runners back to PENDING on startup.

    After a runner restart, old subprocesses are killed but their DB tasks
    may still be marked 'running' with a stale runner_id.  This function
    detects those orphans and resets them so they get cleanly re-queued.
    """
    try:
        running = await asyncio.to_thread(
            tasks_store.list_running_playbook_execution_tasks,
            workspace_id=None, limit=500,
        )
        reset_count = 0
        for t in running:
            ctx = t.execution_context if isinstance(t.execution_context, dict) else {}
            old_runner = ctx.get("runner_id")
            if old_runner and old_runner != current_runner_id:
                ctx2 = dict(ctx)
                ctx2.pop("runner_id", None)
                ctx2.pop("heartbeat_at", None)
                ctx2["status"] = "queued"
                ctx2["runner_reaper"] = {
                    "action": "startup_reset",
                    "previous_runner_id": old_runner,
                    "new_runner_id": current_runner_id,
                }
                tasks_store.update_task(
                    t.id,
                    execution_context=ctx2,
                    status=TaskStatus.PENDING,
                )
                reset_count += 1
                logger.info(
                    f"[Startup] Reset orphaned running task {t.id} "
                    f"(old_runner={old_runner})"
                )
        if reset_count:
            logger.info(f"[Startup] Reset {reset_count} orphaned running task(s)")
    except Exception as e:
        logger.warning(f"[Startup] Failed to reset orphaned tasks: {e}", exc_info=True)


async def _backfill_pending_to_redis(
    tasks_store: TasksStore, ready_queues: dict[str, RedisRunnerQueueStore]
) -> None:
    """Re-enqueue only a bounded runnable frontier from Postgres into shard queues."""
    try:
        backfill_limit = _env_int("LOCAL_CORE_RUNNER_STARTUP_BACKFILL_LIMIT", 64)
        shard_targets = _split_ready_target(backfill_limit, list(ready_queues.keys()))
        queued = await _collect_transport_members(list(ready_queues.values()))
        enqueued = 0
        scanned = 0

        for shard_name, redis_queue in ready_queues.items():
            shard_limit = shard_targets.get(shard_name, 0)
            if shard_limit <= 0:
                continue

            pending = await asyncio.to_thread(
                tasks_store.list_runnable_playbook_execution_tasks,
                None,
                shard_limit,
                shard_name,
            )
            if not pending:
                continue

            client = await redis_queue._get_client()
            if not client:
                logger.warning("[Backfill] Redis unavailable, skipping backfill.")
                return

            scanned += len(pending)
            for t in pending:
                tid = str(t.id)
                if tid in queued:
                    continue
                await client.lpush(redis_queue.q_pending, tid)
                queued.add(tid)
                enqueued += 1

        if not enqueued and not scanned:
            logger.info("[Backfill] No runnable pending tasks in DB — nothing to enqueue.")
            return

        logger.info(
            f"[Backfill] Enqueued {enqueued}/{scanned} runnable pending tasks into shard queues."
        )
    except Exception as e:
        logger.warning(f"[Backfill] Failed: {e}", exc_info=True)


def _resolve_task_queue_shard(
    pack_id: str, task_ctx: Optional[dict] = None
) -> str:
    if isinstance(task_ctx, dict):
        explicit_queue_shard = task_ctx.get("queue_shard")
        if isinstance(explicit_queue_shard, str) and explicit_queue_shard.strip():
            return explicit_queue_shard.strip()
    return _RUNNER_READY_SHARDS.get(pack_id, "default")


def _build_ready_queue_stores() -> dict[str, RedisRunnerQueueStore]:
    return {
        shard_name: RedisRunnerQueueStore(pack_id=shard_name)
        for shard_name in _RUNNER_READY_QUEUE_ORDER
    }


def _split_ready_target(total_target: int, shard_names: list[str]) -> dict[str, int]:
    if not shard_names:
        return {}
    if total_target <= 0:
        return {shard_name: 0 for shard_name in shard_names}

    base = total_target // len(shard_names)
    remainder = total_target % len(shard_names)
    return {
        shard_name: base + (1 if index < remainder else 0)
        for index, shard_name in enumerate(shard_names)
    }


def _normalize_task_id(raw_value: object) -> str:
    if isinstance(raw_value, bytes):
        return raw_value.decode()
    return str(raw_value)


async def _collect_transport_members(
    queue_stores: list[RedisRunnerQueueStore],
) -> set[str]:
    members: set[str] = set()
    for queue_store in queue_stores:
        client = await queue_store._get_client()
        if not client:
            continue
        pending_members = await client.lrange(queue_store.q_pending, 0, -1)
        processing_members = await client.zrange(queue_store.q_processing, 0, -1)
        delayed_members = await client.zrange(queue_store.q_delayed, 0, -1)
        members.update(_normalize_task_id(item) for item in pending_members)
        members.update(_normalize_task_id(item) for item in processing_members)
        members.update(_normalize_task_id(item) for item in delayed_members)
    return members


async def _dequeue_from_ready_queues(
    queue_cycle: list[RedisRunnerQueueStore],
    *,
    cursor: int,
    visibility_timeout_sec: int,
    block_timeout_sec: int,
) -> tuple[Optional[str], Optional[RedisRunnerQueueStore], int]:
    if not queue_cycle:
        await asyncio.sleep(block_timeout_sec)
        return None, None, cursor

    cycle_len = len(queue_cycle)

    for offset in range(cycle_len):
        queue_store = queue_cycle[(cursor + offset) % cycle_len]
        task_id = await queue_store.dequeue_task_nowait(
            visibility_timeout_sec=visibility_timeout_sec
        )
        if task_id:
            next_cursor = (cursor + offset + 1) % cycle_len
            return task_id, queue_store, next_cursor

    queue_store = queue_cycle[cursor % cycle_len]
    task_id = await queue_store.dequeue_task_blocking(
        timeout=block_timeout_sec,
        visibility_timeout_sec=visibility_timeout_sec,
    )
    next_cursor = (cursor + 1) % cycle_len
    return task_id, queue_store if task_id else None, next_cursor


def _build_parked_task_update(
    task_ctx: Optional[dict],
    *,
    reason: str,
    delay_seconds: int,
    now: Optional[datetime] = None,
    dependency_hold: Optional[dict] = None,
    lock_key: Optional[str] = None,
    conflicting_lock_key: Optional[str] = None,
) -> dict:
    base_now = now or datetime.now(timezone.utc)
    next_eligible_at = base_now + timedelta(seconds=delay_seconds)

    ctx2 = dict(task_ctx) if isinstance(task_ctx, dict) else {}
    ctx2["resume_after"] = next_eligible_at.isoformat()

    blocked_payload: dict = {}

    if reason == "dependency_hold":
        ctx2.pop("runner_skip_reason", None)
        ctx2.pop("runner_skip_lock_key", None)
        ctx2.pop("runner_skip_conflict_lock_key", None)
        if dependency_hold:
            ctx2["dependency_hold"] = dependency_hold
            blocked_payload["dependency_hold"] = dependency_hold
        else:
            ctx2.pop("dependency_hold", None)
    elif reason == "concurrency_locked":
        ctx2.pop("dependency_hold", None)
        ctx2["runner_skip_reason"] = "concurrency_locked"
        if lock_key:
            ctx2["runner_skip_lock_key"] = lock_key
            blocked_payload["lock_key"] = lock_key
        else:
            ctx2.pop("runner_skip_lock_key", None)
        if conflicting_lock_key:
            ctx2["runner_skip_conflict_lock_key"] = conflicting_lock_key
            blocked_payload["conflicting_lock_key"] = conflicting_lock_key
        else:
            ctx2.pop("runner_skip_conflict_lock_key", None)

    return {
        "execution_context": ctx2,
        "next_eligible_at": next_eligible_at,
        "blocked_reason": reason,
        "blocked_payload": blocked_payload or None,
        "frontier_state": "cold",
        "frontier_enqueued_at": None,
        "queue_shard": _resolve_task_queue_shard(
            ctx2.get("playbook_code") or "", ctx2
        ),
    }


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


async def _run_maintenance_cycle(
    tasks_store: TasksStore,
    *,
    runner_id: str,
    redis_queue: RedisRunnerQueueStore,
    ready_queues: dict[str, RedisRunnerQueueStore],
    ready_targets: dict[str, int],
    queue_cycle: list[RedisRunnerQueueStore],
) -> None:
    """Keep the ready frontier warm even when the dequeue loop is idle."""
    _reap_stale_running_tasks(tasks_store, runner_id=runner_id, redis_queue=redis_queue)
    for shard_name in _RUNNER_READY_QUEUE_ORDER:
        await _reap_redis_queues(
            tasks_store,
            ready_queues[shard_name],
            ready_target_override=ready_targets.get(shard_name, 0),
            all_queues=queue_cycle,
        )


async def _maintenance_loop(
    tasks_store: TasksStore,
    *,
    runner_id: str,
    redis_queue: RedisRunnerQueueStore,
    ready_queues: dict[str, RedisRunnerQueueStore],
    ready_targets: dict[str, int],
    queue_cycle: list[RedisRunnerQueueStore],
    reap_interval_seconds: int,
) -> None:
    while True:
        try:
            await _run_maintenance_cycle(
                tasks_store,
                runner_id=runner_id,
                redis_queue=redis_queue,
                ready_queues=ready_queues,
                ready_targets=ready_targets,
                queue_cycle=queue_cycle,
            )
        except Exception as e:
            logger.warning(f"Failed to run runner maintenance cycle: {e}")
        await asyncio.sleep(reap_interval_seconds)


async def run_forever() -> None:
    poll_interval_ms = _env_int("LOCAL_CORE_RUNNER_POLL_INTERVAL_MS", 1000)
    max_inflight = _env_int("LOCAL_CORE_RUNNER_MAX_INFLIGHT", 1)
    # Poll significantly more than inflight to prevent Head-of-Line Blocking
    # where many locked older tasks prevent newer ready tasks from being evaluated.
    batch_limit = _env_int(
        "LOCAL_CORE_RUNNER_POLL_BATCH_LIMIT", max(50, max_inflight * 10)
    )
    runner_id = _runner_id()
    visibility_timeout_sec = _env_int("LOCAL_CORE_RUNNER_VISIBILITY_TIMEOUT_SECONDS", 180)

    store = MindscapeStore()
    tasks_store = TasksStore()
    ready_queues = _build_ready_queue_stores()
    queue_cycle = [ready_queues[name] for name in _RUNNER_READY_QUEUE_ORDER]
    redis_queue = ready_queues["default"]
    queue_cursor = 0
    ready_targets = _split_ready_target(
        _env_int("LOCAL_CORE_RUNNER_READY_TARGET", 64),
        list(ready_queues.keys()),
    )

    logger.info(
        f"Local-Core runner started runner_id={runner_id} poll_interval_ms={poll_interval_ms} max_inflight={max_inflight}"
    )

    # Ensure heartbeat table exists before entering the poll loop.
    try:
        tasks_store.ensure_runner_heartbeats_table()
    except Exception:
        pass

    # ── Startup: reset running tasks from dead runners ──
    await _reset_orphaned_running_tasks(tasks_store, runner_id)

    # ── Startup backfill: recover pending tasks lost during restart ──
    await _backfill_pending_to_redis(tasks_store, ready_queues)

    # ── Startup lock cleanup: remove locks from dead runner instances ──
    await _cleanup_stale_locks(redis_queue, runner_id)

    inflight: set[asyncio.Task] = set()
    reap_interval_seconds = _env_int("LOCAL_CORE_RUNNER_REAP_INTERVAL_SECONDS", 60)
    dep_checker = DependencyChecker(cache_ttl=5.0)

    # Kick the bridge once on startup so overdue cold tasks become runnable
    # even if the dequeue loop stays otherwise idle.
    await _run_maintenance_cycle(
        tasks_store,
        runner_id=runner_id,
        redis_queue=redis_queue,
        ready_queues=ready_queues,
        ready_targets=ready_targets,
        queue_cycle=queue_cycle,
    )
    asyncio.create_task(
        _maintenance_loop(
            tasks_store,
            runner_id=runner_id,
            redis_queue=redis_queue,
            ready_queues=ready_queues,
            ready_targets=ready_targets,
            queue_cycle=queue_cycle,
            reap_interval_seconds=reap_interval_seconds,
        )
    )
    logger.info(
        "Runner maintenance loop started (interval=%ss)", reap_interval_seconds
    )

    while True:
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
        task_id, task_queue, queue_cursor = await _dequeue_from_ready_queues(
            queue_cycle,
            cursor=queue_cursor,
            visibility_timeout_sec=visibility_timeout_sec,
            block_timeout_sec=2,
        )

        if not task_id or not task_queue:
            continue

        try:
            # Rehydrate task metadata from DB (as source of truth)
            # If the task doesn't exist or is deeply corrupt, deadletter it.
            t_data = await asyncio.to_thread(tasks_store.get_task, task_id)
            if not t_data:
                logger.error(
                    f"[Worker] Task {task_id} not found in DB but was in queue. Dropping from processing."
                )
                await task_queue.ack_task(task_id)
                continue

            if t_data.status != TaskStatus.PENDING:
                logger.info(
                    f"[Worker] Task {task_id} popped but no longer PENDING (status: {t_data.status.value}). Dropping duplicate queue item."
                )
                await task_queue.ack_task(task_id)
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
                now_dt = datetime.now(timezone.utc)
                dep_hold = {
                    "deps": unmet,
                    "checked_at": now_dt.isoformat(),
                }
                parked_update = _build_parked_task_update(
                    lock_ctx,
                    reason="dependency_hold",
                    delay_seconds=30,
                    now=now_dt,
                    dependency_hold=dep_hold,
                )
                parked_update["queue_shard"] = _resolve_task_queue_shard(
                    t_data.pack_id, lock_ctx
                )
                await asyncio.to_thread(
                    tasks_store.update_task,
                    t_data.id,
                    **parked_update,
                )
                await task_queue.ack_task(task_id)
                continue

            # ── 2. Lock BEFORE Claim ──
            lock_key = _resolve_lock_key(lock_ctx, t_data.pack_id)
            lock_keys = _resolve_lock_keys(lock_ctx, t_data.pack_id)
            if lock_keys:
                acquired_keys: list[str] = []
                conflicting_key: Optional[str] = None
                for candidate_key in lock_keys:
                    acquired = await redis_queue.acquire_lock(
                        candidate_key, runner_id, ttl_seconds=120
                    )
                    if not acquired:
                        conflicting_key = candidate_key
                        break
                    acquired_keys.append(candidate_key)

                if conflicting_key:
                    for acquired_key in reversed(acquired_keys):
                        try:
                            await redis_queue.release_lock(acquired_key, runner_id)
                        except Exception:
                            pass
                    parked_update = _build_parked_task_update(
                        lock_ctx,
                        reason="concurrency_locked",
                        delay_seconds=30,
                        now=_utc_now(),
                        lock_key=lock_key,
                        conflicting_lock_key=conflicting_key,
                    )
                    parked_update["queue_shard"] = _resolve_task_queue_shard(
                        t_data.pack_id, lock_ctx
                    )
                    await asyncio.to_thread(
                        tasks_store.update_task,
                        t_data.id,
                        **parked_update,
                    )
                    await task_queue.ack_task(task_id)
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
                for held_key in lock_keys:
                    try:
                        await redis_queue.release_lock(held_key, runner_id)
                    except Exception:
                        pass
                await task_queue.ack_task(task_id)
                continue

            # ── 4. Dispatch Execution ──
            task_coro = _run_single_task(
                tasks_store,
                runner_id,
                t_data.id,
                redis_queue=task_queue,
            )
            inflight.add(asyncio.create_task(task_coro))

        except Exception as e:
            logger.warning(
                f"Runner task dispatch error for {task_id}: {e}", exc_info=True
            )
            # Failsafe in case of dispatch crash
            await (task_queue or redis_queue).nack_task_to_delayed(task_id, delay_sec=15)


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
