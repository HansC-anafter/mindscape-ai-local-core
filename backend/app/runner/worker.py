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
import socket
import sys
from typing import Iterable, Optional
from datetime import datetime, timedelta, timezone

from backend.app.models.workspace import TaskStatus
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.runner_topology import (
    DEFAULT_LOCAL_QUEUE_PARTITION,
    RUNNER_READY_QUEUE_ORDER,
    canonical_queue_partition_for_pack,
    normalize_queue_partition,
    resolve_installed_playbook_runner_metadata,
    resolve_runner_capacity_snapshot,
    resolve_runner_profile_from_env,
    resolve_target_runner_profile,
    runner_profile_can_claim_task,
)
from backend.app.services.stores.tasks_store import TasksStore

from backend.app.services.stores.redis.runner_queue_store import RedisRunnerQueueStore

# ── Sub-module imports ──
from backend.app.runner.utils import _utc_now, _parse_utc_iso, _env_int
from backend.app.runner.concurrency import (
    _runner_id,
    _resolve_lock_key,
    _resolve_lock_keys,
    _build_inputs,
)
from backend.app.runner.lifecycle_hooks import _invoke_on_fail_hook
from backend.app.runner.resource_pressure import (
    build_runner_resource_snapshot,
    is_browser_resource_profile,
    should_defer_browser_claim,
)
from backend.app.runner.reaper import (
    _request_watchdog_abort_for_no_progress_tasks,
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
    "_invoke_on_fail_hook",
    "_request_watchdog_abort_for_no_progress_tasks",
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
    tasks_store: TasksStore, current_runner_id: str, runner_profile
) -> set[str]:
    """Reset running tasks from dead runners back to PENDING on startup.

    After a runner restart, old subprocesses are killed but their DB tasks
    may still be marked 'running' with a stale runner_id.  This function
    detects those orphans and resets them so they get cleanly re-queued.
    """
    reset_task_ids: set[str] = set()
    try:
        active_runner_ids: set[str] = {current_runner_id}
        try:
            heartbeat_max_age = _env_int(
                "LOCAL_CORE_RUNNER_ORPHAN_HEARTBEAT_MAX_AGE_SECONDS",
                120,
            )
            heartbeats = await asyncio.to_thread(
                tasks_store.list_runner_heartbeats,
                max_age_seconds=heartbeat_max_age,
                limit=500,
            )
            active_runner_ids.update(
                str(row.get("runner_id") or "").strip()
                for row in heartbeats
                if str(row.get("runner_id") or "").strip()
            )
        except Exception:
            pass

        running = await asyncio.to_thread(
            tasks_store.list_running_playbook_execution_tasks,
            workspace_id=None, limit=500,
        )
        reset_count = 0
        for t in running:
            ctx = t.execution_context if isinstance(t.execution_context, dict) else {}
            old_runner = ctx.get("runner_id")
            if (
                old_runner
                and old_runner != current_runner_id
                and old_runner not in active_runner_ids
                and runner_profile_can_claim_task(runner_profile, t)
            ):
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
                reset_task_ids.add(str(t.id))
                reset_count += 1
                logger.info(
                    f"[Startup] Reset orphaned running task {t.id} "
                    f"(old_runner={old_runner})"
                )
        if reset_count:
            logger.info(f"[Startup] Reset {reset_count} orphaned running task(s)")
    except Exception as e:
        logger.warning(f"[Startup] Failed to reset orphaned tasks: {e}", exc_info=True)
    return reset_task_ids


async def _purge_task_ids_from_transport(
    task_ids: Iterable[str],
    queue_stores: Iterable[RedisRunnerQueueStore],
) -> int:
    """Remove specific task ids from Redis queue transport lists/zsets.

    On runner restart, orphaned tasks can remain stranded in processing or delayed
    transport state from the dead runner. Startup backfill treats any transport
    membership as already queued, so these stale members must be purged before
    the tasks can be re-enqueued cleanly.
    """
    normalized_ids = [str(task_id) for task_id in task_ids if str(task_id).strip()]
    if not normalized_ids:
        return 0

    removed = 0
    try:
        for queue_store in queue_stores:
            client = await queue_store._get_client()
            if not client:
                continue
            pipe = client.pipeline()
            for task_id in normalized_ids:
                pipe.lrem(queue_store.q_pending, 0, task_id)
            pipe.zrem(queue_store.q_processing, *normalized_ids)
            pipe.zrem(queue_store.q_delayed, *normalized_ids)
            results = await pipe.execute()
            removed += sum(int(result or 0) for result in results if isinstance(result, int))
    except Exception as e:
        logger.warning(f"[Startup] Failed to purge stale transport members: {e}", exc_info=True)
        return removed

    if removed:
        logger.info(
            "[Startup] Purged %s stale Redis transport entr%s for reset task ids=%s",
            removed,
            "y" if removed == 1 else "ies",
            ",".join(normalized_ids),
        )
    return removed


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
        explicit_queue_shard = normalize_queue_partition(
            task_ctx.get("queue_partition"),
            fallback=None,
        ) or normalize_queue_partition(
            task_ctx.get("queue_shard"),
            fallback=None,
        )
        if explicit_queue_shard:
            return explicit_queue_shard
    metadata = resolve_installed_playbook_runner_metadata(pack_id)
    if metadata:
        metadata_queue_shard = normalize_queue_partition(
            metadata.get("queue_partition"),
            fallback=None,
        ) or normalize_queue_partition(
            metadata.get("queue_shard"),
            fallback=None,
        )
        if metadata_queue_shard:
            return metadata_queue_shard
    return canonical_queue_partition_for_pack(pack_id)


def _build_ready_queue_stores(
    queue_partitions: Optional[list[str] | tuple[str, ...]] = None,
) -> dict[str, RedisRunnerQueueStore]:
    queue_order = list(queue_partitions or RUNNER_READY_QUEUE_ORDER)
    return {
        shard_name: RedisRunnerQueueStore(pack_id=shard_name)
        for shard_name in queue_order
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
    current_queue_shard: Optional[str] = None,
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
        "queue_shard": (
            normalize_queue_partition(current_queue_shard, fallback=None)
            or _resolve_task_queue_shard(ctx2.get("playbook_code") or "", ctx2)
        ),
    }


# ============================================================
#  Main runner loop
# ============================================================


async def _cleanup_stale_locks(
    redis_queue: RedisRunnerQueueStore,
    current_runner_id: str,
    tasks_store: TasksStore,
) -> None:
    """Delete concurrency locks owned by runners with stale heartbeats.

    Lock owners may be either runner_id or runner_id:task_id. A live peer runner
    must keep its locks across another runner's startup.
    """
    try:
        client = await redis_queue._get_client()
        if not client:
            return

        heartbeat_max_age = _env_int(
            "LOCAL_CORE_RUNNER_ORPHAN_HEARTBEAT_MAX_AGE_SECONDS",
            120,
        )
        try:
            heartbeats = await asyncio.to_thread(
                tasks_store.list_runner_heartbeats,
                max_age_seconds=heartbeat_max_age,
                limit=500,
            )
        except Exception as e:
            logger.warning(f"[Startup] Failed to load runner heartbeats for lock cleanup: {e}")
            return

        active_runner_ids: set[str] = {current_runner_id}
        active_runner_ids.update(
            str(row.get("runner_id") or "").strip()
            for row in heartbeats
            if str(row.get("runner_id") or "").strip()
        )

        cleanup_patterns = [
            item.strip()
            for item in os.getenv(
                "LOCAL_CORE_RUNNER_LOCK_CLEANUP_PATTERNS",
                "concurrency:*",
            ).split(",")
            if item.strip()
        ]
        keys: list[str] = []
        for pattern in cleanup_patterns:
            async for key in client.scan_iter(match=pattern):
                keys.append(key)

        try:
            running_tasks = await asyncio.to_thread(
                tasks_store.list_running_playbook_execution_tasks,
                workspace_id=None,
                limit=1000,
            )
            for task in running_tasks:
                ctx = (
                    task.execution_context
                    if isinstance(task.execution_context, dict)
                    else {}
                )
                keys.extend(_resolve_lock_keys(ctx, str(task.pack_id or "")))
        except Exception as e:
            logger.warning("[Startup] Failed to derive task lock aliases: %s", e)

        cleaned = 0
        seen_keys: set[str] = set()
        for key in keys:
            if not key or key in seen_keys:
                continue
            seen_keys.add(key)
            owner = await client.get(key)
            owner_text = (
                owner.decode("utf-8", errors="ignore")
                if isinstance(owner, bytes)
                else str(owner or "")
            ).strip()
            owner_runner_id = owner_text.split(":", 1)[0].strip()
            if owner_runner_id and owner_runner_id not in active_runner_ids:
                await client.delete(key)
                cleaned += 1
                logger.info(
                    f"[Startup] Cleaned stale lock {key} (owner={owner_text}, current={current_runner_id})"
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
    await _cleanup_stale_locks(redis_queue, runner_id, tasks_store)
    _request_watchdog_abort_for_no_progress_tasks(
        tasks_store,
        watcher_id=f"runner_maintenance:{runner_id}",
    )
    for shard_name in ready_queues.keys():
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
    configured_poll_batch_limit = _env_int("LOCAL_CORE_RUNNER_POLL_BATCH_LIMIT", 0)
    runner_id = _runner_id()
    os.environ["LOCAL_CORE_RUNNER_ID"] = runner_id
    visibility_timeout_sec = _env_int("LOCAL_CORE_RUNNER_VISIBILITY_TIMEOUT_SECONDS", 180)
    runner_profile = resolve_runner_profile_from_env(default_max_inflight=max_inflight)
    max_inflight = runner_profile.max_inflight
    capacity = resolve_runner_capacity_snapshot(
        runner_profile,
        inflight=0,
        configured_poll_batch_limit=configured_poll_batch_limit,
    )

    store = MindscapeStore()
    tasks_store = TasksStore()
    if not runner_profile.enabled:
        logger.warning(
            "Runner profile %s is disabled; exiting worker without claim loop.",
            runner_profile.profile_code,
        )
        return

    ready_queues = _build_ready_queue_stores(runner_profile.accepted_queue_partitions)
    queue_cycle = [ready_queues[name] for name in runner_profile.accepted_queue_partitions]
    redis_queue = (
        queue_cycle[0]
        if queue_cycle
        else RedisRunnerQueueStore(pack_id=DEFAULT_LOCAL_QUEUE_PARTITION)
    )
    queue_cursor = 0
    ready_targets = _split_ready_target(
        _env_int("LOCAL_CORE_RUNNER_READY_TARGET", 64),
        list(ready_queues.keys()),
    )

    logger.info(
        "Local-Core runner started runner_id=%s profile=%s partitions=%s "
        "resource_classes=%s poll_interval_ms=%s max_inflight=%s poll_batch_limit=%s",
        runner_id,
        runner_profile.profile_code,
        ",".join(runner_profile.accepted_queue_partitions),
        ",".join(runner_profile.accepted_resource_classes),
        poll_interval_ms,
        max_inflight,
        capacity.poll_batch_limit,
    )

    # Ensure heartbeat table exists before entering the poll loop.
    try:
        tasks_store.ensure_runner_heartbeats_table()
    except Exception:
        pass

    # ── Startup: reset running tasks from dead runners ──
    reset_task_ids = await _reset_orphaned_running_tasks(
        tasks_store, runner_id, runner_profile
    )
    if reset_task_ids:
        await _purge_task_ids_from_transport(reset_task_ids, queue_cycle)

    # ── Startup backfill: recover pending tasks lost during restart ──
    await _backfill_pending_to_redis(tasks_store, ready_queues)

    # ── Startup lock cleanup: remove locks from dead runner instances ──
    await _cleanup_stale_locks(redis_queue, runner_id, tasks_store)

    inflight: set[asyncio.Task] = set()
    reap_interval_seconds = _env_int("LOCAL_CORE_RUNNER_REAP_INTERVAL_SECONDS", 60)
    dep_checker = DependencyChecker(cache_ttl=5.0)
    is_browser_runner = is_browser_resource_profile(runner_profile)
    next_resource_defer_log_at = 0.0

    # Kick the bridge once on startup without blocking the main heartbeat/dequeue
    # loop. The maintenance path can scan queues and DB state; if it stalls, the
    # runner should still come up and start claiming runnable work.
    asyncio.create_task(
        _run_maintenance_cycle(
            tasks_store,
            runner_id=runner_id,
            redis_queue=redis_queue,
            ready_queues=ready_queues,
            ready_targets=ready_targets,
            queue_cycle=queue_cycle,
        ),
        name="runner-startup-maintenance-kick",
    )
    logger.info("Runner startup maintenance kick scheduled")
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
        resource_snapshot = None
        try:
            resource_snapshot = build_runner_resource_snapshot(
                profile_code=runner_profile.profile_code,
                inflight=len(inflight),
                max_inflight=max_inflight,
            )
        except Exception:
            resource_snapshot = None

        # Runner liveness heartbeat via shared PostgreSQL.
        try:
            tasks_store.upsert_runner_heartbeat(
                runner_id,
                profile_code=runner_profile.profile_code,
                hostname=socket.gethostname(),
                inflight=len(inflight),
                resource_snapshot=resource_snapshot,
            )
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

        capacity = resolve_runner_capacity_snapshot(
            runner_profile,
            inflight=len(inflight),
            configured_poll_batch_limit=configured_poll_batch_limit,
        )
        if capacity.saturated:
            await asyncio.sleep(poll_interval_ms / 1000)
            continue

        if is_browser_runner:
            try:
                resource_snapshot = build_runner_resource_snapshot(
                    profile_code=runner_profile.profile_code,
                    inflight=len(inflight),
                    max_inflight=capacity.max_inflight,
                    available_slots=capacity.available_slots,
                )
            except Exception:
                resource_snapshot = None
            if should_defer_browser_claim(resource_snapshot):
                now_loop = asyncio.get_event_loop().time()
                if now_loop >= next_resource_defer_log_at:
                    admission = (
                        resource_snapshot.get("admission", {})
                        if isinstance(resource_snapshot, dict)
                        else {}
                    )
                    memory = (
                        resource_snapshot.get("memory", {})
                        if isinstance(resource_snapshot, dict)
                        else {}
                    )
                    logger.warning(
                        "Browser runner resource admission deferred "
                        "profile=%s state=%s reasons=%s memory_working_set_ratio=%s",
                        runner_profile.profile_code,
                        admission.get("state"),
                        admission.get("reasons"),
                        memory.get("working_set_ratio"),
                    )
                    next_resource_defer_log_at = now_loop + 30.0
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

            if not runner_profile_can_claim_task(runner_profile, t_data):
                logger.info(
                    "[Worker] Task %s not claimable by profile=%s target_profile=%s queue=%s. Delaying for another runner.",
                    task_id,
                    runner_profile.profile_code,
                    resolve_target_runner_profile(t_data),
                    getattr(t_data, "queue_shard", None),
                )
                await task_queue.nack_task_to_delayed(task_id, delay_sec=5)
                continue

            # ── Per-task dependency check ──
            lock_ctx = (
                t_data.execution_context
                if isinstance(t_data.execution_context, dict)
                else {}
            )
            playbook_code = lock_ctx.get("playbook_code") or t_data.pack_id or ""
            unmet = await dep_checker.check_playbook_deps(
                playbook_code,
                execution_context=lock_ctx,
            )

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
                    current_queue_shard=getattr(t_data, "queue_shard", None),
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
            lock_owner_id = f"{runner_id}:{task_id}"
            if lock_keys:
                acquired_keys: list[str] = []
                conflicting_key: Optional[str] = None
                for candidate_key in lock_keys:
                    acquired = await redis_queue.acquire_lock(
                        candidate_key, lock_owner_id, ttl_seconds=120
                    )
                    if not acquired:
                        conflicting_key = candidate_key
                        break
                    acquired_keys.append(candidate_key)

                if conflicting_key:
                    for acquired_key in reversed(acquired_keys):
                        try:
                            await redis_queue.release_lock(acquired_key, lock_owner_id)
                        except Exception:
                            pass
                    parked_update = _build_parked_task_update(
                        lock_ctx,
                        reason="concurrency_locked",
                        delay_seconds=30,
                        now=_utc_now(),
                        lock_key=lock_key,
                        conflicting_lock_key=conflicting_key,
                        current_queue_shard=getattr(t_data, "queue_shard", None),
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
                        await redis_queue.release_lock(held_key, lock_owner_id)
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
                lock_owner_id=lock_owner_id,
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
