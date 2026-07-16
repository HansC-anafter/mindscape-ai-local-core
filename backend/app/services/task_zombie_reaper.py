"""Facade for zombie terminal transitions and exact resource cleanup."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
from typing import Any, Awaitable, Callable, Optional

from backend.app.models.workspace import Task
from backend.app.services.runner_resources import (
    release_task_resource_ownership_from_context,
    reservation_from_context,
    resource_lease_keys_from_context,
)
from backend.app.services.stores.redis.runner_queue_store import (
    RedisRunnerQueueStore,
)
from backend.app.services.stores.tasks_store import TasksStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ZombieTaskReapResult:
    task_ids: tuple[str, ...]
    released_task_ids: tuple[str, ...]
    skipped_task_ids: tuple[str, ...]
    incomplete_task_ids: tuple[str, ...]

    @property
    def cleanup_complete(self) -> bool:
        return not self.incomplete_task_ids


async def reap_zombie_tasks_with_resource_cleanup(
    *,
    tasks_store: Optional[TasksStore] = None,
    redis_queue: Optional[RedisRunnerQueueStore] = None,
    heartbeat_ttl_minutes: int = 10,
    no_heartbeat_ttl_minutes: int = 30,
    release_func: Callable[..., Awaitable[Any]] = (
        release_task_resource_ownership_from_context
    ),
) -> ZombieTaskReapResult:
    """End zombie DB owners, then release their persisted exact resources."""

    resolved_store = tasks_store or TasksStore()
    resolved_queue = redis_queue or RedisRunnerQueueStore(
        pack_id="zombie_resource_cleanup"
    )
    reaped_tasks: list[Task] = []

    def _capture_reaped_task(task: Task) -> None:
        reaped_tasks.append(task)

    task_ids = await asyncio.to_thread(
        resolved_store.reap_zombie_tasks,
        heartbeat_ttl_minutes=heartbeat_ttl_minutes,
        no_heartbeat_ttl_minutes=no_heartbeat_ttl_minutes,
        on_reaped=_capture_reaped_task,
    )

    released_task_ids: list[str] = []
    skipped_task_ids: list[str] = []
    incomplete_task_ids: list[str] = []
    for task in reaped_tasks:
        task_id = str(task.id)
        context = (
            task.execution_context
            if isinstance(task.execution_context, dict)
            else {}
        )
        lease_keys = resource_lease_keys_from_context(context)
        reservation = reservation_from_context(context)
        if not lease_keys and reservation is None:
            skipped_task_ids.append(task_id)
            continue

        runner_id = str(
            getattr(task, "runner_id", None) or context.get("runner_id") or ""
        ).strip()
        if not runner_id:
            incomplete_task_ids.append(task_id)
            logger.warning(
                "Zombie resource cleanup incomplete task_id=%s "
                "reason=missing_persisted_runner_id",
                task_id,
            )
            continue

        try:
            result = await release_func(
                resolved_queue,
                task_id=task_id,
                runner_id=runner_id,
                execution_context=context,
            )
        except Exception as exc:
            incomplete_task_ids.append(task_id)
            logger.warning(
                "Zombie resource cleanup incomplete task_id=%s owner=%s "
                "reason=%s",
                task_id,
                runner_id,
                exc,
            )
            continue

        if bool(getattr(result, "complete", False)):
            released_task_ids.append(task_id)
        else:
            incomplete_task_ids.append(task_id)
            logger.warning(
                "Zombie resource cleanup incomplete task_id=%s owner=%s",
                task_id,
                runner_id,
            )

    return ZombieTaskReapResult(
        task_ids=tuple(str(task_id) for task_id in task_ids),
        released_task_ids=tuple(released_task_ids),
        skipped_task_ids=tuple(skipped_task_ids),
        incomplete_task_ids=tuple(incomplete_task_ids),
    )


__all__ = [
    "ZombieTaskReapResult",
    "reap_zombie_tasks_with_resource_cleanup",
]
