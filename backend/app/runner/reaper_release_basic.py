"""Admission, dependency, cold-frontier, and concurrency release helpers."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from backend.app.models.workspace import TaskStatus
from backend.app.services.stores.tasks_store import TasksStore
from backend.app.services.stores.redis.runner_queue_store import RedisRunnerQueueStore
from backend.app.services.task_admission_service import (
    ADMISSION_DEFERRED_REASON,
    TASK_ADMISSION_SERVICE,
)
from backend.app.runner.concurrency import _resolve_lock_keys
from backend.app.runner.reference_concurrency_repair import (
    normalize_reference_analysis_concurrency,
)
from backend.app.runner.reaper_context import (
    _CONCURRENCY_LOCKED_REASON,
    _DEPENDENCY_HOLD_REASON,
    logger,
)
from backend.app.runner.utils import _utc_now

async def _release_admission_deferred_tasks(
    tasks_store: TasksStore,
    redis_queue: RedisRunnerQueueStore,
    *,
    release_limit: int,
    admission_service: Any = TASK_ADMISSION_SERVICE,
) -> int:
    if release_limit <= 0:
        return 0

    list_due_release_candidates = getattr(
        tasks_store,
        "list_due_admission_deferred_release_candidates",
        tasks_store.list_due_admission_deferred_tasks,
    )
    due_tasks = await asyncio.to_thread(
        list_due_release_candidates,
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

    for task in due_tasks:
        if len(released_task_ids) >= release_limit:
            break

        try:
            decision = await asyncio.to_thread(
                admission_service.evaluate_on_release,
                tasks_store,
                task,
            )
            if decision.allow:
                await asyncio.to_thread(
                    tasks_store.update_task,
                    task.id,
                    next_eligible_at=now,
                    blocked_reason=None,
                    blocked_payload=None,
                    queue_shard=decision.queue_shard or redis_queue.pack_id,
                    frontier_state="ready",
                    frontier_enqueued_at=now,
                    return_updated=False,
                )
                released_task_ids.append(task.id)
                continue

            await asyncio.to_thread(
                tasks_store.update_task,
                task.id,
                next_eligible_at=decision.next_eligible_at,
                blocked_reason=ADMISSION_DEFERRED_REASON,
                blocked_payload=decision.blocked_payload,
                queue_shard=decision.queue_shard or redis_queue.pack_id,
                frontier_state="cold",
                frontier_enqueued_at=None,
                return_updated=False,
            )
        except Exception as exc:
            logger.warning(
                "[Admission] Failed to evaluate deferred task %s on shard %s: %s",
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
            "[Admission] Failed to enqueue %d released task(s) for shard %s: %s",
            len(released_task_ids),
            redis_queue.pack_id,
            exc,
        )

    return len(released_task_ids)

async def _release_dependency_hold_tasks(
    tasks_store: TasksStore,
    redis_queue: RedisRunnerQueueStore,
    *,
    release_limit: int,
) -> int:
    if release_limit <= 0:
        return 0

    list_due_dependency_hold_tasks = getattr(
        tasks_store,
        "list_due_dependency_hold_tasks",
        None,
    )
    if not list_due_dependency_hold_tasks:
        return 0

    due_tasks = await asyncio.to_thread(
        list_due_dependency_hold_tasks,
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

    for task in due_tasks:
        if len(released_task_ids) >= release_limit:
            break
        if getattr(task, "blocked_reason", None) != _DEPENDENCY_HOLD_REASON:
            continue

        try:
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
                ctx2.pop("dependency_hold", None)
                ctx2.pop("resume_after", None)
                update_kwargs["execution_context"] = ctx2
            await asyncio.to_thread(
                tasks_store.update_task,
                task.id,
                **update_kwargs,
            )
            released_task_ids.append(task.id)
        except Exception as exc:
            logger.warning(
                "[Bridge] Failed to release dependency-held task %s on shard %s: %s",
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
            "[Bridge] Failed to enqueue %d dependency-held task(s) for shard %s: %s",
            len(released_task_ids),
            redis_queue.pack_id,
            exc,
        )
        return 0

    logger.warning(
        "[Bridge] Released %d due dependency-held task(s) on shard %s.",
        len(released_task_ids),
        redis_queue.pack_id,
    )
    return len(released_task_ids)

async def _release_unblocked_cold_tasks(
    tasks_store: TasksStore,
    redis_queue: RedisRunnerQueueStore,
    *,
    release_limit: int,
) -> int:
    if release_limit <= 0:
        return 0

    list_due_unblocked_cold_tasks = getattr(
        tasks_store,
        "list_due_unblocked_cold_tasks",
        None,
    )
    if not list_due_unblocked_cold_tasks:
        return 0

    due_tasks = await asyncio.to_thread(
        list_due_unblocked_cold_tasks,
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

    for task in due_tasks:
        if len(released_task_ids) >= release_limit:
            break
        if getattr(task, "blocked_reason", None):
            continue

        try:
            await asyncio.to_thread(
                tasks_store.update_task,
                task.id,
                next_eligible_at=now,
                blocked_reason=None,
                blocked_payload=None,
                queue_shard=getattr(task, "queue_shard", None) or redis_queue.pack_id,
                frontier_state="ready",
                frontier_enqueued_at=now,
                return_updated=False,
            )
            released_task_ids.append(task.id)
        except Exception as exc:
            logger.warning(
                "[Bridge] Failed to release cold pending task %s on shard %s: %s",
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
            "[Bridge] Failed to enqueue %d cold pending task(s) for shard %s: %s",
            len(released_task_ids),
            redis_queue.pack_id,
            exc,
        )
        return 0

    logger.warning(
        "[Bridge] Released %d unblocked cold task(s) on shard %s.",
        len(released_task_ids),
        redis_queue.pack_id,
    )
    return len(released_task_ids)

async def _release_concurrency_locked_tasks(
    tasks_store: TasksStore,
    redis_queue: RedisRunnerQueueStore,
    *,
    release_limit: int,
) -> int:
    if release_limit <= 0:
        return 0

    list_due_locked_tasks = getattr(
        tasks_store,
        "list_due_concurrency_locked_tasks",
        None,
    )
    if not list_due_locked_tasks:
        return 0

    due_tasks = await asyncio.to_thread(
        list_due_locked_tasks,
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
    released_lock_keys: set[str] = set()

    for task in due_tasks:
        if len(released_task_ids) >= release_limit:
            break
        if getattr(task, "blocked_reason", None) != _CONCURRENCY_LOCKED_REASON:
            continue

        raw_ctx = task.execution_context
        ctx = raw_ctx if isinstance(raw_ctx, dict) else {}
        pack_id = str(getattr(task, "pack_id", "") or "")
        repaired_ctx, repaired_concurrency_key = normalize_reference_analysis_concurrency(
            pack_id=pack_id,
            ctx=ctx,
        )
        if isinstance(raw_ctx, dict):
            ctx = repaired_ctx
        effective_concurrency_key = (
            repaired_concurrency_key or getattr(task, "concurrency_key", None)
        )
        lock_keys = _resolve_lock_keys(
            ctx,
            pack_id,
            persisted_concurrency_key=effective_concurrency_key,
        )
        if lock_keys and any(lock_key in released_lock_keys for lock_key in lock_keys):
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
                ctx2 = dict(ctx)
                ctx2.pop("runner_skip_reason", None)
                ctx2.pop("runner_skip_lock_key", None)
                ctx2.pop("runner_skip_conflict_lock_key", None)
                ctx2.pop("resume_after", None)
                update_kwargs["execution_context"] = ctx2
            if repaired_concurrency_key:
                update_kwargs["concurrency_key"] = repaired_concurrency_key
            await asyncio.to_thread(
                tasks_store.update_task,
                task.id,
                return_updated=False,
                **update_kwargs,
            )
            released_task_ids.append(task.id)
            released_lock_keys.update(lock_keys)
        except Exception as exc:
            logger.warning(
                "[Bridge] Failed to release concurrency-locked task %s on shard %s: %s",
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
            "[Bridge] Failed to enqueue %d concurrency-locked task(s) for shard %s: %s",
            len(released_task_ids),
            redis_queue.pack_id,
            exc,
        )
        return 0

    logger.warning(
        "[Bridge] Released %d due concurrency-locked task(s) on shard %s.",
        len(released_task_ids),
        redis_queue.pack_id,
    )
    return len(released_task_ids)
