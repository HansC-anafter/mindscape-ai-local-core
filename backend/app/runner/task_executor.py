"""Runner task executor — subprocess spawn and task lifecycle management."""

import asyncio
import json
import logging
import multiprocessing as mp
import os
import threading
import time
import traceback
from datetime import timedelta
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from backend.app.models.workspace import Task, TaskStatus
from backend.app.services.execution_intent_resolver import (
    ExecutionIntentResolution,
    ExecutionIntentResolver,
)
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.playbook_run_executor import PlaybookRunExecutor
from backend.app.services.runner_topology import (
    resolve_runner_capacity_snapshot,
    resolve_runner_profile_from_env,
    resolve_runtime_dispatch_target,
)
from backend.app.services.runner_resources import (
    RedisResourceLeaseStore,
    release_resource_lease_keys,
    renew_resource_lease_keys,
    resource_lease_keys_from_context,
)
from backend.app.services.runner_live_state import RunnerLiveStateStore
from backend.app.services.stores.tasks_store import TasksStore
from backend.app.services.stores.redis.runner_queue_store import RedisRunnerQueueStore

from backend.app.runner.concurrency import _build_inputs, _resolve_lock_keys
from backend.app.runner.lifecycle_hooks import _invoke_on_fail_hook
from backend.app.runner.resource_pressure import (
    build_runner_resource_snapshot,
    classify_subprocess_resource_failure,
    resource_failure_retry_delay_seconds,
)
from backend.app.runner.utils import _env_int, _utc_now
from backend.app.runner.database_backoff import is_database_recovery_error

logger = logging.getLogger(__name__)

_TERMINAL_SUCCESS_STALE_KEYS = (
    "dependency_hold",
    "error",
    "failed_at",
    "resource_pressure",
    "resource_pressure_source",
    "resource_retry_delay_sec",
    "resource_snapshot",
    "resource_admission",
    "resume_after",
    "runner_resource_leases",
    "runner_reaper",
    "runner_skip_conflict_lock_key",
    "runner_skip_lock_key",
    "runner_skip_reason",
)


def _is_non_retryable_task_error(message: str) -> bool:
    normalized = str(message or "")
    return "Missing required playbook inputs" in normalized


def _resolve_execution_attempt_inputs(
    task: Task,
    task_ctx: Optional[Dict[str, Any]],
) -> tuple[Dict[str, Any], ExecutionIntentResolution]:
    raw_inputs = _build_inputs(task.execution_id or task.id, task_ctx)
    try:
        resolution = ExecutionIntentResolver().resolve(
            task=task,
            execution_context=task_ctx,
            raw_inputs=raw_inputs,
        )
    except Exception:
        logger.warning(
            "Runner execution-intent resolution failed for task %s (playbook=%s); "
            "falling back to raw queued inputs",
            task.id,
            task.pack_id,
            exc_info=True,
        )
        resolution = ExecutionIntentResolution(effective_inputs=dict(raw_inputs))

    effective_inputs = (
        dict(resolution.effective_inputs)
        if isinstance(resolution.effective_inputs, dict)
        else dict(raw_inputs)
    )
    if effective_inputs != raw_inputs:
        logger.info(
            "Runner resolved execution intent for task %s (playbook=%s scope=%s device=%s)",
            task.id,
            task.pack_id,
            resolution.resolved_scope,
            resolution.resolved_device_id,
        )
    return effective_inputs, resolution


def _serialize_runtime_binding(binding: Any) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "dispatch_mode": getattr(binding, "dispatch_mode", None),
        "via": getattr(binding, "via", None),
    }
    for key in (
        "runtime_id",
        "runtime_url",
        "transport",
        "site_key",
        "device_id",
        "binding_scope",
    ):
        value = getattr(binding, key, None)
        if isinstance(value, str) and value.strip():
            payload[key] = value.strip()
    return {key: value for key, value in payload.items() if value}


def _runtime_binding_targets_local_host_runtime(binding_payload: Dict[str, Any]) -> bool:
    binding_scope = str(binding_payload.get("binding_scope") or "").strip().lower()
    if binding_scope == "local":
        return True

    runtime_url = str(binding_payload.get("runtime_url") or "").strip()
    if not runtime_url:
        return False

    try:
        hostname = (urlparse(runtime_url).hostname or "").strip().lower()
    except Exception:
        return False
    return hostname in {"localhost", "127.0.0.1", "::1", "host.docker.internal"}


def _should_force_remote_execution(binding_payload: Dict[str, Any]) -> bool:
    if binding_payload.get("dispatch_mode") != "external_runtime":
        return False
    return not _runtime_binding_targets_local_host_runtime(binding_payload)


def _apply_runtime_binding_to_playbook_task(
    task: Task,
    task_ctx: Optional[Dict[str, Any]],
    inputs: Optional[Dict[str, Any]],
    *,
    profile_id: Optional[str],
) -> tuple[Dict[str, Any], Dict[str, Any], Any]:
    updated_inputs = dict(inputs) if isinstance(inputs, dict) else {}
    updated_ctx = dict(task_ctx) if isinstance(task_ctx, dict) else {}

    runner_profile = resolve_runner_profile_from_env(
        default_max_inflight=_env_int("LOCAL_CORE_RUNNER_MAX_INFLIGHT", 1)
    )
    binding = resolve_runtime_dispatch_target(runner_profile, task)
    binding_payload = _serialize_runtime_binding(binding)

    if not binding_payload:
        return updated_inputs, updated_ctx, binding

    updated_ctx["runtime_binding"] = binding_payload
    updated_inputs.setdefault("runtime_binding", binding_payload)

    runtime_id = binding_payload.get("runtime_id")
    if runtime_id:
        updated_ctx["selected_runtime_id"] = runtime_id
        updated_inputs.setdefault("runtime_id", runtime_id)

    if binding_payload.get("site_key"):
        updated_inputs.setdefault("site_key", binding_payload["site_key"])
    if binding_payload.get("device_id"):
        updated_inputs.setdefault("target_device_id", binding_payload["device_id"])

    if task.task_type == "playbook_execution" and _should_force_remote_execution(
        binding_payload
    ):
        updated_inputs["execution_backend"] = "remote"
        updated_inputs.setdefault("remote_job_type", "playbook")

        capability_code = updated_ctx.get("capability_code")
        if isinstance(capability_code, str) and capability_code.strip():
            updated_inputs.setdefault("remote_capability_code", capability_code.strip())

        remote_request_payload = (
            dict(updated_inputs.get("remote_request_payload"))
            if isinstance(updated_inputs.get("remote_request_payload"), dict)
            else {}
        )
        nested_inputs = (
            dict(remote_request_payload.get("inputs"))
            if isinstance(remote_request_payload.get("inputs"), dict)
            else {}
        )
        for key, value in updated_inputs.items():
            nested_inputs.setdefault(key, value)
        remote_request_payload["inputs"] = nested_inputs
        remote_request_payload.setdefault("playbook_code", task.pack_id)
        if profile_id:
            remote_request_payload.setdefault("profile_id", profile_id)
        remote_request_payload["runtime_binding"] = binding_payload
        if binding_payload.get("device_id"):
            remote_request_payload.setdefault(
                "target_device_id",
                binding_payload["device_id"],
            )
        governance = (
            dict(remote_request_payload.get("_governance"))
            if isinstance(remote_request_payload.get("_governance"), dict)
            else {}
        )
        if binding_payload.get("site_key"):
            governance.setdefault("site_key", binding_payload["site_key"])
        if governance:
            remote_request_payload["_governance"] = governance
        updated_inputs["remote_request_payload"] = remote_request_payload
        updated_ctx["execution_backend_hint"] = "remote"

    return updated_inputs, updated_ctx, binding


def _emit_run_state_changed_for_task(
    task: Task,
    *,
    previous_state: str,
    new_state: str,
    reason: str,
) -> None:
    """Emit a workspace lifecycle event for runner-managed task transitions."""
    try:
        from backend.app.services.playbook_runner import _build_run_state_changed_event

        ctx = task.execution_context if isinstance(task.execution_context, dict) else {}
        inputs = None
        if isinstance(task.params, dict) and task.params:
            inputs = task.params
        elif isinstance(ctx.get("inputs"), dict):
            inputs = ctx.get("inputs")
        elif isinstance(task.params, dict):
            inputs = task.params
        event_inputs = inputs if isinstance(inputs, dict) else {}
        playbook_code = (
            event_inputs.get("playbook_code")
            or (ctx.get("playbook_code") if isinstance(ctx, dict) else None)
            or task.pack_id
            or ""
        )

        event = _build_run_state_changed_event(
            profile_id=(
                getattr(task, "profile_id", None)
                or (ctx.get("profile_id") if isinstance(ctx, dict) else None)
                or "default-user"
            ),
            project_id=task.project_id,
            workspace_id=task.workspace_id,
            execution_id=task.execution_id or str(task.id),
            previous_state=previous_state,
            new_state=new_state,
            reason=reason,
            playbook_code=playbook_code,
            inputs=inputs,
        )
        MindscapeStore().create_event(event)
    except Exception as emit_error:
        logger.warning(
            "Failed to emit %s RUN_STATE_CHANGED event for task %s (%s): %s",
            new_state,
            task.id,
            task.execution_id,
            emit_error,
        )


def _build_runtime_park_update(
    task_ctx: Optional[Dict[str, Any]],
    *,
    blocked_reason: str,
    blocked_payload: Optional[Dict[str, Any]],
    delay_seconds: int,
) -> Dict[str, Any]:
    now = _utc_now()
    next_eligible_at = now + timedelta(seconds=delay_seconds)
    ctx2 = dict(task_ctx) if isinstance(task_ctx, dict) else {}
    ctx2["resume_after"] = next_eligible_at.isoformat()
    ctx2["runner_skip_reason"] = blocked_reason
    ctx2["status"] = "queued"
    if isinstance(blocked_payload, dict) and blocked_payload:
        ctx2["runtime_hold"] = dict(blocked_payload)
    else:
        ctx2.pop("runtime_hold", None)

    return {
        "execution_context": ctx2,
        "status": TaskStatus.PENDING,
        "next_eligible_at": next_eligible_at,
        "blocked_reason": blocked_reason,
        "blocked_payload": blocked_payload or None,
        "frontier_state": "cold",
        "frontier_enqueued_at": None,
        "error": None,
        "completed_at": None,
    }


async def _park_task_after_intent_resolution(
    tasks_store: TasksStore,
    task: Task,
    runner_id: str,
    resolution: ExecutionIntentResolution,
    redis_queue: Optional[RedisRunnerQueueStore] = None,
) -> None:
    blocked_reason = str(resolution.blocked_reason or "runtime_unavailable").strip()
    delay_seconds = _env_int("LOCAL_CORE_RUNNER_RUNTIME_PARK_DELAY_SECONDS", 30)
    latest = tasks_store.get_task(task.id) or task
    latest_ctx = (
        latest.execution_context if isinstance(latest.execution_context, dict) else {}
    )
    park_update = _build_runtime_park_update(
        latest_ctx,
        blocked_reason=blocked_reason,
        blocked_payload=resolution.blocked_payload,
        delay_seconds=delay_seconds,
    )
    tasks_store.update_task(latest.id, **park_update)
    logger.info(
        "Runner parked task %s (playbook=%s reason=%s scope=%s device=%s delay=%ss)",
        latest.id,
        latest.pack_id,
        blocked_reason,
        resolution.resolved_scope,
        resolution.resolved_device_id,
        delay_seconds,
    )
    if redis_queue:
        await redis_queue.ack_task(latest.id)


async def _release_task_locks(
    redis_queue: Optional[RedisRunnerQueueStore],
    lock_keys: list[str],
    lock_owner_id: str,
) -> None:
    if not redis_queue or not lock_keys:
        return
    for held_key in lock_keys:
        try:
            await redis_queue.release_lock(
                lock_key=held_key,
                owner_id=lock_owner_id,
            )
        except Exception:
            pass


async def _release_task_resource_leases(
    redis_queue: Optional[RedisRunnerQueueStore],
    resource_lease_keys: list[str],
    lock_owner_id: str,
) -> None:
    if not redis_queue or not resource_lease_keys:
        return
    try:
        await release_resource_lease_keys(
            RedisResourceLeaseStore(redis_queue),
            resource_lease_keys,
            owner_id=lock_owner_id,
        )
    except Exception:
        pass


def _get_task_control_signal(task: Optional[Task]) -> Optional[Dict[str, str]]:
    """Return a runner control signal derived from task status/context."""
    if not task:
        return {"kind": "missing", "message": "Runner task record missing"}

    if task.status == TaskStatus.CANCELLED_BY_USER:
        return {"kind": "cancelled", "message": task.error or "Cancelled by user"}
    if task.status == TaskStatus.EXPIRED:
        return {"kind": "expired", "message": task.error or "Task expired externally"}

    ctx = task.execution_context if isinstance(task.execution_context, dict) else {}
    watchdog_abort = ctx.get("watchdog_abort")
    if not isinstance(watchdog_abort, dict):
        watchdog_abort = {}
    requested_at = ctx.get("watchdog_abort_requested_at") or watchdog_abort.get(
        "requested_at"
    )
    if requested_at:
        reason = (
            ctx.get("watchdog_abort_reason")
            or watchdog_abort.get("reason")
            or "Watchdog requested abort"
        )
        return {"kind": "watchdog_abort", "message": reason}
    return None


def _initialize_capability_packages_for_runner(*, load_tools: bool = True) -> None:
    try:
        from pathlib import Path

        from backend.app.services.capability_registry import get_registry, load_capabilities

        app_dir = Path(__file__).resolve().parent.parent
        capabilities_dir = (app_dir / "capabilities").resolve()
        load_capabilities(capabilities_dir)
        if load_tools:
            from backend.app.services.capability_tool_loader import load_all_capability_tools

            load_all_capability_tools()

        registry = get_registry()
        logger.info(
            "Runner capability packages loaded: %s capabilities, %s tools, load_tools=%s",
            len(registry.list_capabilities()),
            len(registry.list_tools()),
            load_tools,
        )
    except Exception as e:
        logger.error(f"Runner failed to load capability packages: {e}", exc_info=True)


def _child_execute_playbook(payload: Dict[str, Any]) -> None:
    """
    Run a single playbook or tool execution inside a dedicated process.
    This isolates Playwright/driver hangs that may hold the GIL and would otherwise
    freeze runner heartbeats/lock renew threads.
    """
    os.environ["LOCAL_CORE_RUNNER_PROCESS"] = "1"
    runner_id = str(payload.get("runner_id") or "").strip()
    task_id = str(payload.get("task_id") or "").strip()
    if runner_id:
        os.environ["LOCAL_CORE_RUNNER_ID"] = runner_id
    if task_id:
        os.environ["LOCAL_CORE_TASK_ID"] = task_id
    try:
        eager_tool_load = (
            os.getenv("LOCAL_CORE_RUNNER_CHILD_EAGER_TOOL_LOAD", "")
            .strip()
            .lower()
            in {"1", "true", "yes", "on"}
        )
        _initialize_capability_packages_for_runner(load_tools=eager_tool_load)
    except Exception:
        pass

    task_type = payload.get("task_type", "playbook_execution")
    playbook_code = payload.get("playbook_code")
    profile_id = payload.get("profile_id")
    inputs = payload.get("inputs")
    workspace_id = payload.get("workspace_id")
    project_id = payload.get("project_id")
    result_file = payload.get("_result_file")

    async def _run() -> None:
        if task_type == "tool_execution":
            # Direct tool invocation via UnifiedToolExecutor
            tool_name = payload.get("tool_name") or playbook_code
            from backend.app.services.unified_tool_executor import (
                UnifiedToolExecutor,
            )

            executor = UnifiedToolExecutor()
            result = await executor.execute_tool(
                tool_name=tool_name,
                arguments=inputs or {},
            )
            if not result.success:
                raise RuntimeError(
                    f"Tool execution failed for '{tool_name}': {result.error}"
                )
            if result_file:
                import json as _json

                try:
                    with open(result_file, "w") as f:
                        _json.dump(result.to_dict(), f)
                except Exception:
                    pass
        else:
            # Standard playbook execution path
            executor = PlaybookRunExecutor()
            await executor.execute_playbook_run(
                playbook_code=playbook_code,
                profile_id=profile_id,
                inputs=inputs,
                workspace_id=workspace_id,
                project_id=project_id,
            )

    try:
        asyncio.run(_run())
    except Exception as e:
        if result_file:
            try:
                with open(result_file, "w") as f:
                    json.dump(
                        {
                            "status": "failed",
                            "error": str(e),
                            "exception_type": type(e).__name__,
                            "traceback": traceback.format_exc(),
                        },
                        f,
                    )
            except Exception:
                pass
        raise


def _build_subprocess_failure_message(
    result_file: Optional[str], exitcode: int
) -> str:
    msg = f"Runner subprocess exited non-zero (exitcode={exitcode})"
    if not result_file or not os.path.exists(result_file):
        return msg
    try:
        with open(result_file, "r") as f:
            payload = json.load(f)
    except Exception:
        return msg

    if not isinstance(payload, dict):
        return msg

    detail = payload.get("error") or payload.get("message")
    if isinstance(detail, str) and detail.strip():
        return f"{msg}: {detail.strip()}"
    return msg


def _build_resource_failure_snapshot(*, inflight: int = 1) -> Optional[Dict[str, Any]]:
    try:
        runner_profile = resolve_runner_profile_from_env(
            default_max_inflight=_env_int("LOCAL_CORE_RUNNER_MAX_INFLIGHT", 1)
        )
        capacity = resolve_runner_capacity_snapshot(
            runner_profile,
            inflight=inflight,
            configured_poll_batch_limit=_env_int("LOCAL_CORE_RUNNER_POLL_BATCH_LIMIT", 0),
        )
        return build_runner_resource_snapshot(
            profile_code=runner_profile.profile_code,
            inflight=inflight,
            max_inflight=capacity.max_inflight,
            available_slots=capacity.available_slots,
        )
    except Exception:
        return None


# ---------------------------------------------------------------------------
#  Extracted helpers: deduplicate failure / success task-update patterns
# ---------------------------------------------------------------------------


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
    """Mark a task as FAILED, increment retry_count, and NACK or Deadletter via Redis."""
    max_attempts = _env_int("LOCAL_CORE_RUNNER_MAX_ATTEMPTS", 3)
    try:
        latest = tasks_store.get_task(task_id)
        if latest and latest.status not in (
            TaskStatus.CANCELLED_BY_USER,
            TaskStatus.FAILED,
        ):
            ctxf = (
                latest.execution_context
                if isinstance(latest.execution_context, dict)
                else {}
            )
            ctxf = dict(ctxf)
            resource_wait = bool(resource_pressure_source)
            if resource_wait:
                retry_count = int(ctxf.get("retry_count", 0) or 0)
                ctxf["resource_wait_count"] = int(ctxf.get("resource_wait_count", 0) or 0) + 1
            else:
                retry_count = int(ctxf.get("retry_count", 0) or 0) + 1
                ctxf["retry_count"] = retry_count
            ctxf.pop("resource_admission", None)
            ctxf.pop("runner_resource_leases", None)
            ctxf["error"] = msg
            ctxf["failed_at"] = _utc_now().isoformat()
            if resource_pressure_source:
                ctxf["resource_pressure"] = True
                ctxf["resource_pressure_source"] = resource_pressure_source
                ctxf["resource_retry_delay_sec"] = max(15, int(retry_delay_sec or 15))
                if isinstance(resource_snapshot, dict):
                    ctxf["resource_snapshot"] = resource_snapshot

            non_retryable = _is_non_retryable_task_error(msg)
            is_deadletter = False if resource_wait else (
                non_retryable or retry_count >= max_attempts
            )
            if non_retryable:
                ctxf["non_retryable_failure"] = "missing_required_playbook_inputs"

            # For terminal deadletters, change status to FAILED.
            # Otherwise we keep it as PENDING but defer it to delayed queue.
            new_status = TaskStatus.FAILED if is_deadletter else TaskStatus.PENDING
            ctxf["status"] = "failed" if is_deadletter else "queued"
            ctxf["last_runner_id"] = runner_id
            ctxf.pop("runner_id", None)
            ctxf.pop("heartbeat_at", None)

            # Invoke on_fail hook (best-effort, may create follow-up tasks).
            hook_invoked = False
            if not resource_wait:
                try:
                    hook_invoked = await _invoke_on_fail_hook(ctxf, msg, latest.id)
                except Exception as hook_err:
                    logger.warning(f"on_fail hook error for task {task_id}: {hook_err}")

            if hook_invoked:
                logger.info(f"on_fail hook handled failure for task {task_id}. Skipping native requeue.")
                if redis_queue:
                    try:
                        await redis_queue.ack_task(latest.id)
                    except Exception as e:
                        logger.error(f"Failed to ack task {task_id} after hook invocation: {e}")
                return

            retry_delay_sec = max(15, int(retry_delay_sec or 15))
            next_eligible_at = (
                None
                if is_deadletter
                else _utc_now() + timedelta(seconds=retry_delay_sec)
            )

            # 1. Strict DB write first
            tasks_store.update_task(
                latest.id,
                execution_context=ctxf,
                status=new_status,
                started_at=latest.started_at if is_deadletter else None,
                next_eligible_at=next_eligible_at,
                blocked_reason=None,
                blocked_payload=None,
                frontier_state="done" if is_deadletter else "cold",
                frontier_enqueued_at=None,
                completed_at=_utc_now() if is_deadletter else None,
                error=msg if is_deadletter else None,
                runner_id=None,
                heartbeat_at=None,
            )

            if is_deadletter:
                _emit_run_state_changed_for_task(
                    latest,
                    previous_state="RUNNING",
                    new_state="FAILED",
                    reason="execution_failed",
                )

            # 2. Redis Transport resolution
            if redis_queue:
                if is_deadletter:
                    logger.warning(f"Task {task_id} reached max_attempts ({max_attempts}). Sending to Deadletter.")
                    await redis_queue.move_to_deadletter(task_id)
                    await redis_queue.ack_task(task_id)  # Clean up from processing
                elif resource_wait:
                    logger.warning(
                        "Task %s deferred by browser resource lease wait (wait_count=%s). NACKing to delayed queue.",
                        task_id,
                        ctxf.get("resource_wait_count"),
                    )
                    await redis_queue.nack_task_to_delayed(
                        task_id,
                        delay_sec=retry_delay_sec,
                    )
                else:
                    logger.warning(f"Task {task_id} failed transiently (attempt {retry_count}). NACKing to delayed queue.")
                    await redis_queue.nack_task_to_delayed(
                        task_id,
                        delay_sec=retry_delay_sec,
                    )
    except Exception as e:
        logger.error(f"Failed to mark task {task_id} as failed: {e}", exc_info=True)


async def _mark_task_succeeded(
    tasks_store: TasksStore,
    task_id: str,
    runner_id: str,
    result_file: Optional[str],
    redis_queue: Optional[RedisRunnerQueueStore] = None,
) -> None:
    """Mark a task as SUCCEEDED, reading tool result from IPC temp file."""
    try:
        tool_result = None
        if result_file and os.path.exists(result_file):
            try:
                with open(result_file, "r") as f:
                    tool_result = json.load(f)
            except Exception:
                pass

        latest = tasks_store.get_task(task_id)
        if latest and latest.status not in (
            TaskStatus.CANCELLED_BY_USER,
            TaskStatus.FAILED,
        ):
            ctxs = (
                latest.execution_context
                if isinstance(latest.execution_context, dict)
                else {}
            )
            ctxs = dict(ctxs)
            for key in _TERMINAL_SUCCESS_STALE_KEYS:
                ctxs.pop(key, None)
            ctxs["status"] = "succeeded"
            ctxs["last_runner_id"] = runner_id
            ctxs.pop("runner_id", None)
            ctxs.pop("heartbeat_at", None)
            ctxs["completed_at"] = _utc_now().isoformat()
            update_kwargs = dict(
                execution_context=ctxs,
                status=TaskStatus.SUCCEEDED,
                completed_at=_utc_now(),
                runner_id=None,
                heartbeat_at=None,
            )
            if tool_result is not None:
                update_kwargs["result"] = tool_result
                try:
                    from backend.app.services.object_action_closure_wiring import (
                        close_object_action_from_execution_result,
                    )

                    closure_inputs = (
                        ctxs.get("inputs")
                        if isinstance(ctxs.get("inputs"), dict)
                        else latest.params
                    )
                    closure_result = close_object_action_from_execution_result(
                        workspace_id=latest.workspace_id,
                        execution_id=latest.execution_id or latest.id,
                        inputs=closure_inputs if isinstance(closure_inputs, dict) else {},
                        execution_result=tool_result,
                    )
                    if closure_result:
                        ctxs["object_action_closure"] = closure_result
                        update_kwargs["execution_context"] = ctxs
                except Exception:
                    logger.exception(
                        "Failed to run AOL object action closure for task %s",
                        latest.id,
                    )
            
            # 1. DB Write MUST precede Ack
            tasks_store.update_task(
                latest.id,
                **update_kwargs,
            )
            _emit_run_state_changed_for_task(
                latest,
                previous_state="RUNNING",
                new_state="DONE",
                reason="execution_completed",
            )
            
        # 2. Redis Ack MUST ALWAYS happen even if DB state was skipped
        if redis_queue:
            await redis_queue.ack_task(task_id)
    except Exception as e:
        logger.error(f"Failed to mark task {task_id} as succeeded: {e}", exc_info=True)


# ---------------------------------------------------------------------------
#  Main task execution orchestrator
# ---------------------------------------------------------------------------


async def _run_single_task(
    tasks_store: TasksStore,
    runner_id: str,
    task_id: str,
    redis_queue: Optional[RedisRunnerQueueStore] = None,
    lock_owner_id: Optional[str] = None,
) -> None:
    task = tasks_store.get_task(task_id)
    if not task:
        if redis_queue:
            await redis_queue.ack_task(task_id)
        return

    if task.status == TaskStatus.CANCELLED_BY_USER:
        if redis_queue:
            await redis_queue.ack_task(task_id)
        return

    os.environ["LOCAL_CORE_RUNNER_PROCESS"] = "1"
    inflight_files = set()

    ctx = task.execution_context if isinstance(task.execution_context, dict) else {}
    lock_keys = _resolve_lock_keys(
        ctx,
        task.pack_id,
        persisted_concurrency_key=getattr(task, "concurrency_key", None),
    )
    resource_lease_keys = resource_lease_keys_from_context(ctx)
    resource_lease_store = (
        RedisResourceLeaseStore(redis_queue) if redis_queue and resource_lease_keys else None
    )
    lock_owner_id = lock_owner_id or runner_id
    lock_ttl_seconds = _env_int("LOCAL_CORE_RUNNER_LOCK_TTL_SECONDS", 120)
    stop_event = threading.Event()
    hb_thread: Optional[threading.Thread] = None
    lock_renew_thread = None
    proc = None
    result_file = None
    exec_task = None
    control_task = None
    timeout_task = None
    task_finalized = False
    
    # Lock has ALREADY been acquired by runner/worker.py in the Redis store.
    # We clear any leftover UI lock status metadata as this task is executing now.
    try:
        ctx2 = dict(ctx)
        if (
            ctx2.get("runner_skip_reason") 
            or ctx2.get("runner_skip_owner") 
            or ctx2.get("resume_after")
            or ctx2.get("dependency_hold")
            or ctx2.get("watchdog_abort_requested_at")
            or ctx2.get("watchdog_abort_reason")
            or ctx2.get("watchdog_abort")
        ):
            ctx2.pop("runner_skip_reason", None)
            ctx2.pop("runner_skip_owner", None)
            ctx2.pop("runner_skip_lock_key", None)
            ctx2.pop("resume_after", None)
            ctx2.pop("dependency_hold", None)
            ctx2.pop("watchdog_abort_requested_at", None)
            ctx2.pop("watchdog_abort_reason", None)
            ctx2.pop("watchdog_abort", None)
            tasks_store.update_task(task.id, execution_context=ctx2)
            ctx = ctx2
    except Exception:
        pass
        
    inputs, _intent_resolution = _resolve_execution_attempt_inputs(task, ctx)

    if _intent_resolution.park_task:
        try:
            await _park_task_after_intent_resolution(
                tasks_store,
                task,
                runner_id,
                _intent_resolution,
                redis_queue,
            )
        finally:
            await _release_task_locks(redis_queue, lock_keys, lock_owner_id)
            await _release_task_resource_leases(
                redis_queue,
                resource_lease_keys,
                lock_owner_id,
            )
        return

    resolved_profile_id = (
        getattr(task, "profile_id", None)
        or (ctx.get("profile_id") if isinstance(ctx, dict) else None)
        or "default-user"
    )
    inputs, ctx, runtime_binding = _apply_runtime_binding_to_playbook_task(
        task,
        ctx,
        inputs,
        profile_id=resolved_profile_id,
    )
    runtime_binding_payload = _serialize_runtime_binding(runtime_binding)
    if runtime_binding_payload:
        try:
            tasks_store.update_task(task.id, execution_context=ctx)
        except Exception:
            logger.warning(
                "Failed to persist runtime binding for task %s",
                task.id,
                exc_info=True,
            )
        logger.info(
            "Runner resolved runtime binding task=%s playbook=%s dispatch_mode=%s runtime_id=%s site_key=%s device_id=%s via=%s",
            task.id,
            task.pack_id,
            runtime_binding_payload.get("dispatch_mode"),
            runtime_binding_payload.get("runtime_id"),
            runtime_binding_payload.get("site_key"),
            runtime_binding_payload.get("device_id"),
            runtime_binding_payload.get("via"),
        )

    hb_interval_ms = _env_int("LOCAL_CORE_RUNNER_HEARTBEAT_INTERVAL_MS", 15000)
    heartbeat_ttl_seconds = max(60, int((hb_interval_ms / 1000.0) * 4))
    runner_live_state = RunnerLiveStateStore()
    # Heartbeat/lock renew must keep ticking even if the main async task blocks (e.g. Playwright hanging).

    # Capture the main event loop so daemon threads can schedule coroutines on it
    # instead of calling asyncio.run() (which creates a NEW loop and conflicts
    # with the Redis client's asyncio.Lock bound to the main loop).
    main_loop = asyncio.get_running_loop()

    # proc reference will be set before heartbeat starts checking it
    proc_ref = [None]  # Use list for mutable reference in closure
    trace_heartbeat = bool(ctx.get("trace_runner_heartbeat"))

    def _heartbeat_thread() -> None:
        interval_s = max(1.0, hb_interval_ms / 1000.0)
        beat_seq = 0
        next_db_recovery_log_at = 0.0
        while not stop_event.is_set():
            beat_seq += 1
            # Check if subprocess is still running - stop heartbeat if subprocess died
            try:
                p = proc_ref[0]
                if p is not None and not p.is_alive():
                    logger.warning(
                        "Runner heartbeat stopping: subprocess died for task %s "
                        "(playbook=%s beat_seq=%s exitcode=%s)",
                        task.id,
                        task.pack_id,
                        beat_seq,
                        p.exitcode,
                    )
                    break
            except Exception as e:
                logger.error(f"Error checking subprocess alive status in heartbeat thread: {e}", exc_info=True)
            try:
                hb_started = time.monotonic()
                if trace_heartbeat and beat_seq <= 3:
                    logger.warning(
                        "Runner heartbeat begin task_id=%s playbook=%s beat_seq=%s phase=abort_check",
                        task.id,
                        task.pack_id,
                        beat_seq,
                    )
                should_abort = tasks_store.update_task_heartbeat(
                    task.id,
                    runner_id=runner_id,
                )
                hb_db_elapsed_ms = int((time.monotonic() - hb_started) * 1000)
                if (trace_heartbeat and beat_seq <= 3) or hb_db_elapsed_ms >= 2000:
                    log_fn = logger.warning if hb_db_elapsed_ms >= 2000 or trace_heartbeat else logger.info
                    log_fn(
                        "Runner heartbeat abort_check done task_id=%s playbook=%s beat_seq=%s elapsed_ms=%s should_abort=%s",
                        task.id,
                        task.pack_id,
                        beat_seq,
                        hb_db_elapsed_ms,
                        should_abort,
                    )
                if should_abort:
                    stop_event.set()
                    break
                live_started = time.monotonic()
                live_ok = runner_live_state.renew_task_heartbeat(
                    task_id=task.id,
                    runner_id=runner_id,
                    workspace_id=task.workspace_id,
                    execution_id=task.execution_id,
                    playbook_code=task.pack_id,
                    queue_shard=getattr(task, "queue_shard", None),
                    ttl_seconds=heartbeat_ttl_seconds,
                )
                hb_live_elapsed_ms = int((time.monotonic() - live_started) * 1000)
                if (trace_heartbeat and beat_seq <= 3) or hb_live_elapsed_ms >= 2000 or not live_ok:
                    log_fn = (
                        logger.warning
                        if hb_live_elapsed_ms >= 2000 or not live_ok or trace_heartbeat
                        else logger.info
                    )
                    log_fn(
                        "Runner heartbeat live_state done task_id=%s playbook=%s beat_seq=%s elapsed_ms=%s ok=%s",
                        task.id,
                        task.pack_id,
                        beat_seq,
                        hb_live_elapsed_ms,
                        live_ok,
                    )
                # Touch Redis queue visibility timeout to prevent ghosting by Reaper
                if redis_queue:
                    redis_started = time.monotonic()
                    if trace_heartbeat and beat_seq <= 3:
                        logger.warning(
                            "Runner heartbeat begin task_id=%s playbook=%s beat_seq=%s phase=touch_visibility",
                            task.id,
                            task.pack_id,
                            beat_seq,
                        )
                    fut = asyncio.run_coroutine_threadsafe(
                        redis_queue.touch_visibility_timeout(task.id, added_time_sec=180),
                        main_loop,
                    )
                    touch_ok = fut.result(timeout=10)
                    hb_redis_elapsed_ms = int((time.monotonic() - redis_started) * 1000)
                    if (trace_heartbeat and beat_seq <= 3) or hb_redis_elapsed_ms >= 2000 or not touch_ok:
                        log_fn = (
                            logger.warning
                            if hb_redis_elapsed_ms >= 2000 or not touch_ok or trace_heartbeat
                            else logger.info
                        )
                        log_fn(
                            "Runner heartbeat touch_visibility done task_id=%s playbook=%s beat_seq=%s elapsed_ms=%s ok=%s",
                            task.id,
                            task.pack_id,
                            beat_seq,
                            hb_redis_elapsed_ms,
                            touch_ok,
                        )
            except Exception as e:
                if is_database_recovery_error(e):
                    now_monotonic = time.monotonic()
                    if now_monotonic >= next_db_recovery_log_at:
                        logger.warning(
                            "Runner heartbeat deferred while PostgreSQL is recovering task_id=%s playbook=%s beat_seq=%s",
                            task.id,
                            task.pack_id,
                            beat_seq,
                        )
                        next_db_recovery_log_at = now_monotonic + 30.0
                else:
                    logger.error(
                        "Error updating heartbeat in heartbeat thread for task %s "
                        "(playbook=%s beat_seq=%s): %s",
                        task.id,
                        task.pack_id,
                        beat_seq,
                        e,
                        exc_info=True,
                    )
            stop_event.wait(interval_s)

    hb_thread = threading.Thread(target=_heartbeat_thread, daemon=True)
    hb_thread.start()

    if redis_queue and (lock_keys or resource_lease_keys):

        def _renew_thread() -> None:
            interval_s = max(5.0, hb_interval_ms / 1000.0)
            while not stop_event.is_set():
                try:
                    for held_key in lock_keys:
                        fut = asyncio.run_coroutine_threadsafe(
                            redis_queue.renew_lock(
                                lock_key=held_key,
                                owner_id=lock_owner_id,
                                ttl_seconds=lock_ttl_seconds,
                            ),
                            main_loop,
                        )
                        renew_ok = fut.result(timeout=10)
                        if not renew_ok:
                            logger.warning(
                                "Runner concurrency lock renew returned false task_id=%s playbook=%s lock_key=%s owner_id=%s",
                                task.id,
                                task.pack_id,
                                held_key,
                                lock_owner_id,
                            )
                    if resource_lease_store and resource_lease_keys:
                        fut = asyncio.run_coroutine_threadsafe(
                            renew_resource_lease_keys(
                                resource_lease_store,
                                resource_lease_keys,
                                owner_id=lock_owner_id,
                                ttl_seconds=lock_ttl_seconds,
                            ),
                            main_loop,
                        )
                        fut.result(timeout=10)
                except Exception as e:
                    logger.warning(
                        "Runner lease renew failed task_id=%s playbook=%s owner_id=%s: %s",
                        task.id,
                        task.pack_id,
                        lock_owner_id,
                        e,
                        exc_info=True,
                    )
                stop_event.wait(interval_s)

        lock_renew_thread = threading.Thread(target=_renew_thread, daemon=True)
        lock_renew_thread.start()

    try:
        cancel_poll_ms = _env_int("LOCAL_CORE_RUNNER_CANCEL_POLL_INTERVAL_MS", 2000)
        # Dynamic timeout: playbook-declared > env var > default 3600s
        ctx_timeout = ctx.get("runner_timeout_seconds")
        if isinstance(ctx_timeout, (int, float)) and ctx_timeout > 0:
            max_ceiling = _env_int("LOCAL_CORE_RUNNER_MAX_TIMEOUT_SECONDS", 43200)
            task_timeout_seconds = min(int(ctx_timeout), max_ceiling)
            logger.info(
                f"Runner using spec-declared timeout={task_timeout_seconds}s "
                f"for task {task.id} (ceiling={max_ceiling}s)"
            )
        else:
            task_timeout_seconds = _env_int(
                "LOCAL_CORE_RUNNER_TASK_TIMEOUT_SECONDS", 3600
            )
        ctx_mp = mp.get_context("spawn")

        async def _wait_for_control_signal() -> Optional[Dict[str, str]]:
            while True:
                try:
                    latest = await asyncio.to_thread(tasks_store.get_task, task.id)
                    signal = _get_task_control_signal(latest)
                    if signal:
                        return signal
                except Exception:
                    pass
                await asyncio.sleep(cancel_poll_ms / 1000)

        import tempfile

        result_fd, result_file = tempfile.mkstemp(
            prefix=f"runner_result_{task.id}_", suffix=".json"
        )
        os.close(result_fd)

        payload = {
            "runner_id": runner_id,
            "task_id": task.id,
            "playbook_code": task.pack_id,
            "task_type": task.task_type or "playbook_execution",
            "tool_name": (ctx.get("tool_name") if isinstance(ctx, dict) else None),
            "profile_id": resolved_profile_id,
            "inputs": inputs,
            "workspace_id": task.workspace_id,
            "project_id": task.project_id,
            "_result_file": result_file,
        }

        proc = ctx_mp.Process(
            target=_child_execute_playbook, args=(payload,), daemon=True
        )
        logger.info(
            "Runner subprocess starting task_id=%s playbook=%s",
            task.id,
            task.pack_id,
        )
        try:
            proc.start()
        except BaseException as start_exc:
            logger.exception(
                "Runner subprocess start failed task_id=%s playbook=%s: %s",
                task.id,
                task.pack_id,
                start_exc,
            )
            raise
        if trace_heartbeat:
            logger.warning(
                "Runner subprocess started task_id=%s playbook=%s pid=%s",
                task.id,
                task.pack_id,
                proc.pid,
            )
        else:
            logger.info(
                "Runner subprocess started task_id=%s playbook=%s pid=%s",
                task.id,
                task.pack_id,
                proc.pid,
            )
        # Update proc reference for heartbeat thread to monitor
        proc_ref[0] = proc

        async def _wait_for_proc() -> int:
            while proc.is_alive():
                await asyncio.sleep(0.5)
            # Treat None exitcode as error (-1) to catch zombie/abnormal termination
            exitcode = proc.exitcode
            if trace_heartbeat:
                logger.warning(
                    "Runner subprocess exited task_id=%s playbook=%s pid=%s exitcode=%s",
                    task.id,
                    task.pack_id,
                    proc.pid,
                    exitcode,
                )
            else:
                logger.info(
                    "Runner subprocess exited task_id=%s playbook=%s pid=%s exitcode=%s",
                    task.id,
                    task.pack_id,
                    proc.pid,
                    exitcode,
                )
            if exitcode is None:
                logger.warning(
                    f"Runner subprocess exitcode is None (zombie?) for task {task.id}"
                )
                return -1
            return int(exitcode)

        async def _wait_for_timeout() -> bool:
            # Returns True if timeout fired.
            await asyncio.sleep(task_timeout_seconds)
            return True

        exec_task = asyncio.create_task(_wait_for_proc())
        control_task = asyncio.create_task(_wait_for_control_signal())
        timeout_task = asyncio.create_task(_wait_for_timeout())

        done, pending = await asyncio.wait(
            {exec_task, control_task, timeout_task}, return_when=asyncio.FIRST_COMPLETED
        )
        done_labels = []
        if exec_task in done:
            done_labels.append("exec")
        if control_task in done:
            done_labels.append("control")
        if timeout_task in done:
            done_labels.append("timeout")
        logger.info(
            "Runner wait completed task_id=%s playbook=%s done=%s proc_alive=%s",
            task.id,
            task.pack_id,
            ",".join(done_labels) or "unknown",
            proc.is_alive() if proc else None,
        )

        if control_task in done:
            signal = control_task.result() or {}
            logger.warning(
                "Runner control signal received task_id=%s playbook=%s signal=%s",
                task.id,
                task.pack_id,
                signal,
            )
            try:
                if proc.is_alive():
                    proc.terminate()
            except Exception:
                pass
            exec_task.cancel()
            timeout_task.cancel()
            try:
                await exec_task
            except BaseException:
                pass
            try:
                await timeout_task
            except BaseException:
                pass
            signal_kind = signal.get("kind")
            latest = None
            try:
                latest = await asyncio.to_thread(tasks_store.get_task, task.id)
            except Exception:
                latest = None

            if signal_kind == "cancelled":
                try:
                    if latest and latest.status == TaskStatus.CANCELLED_BY_USER:
                        ctxc = (
                            latest.execution_context
                            if isinstance(latest.execution_context, dict)
                            else {}
                        )
                        ctxc = dict(ctxc)
                        ctxc["status"] = "cancelled"
                        ctxc["cancelled_at"] = _utc_now().isoformat()
                        ctxc["last_runner_id"] = runner_id
                        ctxc.pop("runner_id", None)
                        ctxc.pop("heartbeat_at", None)
                        tasks_store.update_task(
                            latest.id,
                            execution_context=ctxc,
                            status=TaskStatus.CANCELLED_BY_USER,
                            completed_at=_utc_now(),
                            error=latest.error or "Cancelled by user",
                            runner_id=None,
                            heartbeat_at=None,
                        )
                except Exception:
                    pass
                if redis_queue:
                    try:
                        await redis_queue.ack_task(task.id)
                    except Exception:
                        pass
                task_finalized = True
            elif latest and latest.status in (TaskStatus.FAILED, TaskStatus.EXPIRED):
                _emit_run_state_changed_for_task(
                    latest,
                    previous_state="RUNNING",
                    new_state="FAILED",
                    reason=latest.error or "execution_failed",
                )
                if redis_queue:
                    try:
                        await redis_queue.ack_task(task.id)
                    except Exception:
                        pass
                task_finalized = True
            else:
                msg = signal.get("message") or "Runner control signal requested abort"
                await _mark_task_failed(tasks_store, task.id, runner_id, msg, redis_queue)
                task_finalized = True
        elif timeout_task in done and timeout_task.result() is True:
            # --- Hard timeout ---
            try:
                if proc.is_alive():
                    proc.terminate()
            except Exception:
                pass
            exec_task.cancel()
            control_task.cancel()
            try:
                await exec_task
            except BaseException:
                pass
            try:
                await control_task
            except BaseException:
                pass
            msg = (
                f"Runner task timeout ({task_timeout_seconds}s) - subprocess terminated"
            )
            await _mark_task_failed(tasks_store, task.id, runner_id, msg, redis_queue)
            task_finalized = True
        else:
            # --- Process finished ---
            control_task.cancel()
            timeout_task.cancel()
            try:
                await control_task
            except BaseException:
                pass
            try:
                await timeout_task
            except BaseException:
                pass
            exitcode = await exec_task
            if exitcode != 0:
                msg = _build_subprocess_failure_message(result_file, exitcode)
                resource_source = classify_subprocess_resource_failure(exitcode, msg)
                resource_snapshot = None
                retry_delay_sec = 15
                if resource_source:
                    retry_delay_sec = resource_failure_retry_delay_seconds()
                    resource_snapshot = _build_resource_failure_snapshot(inflight=1)
                await _mark_task_failed(
                    tasks_store,
                    task.id,
                    runner_id,
                    msg,
                    redis_queue,
                    retry_delay_sec=retry_delay_sec,
                    resource_pressure_source=resource_source,
                    resource_snapshot=resource_snapshot,
                )
            else:
                await _mark_task_succeeded(tasks_store, task.id, runner_id, result_file, redis_queue)
            task_finalized = True
    finally:
        if proc and proc.is_alive() and not task_finalized:
            logger.warning(
                "Runner orchestration reached cleanup before subprocess exit; "
                "waiting for child task_id=%s playbook=%s pid=%s timeout=%ss",
                task.id,
                task.pack_id,
                proc.pid,
                task_timeout_seconds,
            )
            try:
                cleanup_deadline = time.monotonic() + max(1, int(task_timeout_seconds))
                while proc.is_alive() and time.monotonic() < cleanup_deadline:
                    await asyncio.sleep(0.5)
                if not proc.is_alive():
                    exitcode = proc.exitcode
                    if exitcode is None:
                        exitcode = -1
                    if int(exitcode) == 0:
                        await _mark_task_succeeded(
                            tasks_store,
                            task.id,
                            runner_id,
                            result_file,
                            redis_queue,
                        )
                    else:
                        msg = _build_subprocess_failure_message(result_file, int(exitcode))
                        resource_source = classify_subprocess_resource_failure(
                            int(exitcode), msg
                        )
                        resource_snapshot = None
                        retry_delay_sec = 15
                        if resource_source:
                            retry_delay_sec = resource_failure_retry_delay_seconds()
                            resource_snapshot = _build_resource_failure_snapshot(
                                inflight=1
                            )
                        await _mark_task_failed(
                            tasks_store,
                            task.id,
                            runner_id,
                            msg,
                            redis_queue,
                            retry_delay_sec=retry_delay_sec,
                            resource_pressure_source=resource_source,
                            resource_snapshot=resource_snapshot,
                        )
                    task_finalized = True
            except BaseException:
                logger.exception(
                    "Runner cleanup wait failed for task %s", task.id
                )
            finally:
                for pending_task in (exec_task, control_task, timeout_task):
                    if pending_task and not pending_task.done():
                        pending_task.cancel()
        try:
            if result_file and os.path.exists(result_file):
                os.unlink(result_file)
        except Exception:
            pass
        stop_event.set()
        # Explicitly join subprocess to prevent zombie accumulation
        try:
            if proc:
                proc.join(timeout=5.0)
                if proc.is_alive():
                    logger.warning(
                        f"Runner subprocess still alive after join, killing task {task.id}"
                    )
                    proc.kill()
                    proc.join(timeout=1.0)
                    latest = None
                    try:
                        latest = tasks_store.get_task(task.id)
                    except Exception:
                        latest = None
                    terminal_statuses = {
                        TaskStatus.SUCCEEDED,
                        TaskStatus.FAILED,
                        TaskStatus.CANCELLED_BY_USER,
                        TaskStatus.EXPIRED,
                    }
                    if not latest or latest.status not in terminal_statuses:
                        await _mark_task_failed(
                            tasks_store, task.id, runner_id,
                            f"Runner subprocess killed after join timeout (pid={proc.pid})",
                            redis_queue
                        )
        except Exception as e:
            logger.warning(f"Runner subprocess cleanup error for task {task.id}: {e}")
        if hb_thread:
            try:
                hb_thread.join(timeout=1.0)
            except Exception:
                pass
        try:
            runner_live_state.clear_task_heartbeat(
                task_id=task.id,
                runner_id=runner_id,
            )
        except Exception:
            pass
        if lock_renew_thread:
            try:
                lock_renew_thread.join(timeout=1.0)
            except Exception:
                pass
        # Release lock
        ctx = task.execution_context if isinstance(task.execution_context, dict) else {}
        lock_keys = _resolve_lock_keys(
            ctx,
            task.pack_id,
            persisted_concurrency_key=getattr(task, "concurrency_key", None),
        )
        await _release_task_locks(redis_queue, lock_keys, lock_owner_id)
        await _release_task_resource_leases(
            redis_queue,
            resource_lease_keys,
            lock_owner_id,
        )
