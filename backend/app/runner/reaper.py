"""Runner reaper facade for stale tasks, Redis bridge repair, and release seams."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from backend.app.models.workspace import Task
from backend.app.services.runner_live_state import RunnerLiveStateStore
from backend.app.services.stores.redis.runner_queue_store import RedisRunnerQueueStore
from backend.app.services.stores.tasks_store import TasksStore
from backend.app.services.task_admission_service import TASK_ADMISSION_SERVICE
from backend.app.services.host_resources.route_identity_projection import (
    build_route_identity_projection,
)
from backend.app.services.host_resources.workspace_quota_admission import (
    decide_workspace_quota_admission_for_task,
)
from backend.app.runner.reaper_bridge import _reap_redis_queues as _reap_redis_queues_impl
from backend.app.runner.reaper_context import (
    _BROWSER_LOCAL_QUEUE_SHARD,
    _browser_peer_frontier_lanes,
    _CONCURRENCY_LOCKED_REASON,
    _DEPENDENCY_HOLD_REASON,
    _RESOURCE_WAIT_REASON,
    _WORKSPACE_ALLOCATION_DISABLED_REASON,
    _WORKSPACE_ALLOCATION_REQUIRED_REASON,
    _WORKSPACE_QUOTA_EXHAUSTED_REASON,
    _WORKSPACE_QUOTA_RELEASE_REASONS,
    _blocked_release_limit,
    _browser_peer_frontier_refill_limit,
    _effective_task_heartbeat_at,
    _emit_run_state_changed_for_task,
    _heartbeat_log_value,
    _host_resource_wait_still_blocked,
    _is_stale_started_task,
    _live_task_heartbeat_at,
    _normalize_task_id,
    _resource_wait_keys_from_context,
    _resource_wait_requirements_from_context,
    _task_heartbeat_at,
    _task_runner_id,
    _workspace_quota_allocation,
    _workspace_quota_int,
    _workspace_quota_payload,
    _workspace_quota_release_key,
    _workspace_quota_task_selectors,
    logger,
)
from backend.app.runner.reaper_release_basic import (
    _release_admission_deferred_tasks as _release_admission_deferred_tasks_impl,
    _release_concurrency_locked_tasks as _release_concurrency_locked_tasks_impl,
    _release_dependency_hold_tasks as _release_dependency_hold_tasks_impl,
    _release_unblocked_cold_tasks as _release_unblocked_cold_tasks_impl,
)
from backend.app.runner.reaper_release_resource_quota import (
    _release_resource_wait_tasks as _release_resource_wait_tasks_impl,
    _release_workspace_quota_tasks as _release_workspace_quota_tasks_impl,
)
from backend.app.runner.reaper_stale_tasks import (
    _reap_stale_running_tasks as _reap_stale_running_tasks_impl,
    _requeue_stale_queued_task,
)
from backend.app.runner.reaper_transport import (
    _async_force_release,
    _async_reconcile_transport_membership as _async_reconcile_transport_membership_impl,
    _browser_lane_key_from_task,
    _force_release_lock,
    _mark_frontier_ready,
    _queued_browser_peer_lanes,
    _queued_transport_task_ids,
    _reconcile_temp_transport_items,
    _recycle_visibility_timeout_item as _recycle_visibility_timeout_item_impl,
    _refill_browser_peer_frontier,
    _resolve_transport_queue_store,
    _scrub_processing_terminal_items,
)
from backend.app.runner.reaper_watchdog import (
    _extract_artifact_semantic_progress_at,
    _latest_watchdog_timestamp,
    _normalize_watchdog_timestamp,
    _request_watchdog_abort_for_no_progress_tasks,
    _resolve_watchdog_progress_updated_at,
    _watchdog_pack_allowlist,
    _watchdog_policy_enabled,
    _watchdog_policy_from_context,
)


async def _async_reconcile_transport_membership(
    redis_queue: RedisRunnerQueueStore,
    *,
    task_id: str,
    queue_shard: Optional[str],
    reenqueue_pending: bool,
) -> None:
    return await _async_reconcile_transport_membership_impl(
        redis_queue,
        task_id=task_id,
        queue_shard=queue_shard,
        reenqueue_pending=reenqueue_pending,
        resolve_transport_queue_store_func=_resolve_transport_queue_store,
    )


async def _recycle_visibility_timeout_item(
    *,
    tasks_store: TasksStore,
    redis_queue: RedisRunnerQueueStore,
    client: Any,
    task_id: str,
    now_dt: datetime,
    stale_limit: datetime,
) -> str:
    return await _recycle_visibility_timeout_item_impl(
        tasks_store=tasks_store,
        redis_queue=redis_queue,
        client=client,
        task_id=task_id,
        now_dt=now_dt,
        stale_limit=stale_limit,
        effective_task_heartbeat_at=_effective_task_heartbeat_at,
        reconcile_transport_membership=_async_reconcile_transport_membership,
    )


def _reap_stale_running_tasks(
    tasks_store: TasksStore,
    runner_id: str,
    redis_queue: Optional[RedisRunnerQueueStore] = None,
    event_loop: Optional[Any] = None,
    live_state_store: Optional[RunnerLiveStateStore] = None,
) -> None:
    """Delegate stale task recovery while preserving the legacy reaper import path.

    Source guard: RunnerLiveStateStore.get_task_heartbeat is consulted before
    the DB heartbeat via _effective_task_heartbeat_at(t, ctx, live_state_store).
    """
    return _reap_stale_running_tasks_impl(
        tasks_store,
        runner_id,
        redis_queue=redis_queue,
        event_loop=event_loop,
        live_state_store=live_state_store,
    )


async def _release_admission_deferred_tasks(
    tasks_store: TasksStore,
    redis_queue: RedisRunnerQueueStore,
    *,
    release_limit: int,
) -> int:
    return await _release_admission_deferred_tasks_impl(
        tasks_store,
        redis_queue,
        release_limit=release_limit,
        admission_service=TASK_ADMISSION_SERVICE,
    )


async def _release_workspace_quota_tasks(
    tasks_store: TasksStore,
    redis_queue: RedisRunnerQueueStore,
    *,
    release_limit: int,
) -> int:
    return await _release_workspace_quota_tasks_impl(
        tasks_store,
        redis_queue,
        release_limit=release_limit,
        workspace_quota_admission_func=decide_workspace_quota_admission_for_task,
    )


async def _release_resource_wait_tasks(
    tasks_store: TasksStore,
    redis_queue: RedisRunnerQueueStore,
    *,
    release_limit: int,
) -> int:
    return await _release_resource_wait_tasks_impl(
        tasks_store,
        redis_queue,
        release_limit=release_limit,
        resource_wait_keys_from_context=_resource_wait_keys_from_context,
        host_resource_wait_still_blocked=_host_resource_wait_still_blocked,
    )


async def _release_dependency_hold_tasks(
    tasks_store: TasksStore,
    redis_queue: RedisRunnerQueueStore,
    *,
    release_limit: int,
) -> int:
    return await _release_dependency_hold_tasks_impl(
        tasks_store,
        redis_queue,
        release_limit=release_limit,
    )


async def _release_unblocked_cold_tasks(
    tasks_store: TasksStore,
    redis_queue: RedisRunnerQueueStore,
    *,
    release_limit: int,
) -> int:
    return await _release_unblocked_cold_tasks_impl(
        tasks_store,
        redis_queue,
        release_limit=release_limit,
    )


async def _release_concurrency_locked_tasks(
    tasks_store: TasksStore,
    redis_queue: RedisRunnerQueueStore,
    *,
    release_limit: int,
) -> int:
    return await _release_concurrency_locked_tasks_impl(
        tasks_store,
        redis_queue,
        release_limit=release_limit,
    )


async def _reap_redis_queues(
    tasks_store: TasksStore,
    redis_queue: RedisRunnerQueueStore,
    *,
    ready_target_override: Optional[int] = None,
    all_queues: Optional[list[RedisRunnerQueueStore]] = None,
) -> None:
    return await _reap_redis_queues_impl(
        tasks_store,
        redis_queue,
        ready_target_override=ready_target_override,
        all_queues=all_queues,
        mark_frontier_ready=_mark_frontier_ready,
        reconcile_temp_transport_items=_reconcile_temp_transport_items,
        scrub_processing_terminal_items=_scrub_processing_terminal_items,
        recycle_visibility_timeout_item=_recycle_visibility_timeout_item,
        release_concurrency_locked_tasks=_release_concurrency_locked_tasks,
        release_dependency_hold_tasks=_release_dependency_hold_tasks,
        release_resource_wait_tasks=_release_resource_wait_tasks,
        release_workspace_quota_tasks=_release_workspace_quota_tasks,
        release_admission_deferred_tasks=_release_admission_deferred_tasks,
        release_unblocked_cold_tasks=_release_unblocked_cold_tasks,
        refill_browser_peer_frontier=_refill_browser_peer_frontier,
        build_route_identity_projection_func=build_route_identity_projection,
    )
