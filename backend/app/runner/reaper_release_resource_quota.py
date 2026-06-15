"""Host resource and workspace quota release helpers."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any, Callable

from backend.app.services.stores.tasks_store import TasksStore
from backend.app.services.stores.redis.runner_queue_store import RedisRunnerQueueStore
from backend.app.services.host_resources.workspace_quota_admission import (
    decide_workspace_quota_admission_for_task,
)
from backend.app.runner.reaper_context import (
    _RESOURCE_WAIT_REASON,
    _WORKSPACE_QUOTA_EXHAUSTED_REASON,
    _WORKSPACE_QUOTA_RELEASE_REASONS,
    _host_resource_wait_still_blocked,
    _resource_wait_keys_from_context,
    _workspace_quota_allocation,
    _workspace_quota_int,
    _workspace_quota_payload,
    _workspace_quota_release_key,
    _workspace_quota_task_selectors,
    logger,
)
from backend.app.runner.utils import _env_int, _utc_now

async def _release_workspace_quota_tasks(
    tasks_store: TasksStore,
    redis_queue: RedisRunnerQueueStore,
    *,
    release_limit: int,
    workspace_quota_admission_func: Callable[[Any], Any] = decide_workspace_quota_admission_for_task,
) -> int:
    if release_limit <= 0:
        return 0

    list_due_workspace_quota_tasks = getattr(
        tasks_store,
        "list_due_workspace_quota_tasks",
        None,
    )
    if not list_due_workspace_quota_tasks:
        return 0

    due_tasks = await asyncio.to_thread(
        list_due_workspace_quota_tasks,
        queue_shard=redis_queue.pack_id,
        limit=max(release_limit * 4, release_limit),
    )
    if not due_tasks:
        return 0

    client = await redis_queue._get_client()
    if not client:
        return 0

    count_ready_workspace_quota_tasks = getattr(
        tasks_store,
        "count_ready_workspace_quota_tasks",
        None,
    )
    try_release_workspace_quota_task = getattr(
        tasks_store,
        "try_release_workspace_quota_task",
        None,
    )
    now = _utc_now()
    blocked_next_eligible_at = now + timedelta(
        seconds=max(
            1,
            _env_int("LOCAL_CORE_WORKSPACE_QUOTA_RELEASE_BACKOFF_SECONDS", 10),
        )
    )
    released_task_ids: list[str] = []
    released_by_allocation: dict[str, int] = {}
    ready_count_by_allocation: dict[str, int] = {}

    for task in due_tasks:
        if len(released_task_ids) >= release_limit:
            break
        if getattr(task, "blocked_reason", None) not in _WORKSPACE_QUOTA_RELEASE_REASONS:
            continue

        try:
            decision = await asyncio.to_thread(
                workspace_quota_admission_func,
                task,
            )
            payload = _workspace_quota_payload(decision)
            allocation = _workspace_quota_allocation(decision, payload)
            allocation_key = _workspace_quota_release_key(task, allocation)
            max_parallel_task_claims = max(
                1,
                _workspace_quota_int(
                    getattr(decision, "max_parallel_task_claims", None)
                    or payload.get("max_parallel_task_claims"),
                    default=1,
                ),
            )
            active_count = max(
                0,
                _workspace_quota_int(
                    getattr(decision, "active_count", None)
                    or payload.get("active_count"),
                    default=0,
                ),
            )
            selectors = _workspace_quota_task_selectors(allocation)
            atomic_release = callable(try_release_workspace_quota_task)

            if not atomic_release and allocation_key not in ready_count_by_allocation:
                ready_count = 0
                if callable(count_ready_workspace_quota_tasks):
                    ready_count = await asyncio.to_thread(
                        count_ready_workspace_quota_tasks,
                        workspace_id=str(getattr(task, "workspace_id", "") or ""),
                        queue_shard=str(
                            getattr(task, "queue_shard", "")
                            or redis_queue.pack_id
                        ),
                        selectors=selectors,
                    )
                ready_count_by_allocation[allocation_key] = max(0, int(ready_count or 0))

            reserved_count = (
                active_count
                + ready_count_by_allocation.get(allocation_key, 0)
                + released_by_allocation.get(allocation_key, 0)
            )
            quota_available = bool(getattr(decision, "allow", False)) and (
                atomic_release or reserved_count < max_parallel_task_claims
            )
            if not quota_available:
                blocked_payload = dict(payload)
                blocked_payload["ready_pending_count"] = ready_count_by_allocation.get(
                    allocation_key,
                    0,
                )
                blocked_payload["released_in_loop"] = released_by_allocation.get(
                    allocation_key,
                    0,
                )
                await asyncio.to_thread(
                    tasks_store.update_task,
                    task.id,
                    next_eligible_at=blocked_next_eligible_at,
                    blocked_reason=(
                        _WORKSPACE_QUOTA_EXHAUSTED_REASON
                        if bool(getattr(decision, "allow", False))
                        else (
                            str(getattr(decision, "reason", "") or "").strip()
                            or _WORKSPACE_QUOTA_EXHAUSTED_REASON
                        )
                    ),
                    blocked_payload=blocked_payload,
                    frontier_state="cold",
                    frontier_enqueued_at=None,
                    return_updated=False,
                )
                continue

            raw_ctx = task.execution_context
            update_kwargs = dict(
                next_eligible_at=now,
                blocked_reason=None,
                blocked_payload=None,
                queue_shard=getattr(task, "queue_shard", None) or redis_queue.pack_id,
                frontier_state="ready",
                frontier_enqueued_at=now,
            )
            if isinstance(raw_ctx, dict):
                ctx2 = dict(raw_ctx)
                ctx2.pop("workspace_quota_admission", None)
                ctx2.pop("runner_claim_admission", None)
                ctx2.pop("resume_after", None)
                update_kwargs["execution_context"] = ctx2
            if atomic_release:
                task_selector = str(
                    getattr(task, "pack_id", None)
                    or update_kwargs.get("execution_context", {}).get("playbook_code")
                    or getattr(task, "task_type", "")
                    or ""
                ).strip()
                released = await asyncio.to_thread(
                    try_release_workspace_quota_task,
                    task.id,
                    workspace_id=str(getattr(task, "workspace_id", "") or ""),
                    queue_shard=str(
                        getattr(task, "queue_shard", "") or redis_queue.pack_id
                    ),
                    selectors=selectors,
                    task_selector=task_selector,
                    allocation_key=allocation_key,
                    max_parallel_task_claims=max_parallel_task_claims,
                    blocked_reasons=list(_WORKSPACE_QUOTA_RELEASE_REASONS),
                    execution_context=update_kwargs.get("execution_context"),
                    now=now,
                )
                if not released:
                    blocked_payload = dict(payload)
                    blocked_payload["atomic_release"] = "reserved_capacity_unavailable"
                    await asyncio.to_thread(
                        tasks_store.update_task,
                        task.id,
                        next_eligible_at=blocked_next_eligible_at,
                        blocked_reason=_WORKSPACE_QUOTA_EXHAUSTED_REASON,
                        blocked_payload=blocked_payload,
                        frontier_state="cold",
                        frontier_enqueued_at=None,
                        return_updated=False,
                    )
                    continue
            else:
                await asyncio.to_thread(
                    tasks_store.update_task,
                    task.id,
                    return_updated=False,
                    **update_kwargs,
                )
            released_task_ids.append(task.id)
            released_by_allocation[allocation_key] = (
                released_by_allocation.get(allocation_key, 0) + 1
            )
        except Exception as exc:
            logger.warning(
                "[Bridge] Failed to release workspace quota task %s on shard %s: %s",
                getattr(task, "id", None),
                redis_queue.pack_id,
                exc,
            )

    if not released_task_ids:
        return 0

    try:
        pipe = client.pipeline()
        for task_id in released_task_ids:
            pipe.rpush(redis_queue.q_pending, task_id)
        await pipe.execute()
    except Exception as exc:
        logger.warning(
            "[Bridge] Failed to enqueue %d workspace quota task(s) for shard %s: %s",
            len(released_task_ids),
            redis_queue.pack_id,
            exc,
        )
        return 0

    logger.warning(
        "[Bridge] Released %d workspace quota task(s) on shard %s.",
        len(released_task_ids),
        redis_queue.pack_id,
    )
    return len(released_task_ids)

async def _release_resource_wait_tasks(
    tasks_store: TasksStore,
    redis_queue: RedisRunnerQueueStore,
    *,
    release_limit: int,
    resource_wait_keys_from_context: Callable[[dict[str, Any]], list[str]] = _resource_wait_keys_from_context,
    host_resource_wait_still_blocked: Callable[[dict[str, Any]], Any] = _host_resource_wait_still_blocked,
) -> int:
    if release_limit <= 0:
        return 0

    list_due_resource_wait_tasks = getattr(
        tasks_store,
        "list_due_resource_wait_tasks",
        None,
    )
    if not list_due_resource_wait_tasks:
        return 0

    due_tasks = await asyncio.to_thread(
        list_due_resource_wait_tasks,
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
    released_resource_keys: set[str] = set()

    for task in due_tasks:
        if len(released_task_ids) >= release_limit:
            break
        if getattr(task, "blocked_reason", None) != _RESOURCE_WAIT_REASON:
            continue

        raw_ctx = task.execution_context
        ctx = raw_ctx if isinstance(raw_ctx, dict) else {}
        resource_keys = resource_wait_keys_from_context(ctx)
        if resource_keys and any(
            resource_key in released_resource_keys for resource_key in resource_keys
        ):
            continue
        still_blocked = host_resource_wait_still_blocked(ctx)
        if still_blocked is not None:
            next_eligible_at = now + timedelta(
                seconds=max(5, _env_int("LOCAL_CORE_HOST_RESOURCE_WAIT_BACKOFF_SECONDS", 30))
            )
            blocked_payload = {
                "policy": _RESOURCE_WAIT_REASON,
                "reason": getattr(still_blocked, "reason", None) or "host_resource_still_blocked",
                "defer_until": next_eligible_at.isoformat(),
                "evaluated_at": now.isoformat(),
                "host_decision": getattr(still_blocked, "decision", "defer"),
                "host_advisor": getattr(still_blocked, "payload", {}) or {},
            }
            ctx2 = dict(ctx)
            admission = dict(ctx2.get("resource_admission") or {})
            admission["state"] = "waiting"
            admission["reason"] = blocked_payload["reason"]
            admission["defer_until"] = next_eligible_at.isoformat()
            ctx2["resource_admission"] = admission
            ctx2["resume_after"] = next_eligible_at.isoformat()
            try:
                await asyncio.to_thread(
                    tasks_store.update_task,
                    task.id,
                    execution_context=ctx2,
                    next_eligible_at=next_eligible_at,
                    blocked_reason=_RESOURCE_WAIT_REASON,
                    blocked_payload=blocked_payload,
                    frontier_state="cold",
                    frontier_enqueued_at=None,
                    return_updated=False,
                )
            except Exception as exc:
                logger.warning(
                    "[Bridge] Failed to extend resource-wait task %s on shard %s: %s",
                    getattr(task, "id", None),
                    redis_queue.pack_id,
                    exc,
                )
            continue

        try:
            update_kwargs = dict(
                next_eligible_at=now,
                blocked_reason=None,
                blocked_payload=None,
                queue_shard=getattr(task, "queue_shard", None) or redis_queue.pack_id,
                frontier_state="ready",
                frontier_enqueued_at=now,
            )
            if isinstance(raw_ctx, dict):
                ctx2 = dict(raw_ctx)
                ctx2.pop("resource_admission", None)
                ctx2.pop("runner_resource_leases", None)
                ctx2.pop("resume_after", None)
                update_kwargs["execution_context"] = ctx2
            await asyncio.to_thread(
                tasks_store.update_task,
                task.id,
                return_updated=False,
                **update_kwargs,
            )
            released_task_ids.append(task.id)
            released_resource_keys.update(resource_keys)
        except Exception as exc:
            logger.warning(
                "[Bridge] Failed to release resource-wait task %s on shard %s: %s",
                getattr(task, "id", None),
                redis_queue.pack_id,
                exc,
            )

    if not released_task_ids:
        return 0

    try:
        pipe = client.pipeline()
        for task_id in released_task_ids:
            pipe.rpush(redis_queue.q_pending, task_id)
        await pipe.execute()
    except Exception as exc:
        logger.warning(
            "[Bridge] Failed to enqueue %d resource-wait task(s) for shard %s: %s",
            len(released_task_ids),
            redis_queue.pack_id,
            exc,
        )
        return 0

    logger.warning(
        "[Bridge] Released %d due resource-wait task(s) on shard %s.",
        len(released_task_ids),
        redis_queue.pack_id,
    )
    return len(released_task_ids)
