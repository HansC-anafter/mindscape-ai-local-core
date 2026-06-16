"""Runner task executor facade."""

import asyncio
import multiprocessing as mp
from typing import Any, Dict, Optional

from backend.app.models.workspace import Task
from backend.app.services.execution_intent_resolver import ExecutionIntentResolution
from backend.app.services.runner_topology import (
    resolve_runner_capacity_snapshot,
    resolve_runner_profile_from_env,
    resolve_runtime_dispatch_target,
)
from backend.app.services.stores.redis.runner_queue_store import RedisRunnerQueueStore
from backend.app.services.stores.tasks_store import TasksStore

from backend.app.runner.resource_pressure import build_runner_resource_snapshot
from backend.app.runner.task_executor_child import (
    _build_subprocess_failure_message,
    _child_execute_playbook as _child_execute_playbook_impl,
    _initialize_capability_packages_for_runner,
)
from backend.app.runner.task_executor_completion import (
    _build_resource_failure_snapshot as _build_resource_failure_snapshot_impl,
    _mark_task_failed as _mark_task_failed_impl,
    _mark_task_succeeded as _mark_task_succeeded_impl,
)
from backend.app.runner.task_executor_controls import (
    _get_task_control_signal,
    _release_task_locks,
    _release_task_resource_leases,
)
from backend.app.runner.task_executor_events import _emit_run_state_changed_for_task
from backend.app.runner.task_executor_intent import (
    _apply_runtime_binding_to_playbook_task,
    _build_runtime_park_update,
    _is_non_retryable_task_error,
    _park_task_after_intent_resolution,
    _resolve_execution_attempt_inputs,
    _runtime_binding_targets_local_host_runtime,
    _serialize_runtime_binding,
    _should_force_remote_execution,
)
from backend.app.runner.task_executor_runtime import (
    TaskExecutorHooks,
    _run_single_task_impl,
)
from backend.app.runner.utils import _utc_now


def _child_execute_playbook(payload: Dict[str, Any]) -> None:
    return _child_execute_playbook_impl(
        payload,
        initialize_capability_packages_for_runner=_initialize_capability_packages_for_runner,
    )


def _build_resource_failure_snapshot(*, inflight: int = 1) -> Optional[Dict[str, Any]]:
    return _build_resource_failure_snapshot_impl(
        inflight=inflight,
        build_runner_resource_snapshot_fn=build_runner_resource_snapshot,
    )


async def _mark_task_failed(
    tasks_store: TasksStore,
    task_id: str,
    runner_id: str,
    msg: str,
    redis_queue: Optional[RedisRunnerQueueStore] = None,
    *,
    retry_delay_sec: int = 15,
    resource_pressure_source: Optional[str] = None,
    resource_snapshot: Optional[Dict[str, Any]] = None,
) -> None:
    await _mark_task_failed_impl(
        tasks_store,
        task_id,
        runner_id,
        msg,
        redis_queue,
        retry_delay_sec=retry_delay_sec,
        resource_pressure_source=resource_pressure_source,
        resource_snapshot=resource_snapshot,
        emit_run_state_changed_for_task=_emit_run_state_changed_for_task,
        is_non_retryable_task_error=_is_non_retryable_task_error,
    )


async def _mark_task_succeeded(
    tasks_store: TasksStore,
    task_id: str,
    runner_id: str,
    result_file: Optional[str],
    redis_queue: Optional[RedisRunnerQueueStore] = None,
) -> None:
    await _mark_task_succeeded_impl(
        tasks_store,
        task_id,
        runner_id,
        result_file,
        redis_queue,
        emit_run_state_changed_for_task=_emit_run_state_changed_for_task,
    )


def _build_hooks() -> TaskExecutorHooks:
    return TaskExecutorHooks(
        asyncio_module=asyncio,
        mp_module=mp,
        resolve_execution_attempt_inputs=_resolve_execution_attempt_inputs,
        park_task_after_intent_resolution=_park_task_after_intent_resolution,
        release_task_locks=_release_task_locks,
        release_task_resource_leases=_release_task_resource_leases,
        get_task_control_signal=_get_task_control_signal,
        apply_runtime_binding_to_playbook_task=_apply_runtime_binding_to_playbook_task,
        serialize_runtime_binding=_serialize_runtime_binding,
        child_execute_playbook=_child_execute_playbook,
        build_subprocess_failure_message=_build_subprocess_failure_message,
        build_resource_failure_snapshot=_build_resource_failure_snapshot,
        mark_task_failed=_mark_task_failed,
        mark_task_succeeded=_mark_task_succeeded,
        emit_run_state_changed_for_task=_emit_run_state_changed_for_task,
        utc_now=_utc_now,
    )


async def _run_single_task(
    tasks_store: TasksStore,
    runner_id: str,
    task_id: str,
    redis_queue: Optional[RedisRunnerQueueStore] = None,
    lock_owner_id: Optional[str] = None,
) -> None:
    await _run_single_task_impl(
        tasks_store,
        runner_id,
        task_id,
        redis_queue,
        lock_owner_id,
        _build_hooks(),
    )


__all__ = [
    "ExecutionIntentResolution",
    "Task",
    "TaskExecutorHooks",
    "_apply_runtime_binding_to_playbook_task",
    "_build_resource_failure_snapshot",
    "_build_runtime_park_update",
    "_build_subprocess_failure_message",
    "_child_execute_playbook",
    "_emit_run_state_changed_for_task",
    "_get_task_control_signal",
    "_initialize_capability_packages_for_runner",
    "_is_non_retryable_task_error",
    "_mark_task_failed",
    "_mark_task_succeeded",
    "_park_task_after_intent_resolution",
    "_release_task_locks",
    "_release_task_resource_leases",
    "_resolve_execution_attempt_inputs",
    "_runtime_binding_targets_local_host_runtime",
    "_run_single_task",
    "_serialize_runtime_binding",
    "_should_force_remote_execution",
    "asyncio",
    "build_runner_resource_snapshot",
    "mp",
    "resolve_runner_capacity_snapshot",
    "resolve_runner_profile_from_env",
    "resolve_runtime_dispatch_target",
]
