"""Runner worker main loop orchestration."""

import asyncio
import logging
import os

from backend.app.services.runner_topology import (
    DEFAULT_LOCAL_QUEUE_PARTITION,
    resolve_runner_capacity_snapshot,
    resolve_runner_profile_from_env,
)
from backend.app.services.stores.redis.runner_queue_store import RedisRunnerQueueStore
from backend.app.services.stores.tasks_store import TasksStore
from backend.app.runner.database_backoff import RunnerDatabaseRecoveryBackoff
from backend.app.runner.db_pool_pressure import DbPoolPressureDecision, check_db_pool_pressure
from backend.app.runner.dependency_check import DependencyChecker
from backend.app.runner.resource_pressure import (
    build_runner_resource_snapshot,
    is_browser_resource_profile,
    should_defer_browser_claim,
)
from backend.app.runner.maintenance_leader import (
    resolve_maintenance_lease_seconds,
    try_hold_maintenance_leadership,
)
from backend.app.runner.utils import _env_int
from backend.app.runner.worker_claim_policy import (
    _dequeue_by_browser_fair_candidate_policy,
    _dequeue_by_route_gate_policy,
    _route_drain_after_current_status,
    _runner_claim_gate_paused,
)
from backend.app.runner.worker_dispatch import _dispatch_claimed_task
from backend.app.runner.worker_loop_control import (
    _build_initial_resource_snapshot,
    _discard_finished_tasks,
    _exit_for_restart_if_requested,
    _maybe_write_postgres_runner_heartbeat,
    _publish_resource_heartbeat,
    _resolve_loop_claim_budget,
)
from backend.app.runner.worker_maintenance import (
    _cleanup_stale_locks,
    _maintenance_loop,
    _run_maintenance_cycle,
)
from backend.app.runner.worker_startup import (
    _backfill_pending_to_redis,
    _postgres_runner_heartbeat_enabled,
    _purge_task_ids_from_transport,
    _reset_orphaned_running_tasks,
    _runner_lock_ttl_seconds,
)
from backend.app.runner.worker_transport import (
    _build_ready_queue_stores,
    _dequeue_from_ready_queues,
    _split_ready_target,
)
from backend.app.runner.concurrency import _runner_id

logger = logging.getLogger("backend.app.runner.worker")


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _runner_startup_reconcile_enabled() -> bool:
    return _env_bool("LOCAL_CORE_RUNNER_STARTUP_RECONCILE_ENABLED", True)


async def run_forever() -> None:
    poll_interval_ms = _env_int("LOCAL_CORE_RUNNER_POLL_INTERVAL_MS", 1000)
    max_inflight = _env_int("LOCAL_CORE_RUNNER_MAX_INFLIGHT", 1)
    configured_poll_batch_limit = _env_int("LOCAL_CORE_RUNNER_POLL_BATCH_LIMIT", 0)
    runner_id = _runner_id()
    os.environ["LOCAL_CORE_RUNNER_ID"] = runner_id
    visibility_timeout_sec = _env_int("LOCAL_CORE_RUNNER_VISIBILITY_TIMEOUT_SECONDS", 180)
    lock_ttl_seconds = _runner_lock_ttl_seconds()
    runner_profile = resolve_runner_profile_from_env(default_max_inflight=max_inflight)
    max_inflight = runner_profile.max_inflight
    capacity = resolve_runner_capacity_snapshot(
        runner_profile,
        inflight=0,
        configured_poll_batch_limit=configured_poll_batch_limit,
    )

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
    reap_interval_seconds = _env_int("LOCAL_CORE_RUNNER_REAP_INTERVAL_SECONDS", 60)
    maintenance_lease_seconds = resolve_maintenance_lease_seconds(
        reap_interval_seconds
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

    postgres_heartbeat_enabled = _postgres_runner_heartbeat_enabled()
    if postgres_heartbeat_enabled:
        try:
            tasks_store.ensure_runner_heartbeats_table()
        except Exception:
            pass

    claim_gate_paused, startup_claim_gate = _runner_claim_gate_paused()
    startup_db_pressure = DbPoolPressureDecision.open(reason="startup_not_checked")
    startup_maintenance_leader = False
    if not claim_gate_paused:
        startup_maintenance_leader = await try_hold_maintenance_leadership(
            redis_queue,
            runner_id=runner_id,
            ttl_seconds=maintenance_lease_seconds,
        )
        if startup_maintenance_leader:
            startup_db_pressure = await check_db_pool_pressure(
                redis_queue,
                owner_id=f"{runner_id}:startup",
            )
    startup_reconcile_enabled = _runner_startup_reconcile_enabled()
    if not startup_reconcile_enabled:
        logger.info(
            "Runner startup reconciliation disabled by env profile=%s",
            runner_profile.profile_code,
        )
    elif claim_gate_paused:
        logger.warning(
            "Runner startup reconciliation skipped while claim gate is paused "
            "profile=%s reason=%s source=%s",
            runner_profile.profile_code,
            startup_claim_gate.get("reason"),
            startup_claim_gate.get("source"),
        )
    elif not startup_maintenance_leader:
        logger.info(
            "Runner startup reconciliation skipped because another runner owns "
            "maintenance leadership profile=%s",
            runner_profile.profile_code,
        )
    elif startup_db_pressure.paused:
        logger.warning(
            "Runner startup reconciliation skipped while PgBouncer pressure is active "
            "profile=%s reason=%s wait_seconds=%s",
            runner_profile.profile_code,
            startup_db_pressure.reason,
            startup_db_pressure.wait_seconds,
        )
    elif not startup_db_pressure.paused:
        # Reset running tasks from dead runners.
        reset_task_ids = await _reset_orphaned_running_tasks(
            tasks_store, runner_id, runner_profile, redis_queue
        )
        if reset_task_ids:
            await _purge_task_ids_from_transport(reset_task_ids, queue_cycle)

        # Recover pending tasks lost during restart.
        await _backfill_pending_to_redis(tasks_store, ready_queues)

        # Remove locks from dead runner instances.
        await _cleanup_stale_locks(redis_queue, runner_id, tasks_store)

    inflight: set[asyncio.Task] = set()
    dep_checker = DependencyChecker(cache_ttl=5.0)
    is_browser_runner = is_browser_resource_profile(runner_profile)
    next_resource_defer_log_at = 0.0
    next_claim_gate_log_at = 0.0
    next_route_drain_gate_log_at = 0.0
    next_db_pressure_log_at = 0.0
    next_postgres_heartbeat_pressure_log_at = 0.0
    next_runner_claim_control_log_at = 0.0
    last_postgres_heartbeat_epoch = 0.0
    playbook_fair_scan_limit = _env_int(
        "LOCAL_CORE_RUNNER_PLAYBOOK_FAIR_SCAN_LIMIT",
        128,
    )
    db_recovery_backoff = RunnerDatabaseRecoveryBackoff(
        delay_seconds=_env_int("LOCAL_CORE_RUNNER_DB_RECOVERY_BACKOFF_SECONDS", 30)
    )

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
            maintenance_lease_seconds=maintenance_lease_seconds,
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
            maintenance_lease_seconds=maintenance_lease_seconds,
        )
    )
    logger.info(
        "Runner maintenance loop started (interval=%ss)", reap_interval_seconds
    )

    while True:
        _discard_finished_tasks(inflight)
        capacity = resolve_runner_capacity_snapshot(
            runner_profile,
            inflight=len(inflight),
            configured_poll_batch_limit=configured_poll_batch_limit,
        )
        resource_snapshot = _build_initial_resource_snapshot(
            runner_profile,
            inflight=len(inflight),
            max_inflight=max_inflight,
        )
        (
            runner_claim_control,
            runner_claiming_enabled,
            db_pressure,
            db_budget,
        ) = await _resolve_loop_claim_budget(
            redis_queue,
            runner_id=runner_id,
            runner_profile=runner_profile,
            inflight=len(inflight),
            max_inflight=max_inflight,
        )
        (
            last_postgres_heartbeat_epoch,
            next_postgres_heartbeat_pressure_log_at,
        ) = _maybe_write_postgres_runner_heartbeat(
            enabled=postgres_heartbeat_enabled,
            tasks_store=tasks_store,
            runner_id=runner_id,
            runner_profile=runner_profile,
            inflight=len(inflight),
            resource_snapshot=resource_snapshot,
            db_budget=db_budget,
            db_pressure=db_pressure,
            db_recovery_backoff=db_recovery_backoff,
            runner_claiming_enabled=runner_claiming_enabled,
            last_write_epoch=last_postgres_heartbeat_epoch,
            next_pressure_log_at=next_postgres_heartbeat_pressure_log_at,
        )
        await _publish_resource_heartbeat(
            redis_queue,
            runner_id=runner_id,
            runner_profile=runner_profile,
            capacity=capacity,
            resource_snapshot=resource_snapshot,
            runner_claim_control=runner_claim_control,
        )
        await _exit_for_restart_if_requested(inflight)
        _discard_finished_tasks(inflight)

        if db_recovery_backoff.is_active():
            if db_recovery_backoff.should_log():
                logger.warning(
                    "Runner claim loop paused while PostgreSQL is recovering; inflight=%s remaining_backoff=%.1fs",
                    len(inflight),
                    db_recovery_backoff.remaining_seconds(),
                )
            await asyncio.sleep(
                min(
                    max(poll_interval_ms / 1000, 0.25),
                    db_recovery_backoff.remaining_seconds(),
                    5.0,
                )
            )
            continue

        if not runner_claiming_enabled:
            now_loop = asyncio.get_event_loop().time()
            if now_loop >= next_runner_claim_control_log_at:
                logger.warning(
                    "Runner claim mode blocks new claims runner_id=%s profile=%s mode=%s inflight=%s reason=%s",
                    runner_id,
                    runner_profile.profile_code,
                    runner_claim_control.mode,
                    len(inflight),
                    runner_claim_control.reason,
                )
                next_runner_claim_control_log_at = now_loop + 30.0
            await asyncio.sleep(poll_interval_ms / 1000)
            continue

        claim_gate_paused, claim_gate = _runner_claim_gate_paused()
        if claim_gate_paused:
            now_loop = asyncio.get_event_loop().time()
            if now_loop >= next_claim_gate_log_at:
                logger.warning(
                    "Runner claim gate paused profile=%s reason=%s source=%s inflight=%s",
                    runner_profile.profile_code,
                    claim_gate.get("reason"),
                    claim_gate.get("source"),
                    len(inflight),
                )
                next_claim_gate_log_at = now_loop + 30.0
            await asyncio.sleep(poll_interval_ms / 1000)
            continue

        if not db_budget.allow_claim_scan:
            now_loop = asyncio.get_event_loop().time()
            if now_loop >= next_db_pressure_log_at:
                logger.warning(
                    "Runner claim loop paused by DB budget "
                    "profile=%s reason=%s wait_seconds=%s inflight=%s",
                    runner_profile.profile_code,
                    db_budget.reason,
                    db_budget.wait_seconds,
                    len(inflight),
                )
                next_db_pressure_log_at = now_loop + 30.0
            await asyncio.sleep(
                max(poll_interval_ms / 1000, min(db_budget.wait_seconds, 5))
            )
            continue

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

        task_id = None
        task_queue = None
        route_drain_wait = False
        if is_browser_runner:
            task_id, task_queue, route_drain_wait = (
                await _dequeue_by_browser_fair_candidate_policy(
                    queue_cycle,
                    tasks_store=tasks_store,
                    runner_profile=runner_profile,
                    visibility_timeout_sec=visibility_timeout_sec,
                    scan_limit=db_budget.apply_claim_scan_limit(playbook_fair_scan_limit),
                )
            )
        else:
            active_pack_ids = {
                str(getattr(task, "_mindscape_pack_id", "") or "")
                for task in inflight
                if str(getattr(task, "_mindscape_pack_id", "") or "").strip()
            }
            task_id, task_queue, route_drain_wait = await _dequeue_by_route_gate_policy(
                queue_cycle,
                runner_profile=runner_profile,
                visibility_timeout_sec=visibility_timeout_sec,
                scan_limit=db_budget.apply_claim_scan_limit(playbook_fair_scan_limit),
                active_pack_ids=active_pack_ids,
            )
        if route_drain_wait:
            route_drain_gate = _route_drain_after_current_status()
            now_loop = asyncio.get_event_loop().time()
            if now_loop >= next_route_drain_gate_log_at:
                logger.warning(
                    "Runner route drain gate waiting profile=%s reservation_ids=%s inflight=%s",
                    runner_profile.profile_code,
                    ",".join(route_drain_gate.get("reservation_ids") or []),
                    len(inflight),
                )
                next_route_drain_gate_log_at = now_loop + 30.0
            await asyncio.sleep(poll_interval_ms / 1000)
            continue

        # Blocking pop from pending to processing replaces DB polling.
        if not task_id or not task_queue:
            task_id, task_queue, queue_cursor = await _dequeue_from_ready_queues(
                queue_cycle,
                cursor=queue_cursor,
                visibility_timeout_sec=visibility_timeout_sec,
                block_timeout_sec=2,
            )

        if not task_id or not task_queue:
            continue

        dispatch_task = await _dispatch_claimed_task(
            task_id,
            task_queue,
            tasks_store=tasks_store,
            runner_id=runner_id,
            redis_queue=redis_queue,
            runner_profile=runner_profile,
            db_budget=db_budget,
            resource_snapshot=resource_snapshot,
            capacity=capacity,
            dep_checker=dep_checker,
            visibility_timeout_sec=visibility_timeout_sec,
            lock_ttl_seconds=lock_ttl_seconds,
            db_recovery_backoff=db_recovery_backoff,
        )
        if dispatch_task is not None:
            inflight.add(dispatch_task)
