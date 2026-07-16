"""Bounded sync-to-async resource ownership cleanup for the task reaper."""

from __future__ import annotations

import asyncio
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import Optional

from backend.app.models.workspace import Task
from backend.app.runner.reaper_transport import _force_release_lock
from backend.app.services.runner_resources import (
    TaskResourceOwnershipReleaseResult,
    release_task_resource_ownership_from_context,
)
from backend.app.services.stores.redis.runner_queue_store import RedisRunnerQueueStore


REAPER_RESOURCE_RELEASE_TIMEOUT_SECONDS = 5.0


def release_reaped_task_ownership(
    task: Task,
    execution_context: dict,
    *,
    previous_runner_id: Optional[str],
    redis_queue: Optional[RedisRunnerQueueStore],
    event_loop: Optional[asyncio.AbstractEventLoop],
    logger,
) -> Optional[TaskResourceOwnershipReleaseResult]:
    """Release concurrency and exact resource ownership after the DB transition."""

    _force_release_lock(
        execution_context,
        task.pack_id,
        redis_queue,
        persisted_concurrency_key=getattr(task, "concurrency_key", None),
        event_loop=event_loop,
    )

    normalized_runner_id = str(previous_runner_id or "").strip()
    if redis_queue is None or not normalized_runner_id:
        return None
    if event_loop is None or not event_loop.is_running():
        logger.warning(
            "[Reaper] Resource ownership cleanup incomplete task_id=%s "
            "owner=%s reason=no_running_event_loop",
            task.id,
            normalized_runner_id,
        )
        return None

    future = asyncio.run_coroutine_threadsafe(
        release_task_resource_ownership_from_context(
            redis_queue,
            task_id=str(task.id),
            runner_id=normalized_runner_id,
            execution_context=execution_context,
        ),
        event_loop,
    )
    try:
        result = future.result(timeout=REAPER_RESOURCE_RELEASE_TIMEOUT_SECONDS)
    except FutureTimeoutError:
        future.cancel()
        logger.warning(
            "[Reaper] Resource ownership cleanup incomplete task_id=%s "
            "owner=%s reason=timeout timeout_seconds=%s",
            task.id,
            normalized_runner_id,
            REAPER_RESOURCE_RELEASE_TIMEOUT_SECONDS,
        )
        return None
    except Exception as exc:
        logger.warning(
            "[Reaper] Resource ownership cleanup incomplete task_id=%s "
            "owner=%s reason=%s",
            task.id,
            normalized_runner_id,
            exc,
        )
        return None

    if not result.complete:
        logger.warning(
            "[Reaper] Resource ownership cleanup incomplete task_id=%s "
            "owner=%s unreleased=%s node_released=%s "
            "node_owner_mismatch=%s errors=%s",
            task.id,
            result.owner_id,
            list(result.unreleased_lease_keys),
            result.node_reservation_released,
            result.node_reservation_owner_mismatch,
            list(result.errors),
        )
    return result


__all__ = [
    "REAPER_RESOURCE_RELEASE_TIMEOUT_SECONDS",
    "release_reaped_task_ownership",
]
