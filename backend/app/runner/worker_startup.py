"""Runner worker startup reconciliation helpers."""

import asyncio
import logging
import os
from typing import Iterable, Optional

from backend.app.models.workspace import TaskStatus
from backend.app.services.runner_resources import list_active_runner_resource_heartbeats
from backend.app.services.runner_topology import (
    resolve_runner_profile_from_env,
    runner_profile_can_claim_task,
)
from backend.app.services.stores.redis.runner_queue_store import RedisRunnerQueueStore
from backend.app.services.stores.tasks_store import TasksStore
from backend.app.services.host_resources.route_identity_projection import (
    build_route_identity_projection,
)
from backend.app.runner.utils import _env_int
from backend.app.runner.reference_concurrency_repair import (
    normalize_reference_analysis_concurrency,
)
from backend.app.runner.worker_transport import (
    _collect_transport_members,
    _split_ready_target,
)
from backend.app.runner.resource_failure_policy import is_resource_block_reason

logger = logging.getLogger("backend.app.runner.worker")

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
        except Exception as exc:
            logger.warning("Runner resource heartbeat read failed: %s", exc)
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
                pack_id = getattr(t, "pack_id", None) or ctx.get("playbook_code") or ""
                ctx2, concurrency_key = normalize_reference_analysis_concurrency(
                    pack_id=pack_id,
                    ctx=ctx2,
                )
                update_kwargs = {
                    "execution_context": ctx2,
                    "status": TaskStatus.PENDING,
                    "frontier_state": "ready",
                    "started_at": None,
                    "blocked_reason": None,
                    "queue_shard": getattr(t, "queue_shard", None),
                    "runner_id": None,
                    "heartbeat_at": None,
                }
                if concurrency_key:
                    update_kwargs["concurrency_key"] = concurrency_key
                tasks_store.update_task(
                    t.id,
                    **update_kwargs,
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
            if frontier_state in {"running", "cold"} and not is_resource_block_reason(
                getattr(t, "blocked_reason", None)
            ):
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

            if update_kwargs:
                pack_id = getattr(t, "pack_id", None) or ctx.get("playbook_code") or ""
                ctx2, concurrency_key = normalize_reference_analysis_concurrency(
                    pack_id=pack_id,
                    ctx=ctx2,
                )
                if concurrency_key:
                    update_kwargs["concurrency_key"] = concurrency_key
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
                if hasattr(queue_store, "q_temp"):
                    pipe.lrem(queue_store.q_temp, 0, task_id)
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
