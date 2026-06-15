"""Runner worker maintenance cycle helpers."""

import asyncio
import logging
import os
import sys

from backend.app.services.stores.redis.runner_queue_store import RedisRunnerQueueStore
from backend.app.services.stores.tasks_store import TasksStore
from backend.app.services.host_resources.queue_utilization import (
    write_queue_utilization_snapshot_if_leader,
)
from backend.app.runner.concurrency import _resolve_lock_keys
from backend.app.runner.database_backoff import RunnerDatabaseRecoveryBackoff
from backend.app.runner.db_pool_pressure import check_db_pool_pressure
from backend.app.runner.reaper import (
    _request_watchdog_abort_for_no_progress_tasks,
    _reap_stale_running_tasks,
    _reap_redis_queues,
)
from backend.app.runner.utils import _env_int
from backend.app.runner.worker_claim_policy import _runner_claim_gate_paused
from backend.app.runner.worker_db_budget import decide_worker_db_budget
from backend.app.runner.worker_startup import _load_active_runner_ids

logger = logging.getLogger("backend.app.runner.worker")


def _worker_facade():
    return sys.modules.get("backend.app.runner.worker")


def _facade_attr(name: str, fallback):
    facade = _worker_facade()
    return getattr(facade, name, fallback) if facade is not None else fallback

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

        active_runner_ids: set[str] = {current_runner_id}
        active_runner_ids.update(
            await _load_active_runner_ids(
                redis_queue,
                tasks_store,
                max_age_seconds=heartbeat_max_age,
            )
        )

        cleanup_patterns = [
            item.strip()
            for item in os.getenv(
                "LOCAL_CORE_RUNNER_LOCK_CLEANUP_PATTERNS",
                "concurrency:*,ig_profile:*",
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
                keys.extend(
                    _resolve_lock_keys(
                        ctx,
                        str(task.pack_id or ""),
                        persisted_concurrency_key=getattr(
                            task,
                            "concurrency_key",
                            None,
                        ),
                    )
                )
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
) -> bool:
    """Keep the ready frontier warm even when the dequeue loop is idle."""
    claim_gate_paused, claim_gate = _facade_attr("_runner_claim_gate_paused", _runner_claim_gate_paused)()
    if claim_gate_paused:
        logger.warning(
            "Runner maintenance skipped while claim gate is paused reason=%s source=%s",
            claim_gate.get("reason"),
            claim_gate.get("source"),
        )
        return False

    if hasattr(redis_queue, "_get_client"):
        db_pressure = await _facade_attr("check_db_pool_pressure", check_db_pool_pressure)(
            redis_queue,
            owner_id=f"{runner_id}:maintenance",
        )
        db_budget = decide_worker_db_budget(
            db_pressure,
            profile_code="maintenance",
            inflight=0,
            max_inflight=1,
        )
        if not db_budget.allow_release_maintenance:
            logger.warning(
                "Runner maintenance skipped by DB budget "
                "reason=%s wait_seconds=%s",
                db_budget.reason,
                db_budget.wait_seconds,
            )
            return False

    loop = asyncio.get_running_loop()
    await asyncio.to_thread(
        _facade_attr("_reap_stale_running_tasks", _reap_stale_running_tasks),
        tasks_store,
        runner_id=runner_id,
        redis_queue=redis_queue,
        event_loop=loop,
    )
    await _facade_attr("_cleanup_stale_locks", _cleanup_stale_locks)(redis_queue, runner_id, tasks_store)
    await asyncio.to_thread(
        _facade_attr("_request_watchdog_abort_for_no_progress_tasks", _request_watchdog_abort_for_no_progress_tasks),
        tasks_store,
        watcher_id=f"runner_maintenance:{runner_id}",
    )
    for shard_name in ready_queues.keys():
        await _facade_attr("_reap_redis_queues", _reap_redis_queues)(
            tasks_store,
            ready_queues[shard_name],
            ready_target_override=ready_targets.get(shard_name, 0),
            all_queues=queue_cycle,
        )
    return True


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
    db_recovery_backoff = RunnerDatabaseRecoveryBackoff(
        delay_seconds=_env_int("LOCAL_CORE_RUNNER_DB_RECOVERY_BACKOFF_SECONDS", 30)
    )
    while True:
        try:
            maintenance_ran = await _run_maintenance_cycle(
                tasks_store,
                runner_id=runner_id,
                redis_queue=redis_queue,
                ready_queues=ready_queues,
                ready_targets=ready_targets,
                queue_cycle=queue_cycle,
            )
            if not maintenance_ran:
                await asyncio.sleep(reap_interval_seconds)
                continue
            try:
                snapshot_result = await write_queue_utilization_snapshot_if_leader(
                    queue_stores=list(ready_queues.values()),
                    scan_limit=_env_int(
                        "LOCAL_CORE_RUNNER_QUEUE_UTILIZATION_SCAN_LIMIT",
                        _env_int("LOCAL_CORE_RUNNER_PLAYBOOK_FAIR_SCAN_LIMIT", 128),
                    ),
                )
                if snapshot_result.get("written"):
                    logger.debug(
                        "Runner queue utilization snapshot written rows=%s",
                        snapshot_result.get("inserted"),
                    )
            except Exception as snapshot_exc:
                logger.debug(
                    "Runner queue utilization snapshot skipped: %s",
                    snapshot_exc,
                )
        except Exception as e:
            if db_recovery_backoff.note_failure(e):
                if db_recovery_backoff.should_log():
                    logger.warning(
                        "Runner maintenance paused while PostgreSQL is recovering."
                    )
                await asyncio.sleep(db_recovery_backoff.remaining_seconds())
                continue
            logger.warning(f"Failed to run runner maintenance cycle: {e}")
        await asyncio.sleep(reap_interval_seconds)
