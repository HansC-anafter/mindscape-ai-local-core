"""Runner worker main loop coordinator.

This file was refactored from a 1150-line monolith into a slim coordinator
that delegates to focused sub-modules:

  utils.py          - _utc_now, _parse_utc_iso, _env_int
  concurrency.py    - _runner_id, _resolve_lock_key, _build_inputs
  lifecycle_hooks.py - _invoke_on_fail_hook
  reaper.py         - _reap_stale_running_tasks, _reap_redis_queues
  task_executor.py  - _child_execute_playbook, _run_single_task
  restart.py        - _check_restart_sentinel
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
from backend.app.services.runner_resources import (
    RedisResourceLeaseStore,
    acquire_task_resource_admission,
    build_resource_wait_task_update,
    build_runner_resource_heartbeat,
    list_active_runner_resource_heartbeats,
    publish_runner_resource_heartbeat,
    release_acquired_resource_leases,
    resolve_resource_requirements,
)
from backend.app.services.stores.tasks_store import TasksStore

from backend.app.services.stores.redis.runner_queue_store import RedisRunnerQueueStore
from backend.app.services.host_resources.route_identity_projection import (
    build_route_identity_projection,
    read_route_identity_projections,
)
from backend.app.services.host_resources.queue_utilization import (
    write_queue_utilization_snapshot_if_leader,
)

# Sub-module imports
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
from backend.app.runner.database_backoff import (
    RunnerDatabaseRecoveryBackoff,
    is_database_recovery_error,
)
from backend.app.runner.db_pool_pressure import (
    DbPoolPressureDecision,
    check_db_pool_pressure,
    should_write_postgres_heartbeat,
)
from backend.app.runner.browser_fair_candidate_scheduler import (
    select_browser_fair_candidate,
)

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
    "_repair_misqueued_task_if_needed",
    "_dequeue_by_browser_fair_candidate_policy",
    "run_forever",
    "main",
]


def _runner_lock_ttl_seconds() -> int:
    return _env_int("LOCAL_CORE_RUNNER_LOCK_TTL_SECONDS", 120)


def _postgres_runner_heartbeat_enabled() -> bool:
    return os.getenv(
        "LOCAL_CORE_RUNNER_POSTGRES_HEARTBEAT_ENABLED",
        "false",
    ).lower() in {"1", "true", "yes", "on"}


async def _load_active_runner_ids(
    redis_queue: Optional[RedisRunnerQueueStore],
    tasks_store: TasksStore,
    *,
    max_age_seconds: int,
) -> set[str]:
    active_runner_ids: set[str] = set()
    if redis_queue is not None:
        try:
            heartbeats = await list_active_runner_resource_heartbeats(redis_queue)
            active_runner_ids.update(
                str(row.get("runner_id") or "").strip()
                for row in heartbeats
                if str(row.get("runner_id") or "").strip()
            )
        except Exception:
            pass
    if active_runner_ids:
        return active_runner_ids

    try:
        heartbeats = await asyncio.to_thread(
            tasks_store.list_runner_heartbeats,
            max_age_seconds=max_age_seconds,
            limit=500,
        )
        active_runner_ids.update(
            str(row.get("runner_id") or "").strip()
            for row in heartbeats
            if str(row.get("runner_id") or "").strip()
        )
    except Exception:
        pass
    return active_runner_ids


# ============================================================
#  Redis is not durable, so container restart can remove pending task
#  entries from the transport queue. This one-shot backfill reads
#  PostgreSQL and re-enqueues tasks that are still pending.
# ============================================================


async def _reset_orphaned_running_tasks(
    tasks_store: TasksStore,
    current_runner_id: str,
    runner_profile=None,
    redis_queue: Optional[RedisRunnerQueueStore] = None,
) -> set[str]:
    """Reset running tasks from dead runners back to PENDING on startup.

    After a runner restart, old subprocesses are killed but their DB tasks
    may still be marked 'running' with a stale runner_id.  This function
    detects those orphans and resets them so they get cleanly re-queued.
    """
    reset_task_ids: set[str] = set()
    try:
        if runner_profile is None:
            runner_profile = resolve_runner_profile_from_env(
                default_max_inflight=_env_int("LOCAL_CORE_RUNNER_MAX_INFLIGHT", 1)
            )
        active_runner_ids: set[str] = {current_runner_id}
        heartbeat_max_age = _env_int(
            "LOCAL_CORE_RUNNER_ORPHAN_HEARTBEAT_MAX_AGE_SECONDS",
            120,
        )
        active_runner_ids.update(
            await _load_active_runner_ids(
                redis_queue,
                tasks_store,
                max_age_seconds=heartbeat_max_age,
            )
        )

        running = await asyncio.to_thread(
            tasks_store.list_running_playbook_execution_tasks,
            workspace_id=None, limit=500,
        )
        reset_count = 0
        for t in running:
            ctx = t.execution_context if isinstance(t.execution_context, dict) else {}
            old_runner = getattr(t, "runner_id", None) or ctx.get("runner_id")
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
                    frontier_state="ready",
                    started_at=None,
                    blocked_reason=None,
                    queue_shard=getattr(t, "queue_shard", None),
                    runner_id=None,
                    heartbeat_at=None,
                )
                reset_task_ids.add(str(t.id))
                reset_count += 1
                logger.info(
                    f"[Startup] Reset orphaned running task {t.id} "
                    f"(old_runner={old_runner})"
                )
        if reset_count:
            logger.info(f"[Startup] Reset {reset_count} orphaned running task(s)")

        pending = await asyncio.to_thread(
            tasks_store.list_tasks_by_workspace,
            None,
            status=TaskStatus.PENDING,
            limit=500,
            exclude_cancelled=True,
        )
        for t in pending:
            ctx = t.execution_context if isinstance(t.execution_context, dict) else {}
            ctx2 = dict(ctx)
            update_kwargs = {}
            frontier_state = str(getattr(t, "frontier_state", "") or "").strip()
            if frontier_state in {"running", "cold"}:
                ctx2["status"] = "queued"
                ctx2["runner_reaper"] = {
                    "action": "startup_reset",
                    "new_runner_id": current_runner_id,
                }
                update_kwargs.update(
                    {
                        "status": TaskStatus.PENDING,
                        "frontier_state": "ready",
                        "blocked_reason": None,
                        "queue_shard": getattr(t, "queue_shard", None),
                    }
                )

            concurrency = ctx2.get("concurrency")
            inputs = ctx2.get("inputs") if isinstance(ctx2.get("inputs"), dict) else {}
            reference_id = str(inputs.get("reference_id") or "").strip()
            if (
                isinstance(concurrency, dict)
                and concurrency.get("lock_scope") == "playbook"
                and reference_id
            ):
                ctx2["concurrency"] = {
                    "lock_scope": "playbook_input",
                    "lock_key_input": "reference_id",
                    "max_parallel": 1,
                }
                update_kwargs["concurrency_key"] = (
                    f"concurrency:playbook_input:{t.pack_id}:{reference_id}"
                )

            if update_kwargs:
                update_kwargs["execution_context"] = ctx2
                tasks_store.update_task(t.id, **update_kwargs)
                reset_task_ids.add(str(t.id))
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
                await redis_queue.enqueue_task(
                    tid,
                    route_identity=build_route_identity_projection(t),
                )
                queued.add(tid)
                enqueued += 1

        if not enqueued and not scanned:
            logger.info("[Backfill] No runnable pending tasks in DB - nothing to enqueue.")
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


async def _repair_misqueued_task_if_needed(
    task_id: str,
    task_data,
    task_queue: RedisRunnerQueueStore,
) -> bool:
    expected_shard = normalize_queue_partition(
        getattr(task_data, "queue_shard", None),
        fallback=DEFAULT_LOCAL_QUEUE_PARTITION,
    )
    current_shard = normalize_queue_partition(
        getattr(task_queue, "pack_id", None),
        fallback=DEFAULT_LOCAL_QUEUE_PARTITION,
    )
    if expected_shard == current_shard:
        return False

    target_queue = RedisRunnerQueueStore(pack_id=expected_shard)
    try:
        enqueued = await target_queue.enqueue_task(
            task_id,
            route_identity=build_route_identity_projection(task_data),
        )
    except TypeError:
        enqueued = await target_queue.enqueue_task(task_id)
    if not enqueued:
        logger.warning(
            "[Worker] Failed to repair misqueued task %s from %s to %s",
            task_id,
            current_shard,
            expected_shard,
        )
        return False

    await task_queue.ack_task(task_id)
    logger.warning(
        "[Worker] Repaired misqueued task %s from %s to %s",
        task_id,
        current_shard,
        expected_shard,
    )
    return True


def _host_route_gate_enabled() -> bool:
    raw = os.getenv("LOCAL_CORE_HOST_RESOURCE_ROUTE_GATE_ENABLED", "true")
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _runner_claim_gate_status() -> dict:
    try:
        from backend.app.services.host_resources import get_runner_claim_gate

        return get_runner_claim_gate()
    except Exception:
        return {"state": "open", "source": "unavailable", "persisted": False}


def _runner_claim_gate_paused() -> tuple[bool, dict]:
    gate = _runner_claim_gate_status()
    return gate.get("state") == "paused", gate


def _route_drain_after_current_status() -> dict:
    if not _host_route_gate_enabled():
        return {"active": False, "source": "disabled", "reservation_ids": []}
    try:
        from backend.app.services.host_resources import route_gate

        active_reservations = route_gate.get_active_route_reservations()
        drain_reservations = route_gate.drain_after_current_reservations(
            active_reservations
        )
        return {
            "active": bool(drain_reservations),
            "source": "route_reservation",
            "reservation_ids": [
                str(reservation.get("reservation_id") or "")
                for reservation in drain_reservations
                if isinstance(reservation, dict)
            ],
        }
    except Exception:
        return {"active": False, "source": "unavailable", "reservation_ids": []}


async def _dequeue_by_route_gate_policy(
    queue_cycle: list[RedisRunnerQueueStore],
    *,
    runner_profile,
    visibility_timeout_sec: int,
    scan_limit: int,
    active_pack_ids: set[str] | None = None,
) -> tuple[Optional[str], Optional[RedisRunnerQueueStore], bool]:
    if not queue_cycle or scan_limit <= 0:
        return None, None, False
    if not _host_route_gate_enabled():
        return None, None, False

    try:
        from backend.app.services.host_resources import route_gate

        active_reservations = route_gate.get_active_route_reservations()
    except Exception:
        return None, None, False

    candidates: list[dict] = []
    seen: set[str] = set()
    for queue_store in queue_cycle:
        client = await queue_store._get_client()
        if not client:
            continue
        try:
            candidate_ids = await client.lrange(
                queue_store.q_pending,
                0,
                max(0, scan_limit - 1),
            )
        except Exception as e:
            logger.warning(
                "[Worker] Failed to scan ready queue %s for route gate: %s",
                queue_store.pack_id,
                e,
            )
            continue
        task_ids: list[str] = []
        positions: dict[str, int] = {}
        for position, raw_task_id in enumerate(candidate_ids):
            task_id = _normalize_task_id(raw_task_id).strip()
            if not task_id or task_id in seen:
                continue
            seen.add(task_id)
            task_ids.append(task_id)
            positions[task_id] = position

        projections = await read_route_identity_projections(client, task_ids)
        for task_id in task_ids:
            projection = projections.get(task_id)
            if not projection:
                logger.debug(
                    "[Worker] Route identity projection missing task=%s queue=%s",
                    task_id,
                    queue_store.pack_id,
                )
                continue
            if not runner_profile_can_claim_task(runner_profile, projection):
                continue
            candidates.append(
                {
                    **projection,
                    "queue": queue_store.pack_id,
                    "queue_position": positions.get(task_id, 0),
                    "queue_store": queue_store,
                    "pack_id": projection.get("pack_id"),
                    "route_identity": projection.get("route_identity") or {},
                }
            )

    selection = route_gate.select_candidate_policy(
        candidates,
        active_reservations=active_reservations,
        reserved_share_pack_ids=[],
        active_pack_ids=active_pack_ids or set(),
    )
    if selection.get("drain_wait"):
        return None, None, True
    selected = selection.get("selected")
    if not isinstance(selected, dict):
        return None, None, False
    task_id = str(selected.get("task_id") or "").strip()
    queue_store = selected.get("queue_store")
    if not task_id or not hasattr(queue_store, "promote_pending_task_by_id"):
        return None, None, False
    moved = await queue_store.promote_pending_task_by_id(
        task_id,
        visibility_timeout_sec=visibility_timeout_sec,
    )
    if moved:
        logger.info(
            "[Worker] Route gate policy selected task %s reason=%s queue=%s",
            task_id,
            selection.get("reason"),
            queue_store.pack_id,
        )
        return moved, queue_store, False
    return None, None, False


async def _dequeue_by_browser_fair_candidate_policy(
    queue_cycle: list[RedisRunnerQueueStore],
    *,
    tasks_store: TasksStore,
    runner_profile,
    visibility_timeout_sec: int,
    scan_limit: int,
) -> tuple[Optional[str], Optional[RedisRunnerQueueStore], bool]:
    if (
        not queue_cycle
        or scan_limit <= 0
        or not is_browser_resource_profile(runner_profile)
    ):
        return None, None, False

    try:
        from backend.app.services.host_resources import route_gate

        active_reservations = route_gate.get_active_route_reservations()
    except Exception:
        active_reservations = []

    candidates: list[dict] = []
    seen: set[str] = set()
    for queue_store in queue_cycle:
        client = await queue_store._get_client()
        if not client:
            continue
        try:
            candidate_ids = await client.lrange(
                queue_store.q_pending,
                0,
                max(0, scan_limit - 1),
            )
        except Exception as e:
            logger.warning(
                "[Worker] Failed to scan ready queue %s for browser fairness: %s",
                queue_store.pack_id,
                e,
            )
            continue

        task_ids: list[str] = []
        positions: dict[str, int] = {}
        for position, raw_task_id in enumerate(candidate_ids):
            task_id = _normalize_task_id(raw_task_id).strip()
            if not task_id or task_id in seen:
                continue
            seen.add(task_id)
            task_ids.append(task_id)
            positions[task_id] = position
        if not task_ids:
            continue

        route_projections = await read_route_identity_projections(client, task_ids)
        db_projections = await asyncio.to_thread(
            tasks_store.list_runner_candidate_projections_by_ids,
            task_ids,
            queue_store.pack_id,
        )
        projections_by_id = {
            str(
                projection.get("task_id") or projection.get("id") or ""
            ).strip(): projection
            for projection in db_projections
            if str(projection.get("task_id") or projection.get("id") or "").strip()
        }
        for task_id in task_ids:
            projection = projections_by_id.get(task_id)
            if not projection:
                continue
            route_projection = route_projections.get(task_id) or {}
            route_identity = (
                route_projection.get("route_identity")
                if isinstance(route_projection, dict)
                else None
            )
            candidate = {
                **projection,
                "queue": queue_store.pack_id,
                "queue_position": positions.get(task_id, 0),
                "queue_store": queue_store,
                "route_identity": (
                    route_identity if isinstance(route_identity, dict) else {}
                ),
            }
            if not runner_profile_can_claim_task(runner_profile, candidate):
                continue
            candidates.append(candidate)

    if not candidates:
        return None, None, False

    route_selection = route_gate.select_candidate_policy(
        candidates,
        active_reservations=active_reservations,
        reserved_share_pack_ids=[],
        active_pack_ids=set(),
    )
    if route_selection.get("drain_wait"):
        return None, None, True

    selected = route_selection.get("selected")
    reason = str(route_selection.get("reason") or "")
    if reason == "route_reservation" and isinstance(selected, dict):
        task_id = str(selected.get("task_id") or selected.get("id") or "").strip()
        queue_store = selected.get("queue_store")
        if task_id and hasattr(queue_store, "promote_pending_task_by_id"):
            moved = await queue_store.promote_pending_task_by_id(
                task_id,
                visibility_timeout_sec=visibility_timeout_sec,
            )
            if moved:
                logger.info(
                    "[Worker] Browser route policy selected task %s queue=%s",
                    task_id,
                    queue_store.pack_id,
                )
                return moved, queue_store, False
        return None, None, False

    queue_shard = queue_cycle[0].pack_id
    running_counts = await asyncio.to_thread(
        tasks_store.count_running_browser_lanes,
        queue_shard,
    )
    fair_decision = select_browser_fair_candidate(candidates, running_counts)
    if not fair_decision.selected_task_id:
        return None, None, False

    selected_candidate = next(
        (
            candidate
            for candidate in candidates
            if str(candidate.get("task_id") or candidate.get("id") or "").strip()
            == fair_decision.selected_task_id
        ),
        None,
    )
    if not selected_candidate:
        return None, None, False
    queue_store = selected_candidate.get("queue_store")
    if not hasattr(queue_store, "promote_pending_task_by_id"):
        return None, None, False

    moved = await queue_store.promote_pending_task_by_id(
        fair_decision.selected_task_id,
        visibility_timeout_sec=visibility_timeout_sec,
    )
    if moved:
        logger.info(
            "[Worker] Browser fair policy selected task %s lane=%s running_count=%s queue=%s",
            fair_decision.selected_task_id,
            fair_decision.selected_lane,
            fair_decision.running_count,
            queue_store.pack_id,
        )
        return moved, queue_store, False
    return None, None, False


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
    previous_runner_id = ctx2.pop("runner_id", None)
    ctx2.pop("heartbeat_at", None)
    if previous_runner_id and not ctx2.get("last_runner_id"):
        ctx2["last_runner_id"] = previous_runner_id
    ctx2["resume_after"] = next_eligible_at.isoformat()
    ctx2.pop("resource_admission", None)
    ctx2.pop("runner_resource_leases", None)

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
    claim_gate_paused, claim_gate = _runner_claim_gate_paused()
    if claim_gate_paused:
        logger.warning(
            "Runner maintenance skipped while claim gate is paused reason=%s source=%s",
            claim_gate.get("reason"),
            claim_gate.get("source"),
        )
        return False

    db_pressure = await check_db_pool_pressure(
        redis_queue,
        owner_id=f"{runner_id}:maintenance",
    )
    if db_pressure.paused:
        logger.warning(
            "Runner maintenance skipped while PgBouncer pressure is active "
            "reason=%s wait_seconds=%s",
            db_pressure.reason,
            db_pressure.wait_seconds,
        )
        return False

    loop = asyncio.get_running_loop()
    await asyncio.to_thread(
        _reap_stale_running_tasks,
        tasks_store,
        runner_id=runner_id,
        redis_queue=redis_queue,
        event_loop=loop,
    )
    await _cleanup_stale_locks(redis_queue, runner_id, tasks_store)
    await asyncio.to_thread(
        _request_watchdog_abort_for_no_progress_tasks,
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

    postgres_heartbeat_enabled = _postgres_runner_heartbeat_enabled()
    if postgres_heartbeat_enabled:
        try:
            tasks_store.ensure_runner_heartbeats_table()
        except Exception:
            pass

    claim_gate_paused, startup_claim_gate = _runner_claim_gate_paused()
    startup_db_pressure = DbPoolPressureDecision.open(reason="startup_not_checked")
    if not claim_gate_paused:
        startup_db_pressure = await check_db_pool_pressure(
            redis_queue,
            owner_id=f"{runner_id}:startup",
        )
    if claim_gate_paused:
        logger.warning(
            "Runner startup reconciliation skipped while claim gate is paused "
            "profile=%s reason=%s source=%s",
            runner_profile.profile_code,
            startup_claim_gate.get("reason"),
            startup_claim_gate.get("source"),
        )
    elif startup_db_pressure.paused:
        logger.warning(
            "Runner startup reconciliation skipped while PgBouncer pressure is active "
            "profile=%s reason=%s wait_seconds=%s",
            runner_profile.profile_code,
            startup_db_pressure.reason,
            startup_db_pressure.wait_seconds,
        )
    else:
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
    reap_interval_seconds = _env_int("LOCAL_CORE_RUNNER_REAP_INTERVAL_SECONDS", 60)
    dep_checker = DependencyChecker(cache_ttl=5.0)
    is_browser_runner = is_browser_resource_profile(runner_profile)
    next_resource_defer_log_at = 0.0
    next_claim_gate_log_at = 0.0
    next_route_drain_gate_log_at = 0.0
    next_db_pressure_log_at = 0.0
    next_postgres_heartbeat_pressure_log_at = 0.0
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
        db_pressure = DbPoolPressureDecision.open(reason="pgbouncer_pressure_not_checked")
        try:
            resource_snapshot = build_runner_resource_snapshot(
                profile_code=runner_profile.profile_code,
                inflight=len(inflight),
                max_inflight=max_inflight,
            )
        except Exception:
            resource_snapshot = None

        try:
            db_pressure = await check_db_pool_pressure(
                redis_queue,
                owner_id=f"{runner_id}:claim",
            )
        except Exception as e:
            logger.warning("PgBouncer pressure check failed in runner loop: %s", e)
            db_pressure = DbPoolPressureDecision.paused_for(
                "pgbouncer_pressure_probe_failed"
            )

        if postgres_heartbeat_enabled:
            now_epoch = datetime.now(timezone.utc).timestamp()
            if should_write_postgres_heartbeat(
                db_pressure,
                now_epoch=now_epoch,
                last_write_epoch=last_postgres_heartbeat_epoch,
            ):
                try:
                    tasks_store.upsert_runner_heartbeat(
                        runner_id,
                        profile_code=runner_profile.profile_code,
                        hostname=socket.gethostname(),
                        inflight=len(inflight),
                        resource_snapshot=resource_snapshot,
                    )
                    last_postgres_heartbeat_epoch = now_epoch
                except Exception as e:
                    db_recovery_backoff.note_failure(e)
            else:
                now_loop = asyncio.get_event_loop().time()
                if now_loop >= next_postgres_heartbeat_pressure_log_at:
                    logger.warning(
                        "Postgres runner heartbeat skipped while PgBouncer pressure "
                        "is active profile=%s reason=%s inflight=%s",
                        runner_profile.profile_code,
                        db_pressure.reason,
                        len(inflight),
                    )
                    next_postgres_heartbeat_pressure_log_at = now_loop + 30.0
        try:
            await publish_runner_resource_heartbeat(
                redis_queue,
                build_runner_resource_heartbeat(
                    runner_id=runner_id,
                    profile_code=runner_profile.profile_code,
                    queue_shards=list(runner_profile.accepted_queue_partitions),
                    capacity=capacity,
                    resource_snapshot=resource_snapshot,
                ),
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

        if db_pressure.paused:
            now_loop = asyncio.get_event_loop().time()
            if now_loop >= next_db_pressure_log_at:
                logger.warning(
                    "Runner claim loop paused by PgBouncer pressure "
                    "profile=%s reason=%s wait_seconds=%s inflight=%s",
                    runner_profile.profile_code,
                    db_pressure.reason,
                    db_pressure.wait_seconds,
                    len(inflight),
                )
                next_db_pressure_log_at = now_loop + 30.0
            await asyncio.sleep(
                max(poll_interval_ms / 1000, min(db_pressure.wait_seconds, 5))
            )
            continue

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
                    scan_limit=playbook_fair_scan_limit,
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
                scan_limit=playbook_fair_scan_limit,
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

        lock_owner_id = f"{runner_id}:{task_id}"
        resource_lease_store = None
        resource_decision = None

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

            if await _repair_misqueued_task_if_needed(task_id, t_data, task_queue):
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

            # Check per-task dependencies.
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

            # Run resource admission before lock and claim.
            playbook_metadata = resolve_installed_playbook_runner_metadata(
                playbook_code
            )
            resource_requirements = resolve_resource_requirements(
                t_data,
                execution_context=lock_ctx,
                playbook_metadata=playbook_metadata,
            )
            resource_lease_store = RedisResourceLeaseStore(task_queue)
            resource_decision = await acquire_task_resource_admission(
                task=t_data,
                requirements=resource_requirements,
                runner_profile=runner_profile,
                capacity=capacity,
                lease_store=resource_lease_store,
                owner_id=lock_owner_id,
                ttl_seconds=lock_ttl_seconds,
            )
            if not resource_decision.allow:
                resource_wait_update = build_resource_wait_task_update(
                    lock_ctx,
                    resource_decision,
                    current_queue_shard=getattr(t_data, "queue_shard", None),
                )
                await asyncio.to_thread(
                    tasks_store.update_task,
                    t_data.id,
                    **resource_wait_update,
                )
                await task_queue.ack_task(task_id)
                continue

            if resource_decision.execution_context_updates:
                lock_ctx = {
                    **lock_ctx,
                    **resource_decision.execution_context_updates,
                }
                await asyncio.to_thread(
                    tasks_store.update_task,
                    t_data.id,
                    execution_context=lock_ctx,
                )

            # Acquire concurrency locks before claim.
            lock_keys = _resolve_lock_keys(
                lock_ctx,
                t_data.pack_id,
                persisted_concurrency_key=getattr(t_data, "concurrency_key", None),
            )
            lock_key = lock_keys[0] if lock_keys else None
            if lock_keys:
                db_conflict = await asyncio.to_thread(
                    tasks_store.has_running_concurrency_conflict,
                    t_data.id,
                    lock_keys,
                )
                if db_conflict:
                    if resource_lease_store and resource_decision:
                        await release_acquired_resource_leases(
                            resource_lease_store,
                            resource_decision.acquired_leases,
                            owner_id=lock_owner_id,
                        )
                    parked_update = _build_parked_task_update(
                        lock_ctx,
                        reason="concurrency_locked",
                        delay_seconds=30,
                        now=_utc_now(),
                        lock_key=lock_key,
                        conflicting_lock_key=lock_key,
                        current_queue_shard=getattr(t_data, "queue_shard", None),
                    )
                    await asyncio.to_thread(
                        tasks_store.update_task,
                        t_data.id,
                        **parked_update,
                    )
                    await task_queue.ack_task(task_id)
                    continue

            if lock_keys:
                acquired_keys: list[str] = []
                conflicting_key: Optional[str] = None
                for candidate_key in lock_keys:
                    acquired = await redis_queue.acquire_lock(
                        candidate_key, lock_owner_id, ttl_seconds=lock_ttl_seconds
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
                    if resource_lease_store and resource_decision:
                        await release_acquired_resource_leases(
                            resource_lease_store,
                            resource_decision.acquired_leases,
                            owner_id=lock_owner_id,
                        )
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

            # Claim only pending rows.
            claimed = await asyncio.to_thread(
                tasks_store.try_claim_task,
                t_data.id,
                runner_id=runner_id,
                concurrency_keys=lock_keys,
            )
            if not claimed:
                db_conflict = False
                if lock_keys:
                    db_conflict = await asyncio.to_thread(
                        tasks_store.has_running_concurrency_conflict,
                        t_data.id,
                        lock_keys,
                    )
                logger.warning(
                    f"[Worker] DB claim failed for Task {task_id}. Ghost pop or duplicated. Acking."
                )
                for held_key in lock_keys:
                    try:
                        await redis_queue.release_lock(held_key, lock_owner_id)
                    except Exception:
                        pass
                if resource_lease_store and resource_decision:
                    await release_acquired_resource_leases(
                        resource_lease_store,
                        resource_decision.acquired_leases,
                        owner_id=lock_owner_id,
                    )
                if db_conflict:
                    parked_update = _build_parked_task_update(
                        lock_ctx,
                        reason="concurrency_locked",
                        delay_seconds=30,
                        now=_utc_now(),
                        lock_key=lock_key,
                        conflicting_lock_key=lock_key,
                        current_queue_shard=getattr(t_data, "queue_shard", None),
                    )
                    await asyncio.to_thread(
                        tasks_store.update_task,
                        t_data.id,
                        **parked_update,
                    )
                await task_queue.ack_task(task_id)
                continue

            # Dispatch execution.
            task_coro = _run_single_task(
                tasks_store,
                runner_id,
                t_data.id,
                redis_queue=task_queue,
                lock_owner_id=lock_owner_id,
            )
            dispatch_task = asyncio.create_task(task_coro)
            setattr(dispatch_task, "_mindscape_pack_id", str(t_data.pack_id or ""))
            inflight.add(dispatch_task)

        except Exception as e:
            if db_recovery_backoff.note_failure(e):
                logger.warning(
                    "Runner task dispatch deferred while PostgreSQL is recovering task_id=%s delay=%ss",
                    task_id,
                    db_recovery_backoff.delay_seconds,
                )
            else:
                logger.warning(
                    f"Runner task dispatch error for {task_id}: {e}", exc_info=True
                )
            if resource_lease_store and resource_decision:
                try:
                    await release_acquired_resource_leases(
                        resource_lease_store,
                        resource_decision.acquired_leases,
                        owner_id=lock_owner_id,
                    )
                except Exception:
                    pass
            # Failsafe in case of dispatch crash
            await (task_queue or redis_queue).nack_task_to_delayed(
                task_id,
                delay_sec=(
                    db_recovery_backoff.delay_seconds
                    if db_recovery_backoff.is_active()
                    else 15
                ),
            )


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
