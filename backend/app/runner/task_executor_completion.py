"""Task executor terminal update helpers."""

import json
import logging
import os
from datetime import timedelta
from typing import Any, Callable, Dict, Optional

from backend.app.models.workspace import Task, TaskStatus
from backend.app.services.runner_topology import (
    resolve_runner_capacity_snapshot,
    resolve_runner_profile_from_env,
)
from backend.app.services.stores.redis.runner_queue_store import RedisRunnerQueueStore
from backend.app.services.stores.tasks_store import TasksStore

from backend.app.runner.lifecycle_hooks import _invoke_on_fail_hook
from backend.app.runner.resource_pressure import build_runner_resource_snapshot
from backend.app.runner.resource_failure_policy import decide_resource_failure
from backend.app.services.runner_resources import NODE_BUDGET_CONTEXT_KEY
from backend.app.runner.utils import _env_int, _utc_now

logger = logging.getLogger(__name__)

_TERMINAL_SUCCESS_STALE_KEYS = (
    "dependency_hold",
    "error",
    "failed_at",
    "resource_pressure",
    "resource_pressure_source",
    "resource_retry_delay_sec",
    "resource_snapshot",
    "resource_block",
    "resource_admission",
    "resume_after",
    "runner_resource_leases",
    NODE_BUDGET_CONTEXT_KEY,
    "runner_reaper",
    "runner_skip_conflict_lock_key",
    "runner_skip_lock_key",
    "runner_skip_reason",
)


def _build_resource_failure_snapshot(
    *,
    inflight: int = 1,
    build_runner_resource_snapshot_fn: Callable[..., Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    try:
        runner_profile = resolve_runner_profile_from_env(
            default_max_inflight=_env_int("LOCAL_CORE_RUNNER_MAX_INFLIGHT", 1)
        )
        capacity = resolve_runner_capacity_snapshot(
            runner_profile,
            inflight=inflight,
            configured_poll_batch_limit=_env_int("LOCAL_CORE_RUNNER_POLL_BATCH_LIMIT", 0),
        )
        return build_runner_resource_snapshot_fn(
            profile_code=runner_profile.profile_code,
            inflight=inflight,
            max_inflight=capacity.max_inflight,
            available_slots=capacity.available_slots,
        )
    except Exception:
        return None


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
    emit_run_state_changed_for_task: Callable[..., None],
    is_non_retryable_task_error: Callable[[str], bool],
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
            admission_context = (
                dict(ctxf.get("resource_admission") or {})
                if isinstance(ctxf.get("resource_admission"), dict)
                else {}
            )
            resource_decision = decide_resource_failure(
                resource_pressure_source,
                resource_contract_available=bool(
                    admission_context.get("node_policy_fingerprint")
                    and admission_context.get("resource_profile_fingerprint")
                ),
            )
            resource_wait = resource_decision.action == "resource_wait"
            resource_block = resource_decision.action == "resource_block"
            if resource_wait or resource_block:
                retry_count = int(ctxf.get("retry_count", 0) or 0)
                counter_key = (
                    "resource_wait_count" if resource_wait else "resource_block_count"
                )
                ctxf[counter_key] = int(ctxf.get(counter_key, 0) or 0) + 1
            else:
                retry_count = int(ctxf.get("retry_count", 0) or 0) + 1
                ctxf["retry_count"] = retry_count
            ctxf.pop("resource_admission", None)
            ctxf.pop("runner_resource_leases", None)
            ctxf.pop(NODE_BUDGET_CONTEXT_KEY, None)
            ctxf["error"] = msg
            ctxf["failed_at"] = _utc_now().isoformat()
            if resource_pressure_source:
                ctxf["resource_pressure"] = True
                ctxf["resource_pressure_source"] = resource_pressure_source
                ctxf["resource_retry_delay_sec"] = max(15, int(retry_delay_sec or 15))
                if isinstance(resource_snapshot, dict):
                    ctxf["resource_snapshot"] = resource_snapshot

            non_retryable = is_non_retryable_task_error(msg)
            is_deadletter = False if (resource_wait or resource_block) else (
                non_retryable or retry_count >= max_attempts
            )
            if non_retryable:
                ctxf["non_retryable_failure"] = "missing_required_playbook_inputs"

            new_status = TaskStatus.FAILED if is_deadletter else TaskStatus.PENDING
            ctxf["status"] = "failed" if is_deadletter else "queued"
            ctxf["last_runner_id"] = runner_id
            ctxf.pop("runner_id", None)
            ctxf.pop("heartbeat_at", None)

            hook_invoked = False
            if not resource_wait and not resource_block:
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
            blocked_reason = None
            blocked_payload = None
            if resource_block:
                blocked_reason = resource_decision.blocked_reason
                next_eligible_at = _utc_now()
                resource_block_payload = {
                    "reason": blocked_reason,
                    "source": resource_pressure_source,
                    "blocked_at": _utc_now().isoformat(),
                    "node_policy_fingerprint": admission_context.get(
                        "node_policy_fingerprint"
                    ),
                    "resource_profile_fingerprint": admission_context.get(
                        "resource_profile_fingerprint"
                    ),
                    "requested_memory_bytes": admission_context.get(
                        "requested_memory_bytes"
                    ),
                    "memory_reservation_source": admission_context.get(
                        "memory_reservation_source"
                    ),
                    "resource_snapshot": resource_snapshot,
                }
                ctxf["resource_block"] = resource_block_payload
                ctxf["status"] = "blocked_resource"
                blocked_payload = resource_block_payload
            elif resource_wait:
                blocked_reason = "resource_wait"
                blocked_payload = {
                    "reason": resource_pressure_source,
                    "defer_until": next_eligible_at.isoformat(),
                }

            tasks_store.update_task(
                latest.id,
                execution_context=ctxf,
                status=new_status,
                started_at=getattr(latest, "started_at", None) if is_deadletter else None,
                next_eligible_at=next_eligible_at,
                blocked_reason=blocked_reason,
                blocked_payload=blocked_payload,
                frontier_state="done" if is_deadletter else "cold",
                frontier_enqueued_at=None,
                completed_at=_utc_now() if is_deadletter else None,
                error=msg if is_deadletter else None,
                runner_id=None,
                heartbeat_at=None,
            )

            if is_deadletter:
                emit_run_state_changed_for_task(
                    latest,
                    previous_state="RUNNING",
                    new_state="FAILED",
                    reason="execution_failed",
                )

            if redis_queue:
                if is_deadletter:
                    logger.warning(f"Task {task_id} reached max_attempts ({max_attempts}). Sending to Deadletter.")
                    await redis_queue.move_to_deadletter(task_id)
                    await redis_queue.ack_task(task_id)
                elif resource_block:
                    logger.warning(
                        "Task %s preserved in resource block reason=%s; ACKing current queue item without delayed/deadletter enqueue.",
                        task_id,
                        blocked_reason,
                    )
                    await redis_queue.ack_task(task_id)
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
    *,
    emit_run_state_changed_for_task: Callable[..., None],
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
                    from backend.app.services.knowledge_projection.retrievable.source_triggers import (
                        committed_source_trigger_authority,
                    )

                    with committed_source_trigger_authority(
                        actor_user_id=str(
                            ctxs.get("profile_id")
                            or latest.params.get("actor_user_id")
                            or ""
                        ),
                        active_group_id=str(
                            (
                                ctxs.get("execution_admission_snapshot")
                                if isinstance(
                                    ctxs.get(
                                        "execution_admission_snapshot"
                                    ),
                                    dict,
                                )
                                else {}
                            ).get("active_group_id")
                            or ""
                        )
                        or None,
                    ):
                        closure_result = close_object_action_from_execution_result(
                            workspace_id=latest.workspace_id,
                            execution_id=latest.execution_id or latest.id,
                            inputs=(
                                closure_inputs
                                if isinstance(closure_inputs, dict)
                                else {}
                            ),
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

            tasks_store.update_task(
                latest.id,
                **update_kwargs,
            )
            emit_run_state_changed_for_task(
                latest,
                previous_state="RUNNING",
                new_state="DONE",
                reason="execution_completed",
            )

        if redis_queue:
            await redis_queue.ack_task(task_id)
    except Exception as e:
        logger.error(f"Failed to mark task {task_id} as succeeded: {e}", exc_info=True)
