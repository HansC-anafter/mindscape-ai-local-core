"""Task execution intent and runtime binding helpers."""

import logging
from datetime import timedelta
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from backend.app.models.workspace import Task, TaskStatus
from backend.app.services.execution_intent_resolver import (
    ExecutionIntentResolution,
    ExecutionIntentResolver,
)
from backend.app.services.playbook_execution_input_payloads import (
    hydrate_execution_inputs,
)
from backend.app.services.runner_topology import (
    resolve_runner_profile_from_env,
    resolve_runtime_dispatch_target,
)
from backend.app.services.stores.redis.runner_queue_store import RedisRunnerQueueStore
from backend.app.services.stores.tasks_store import TasksStore

from backend.app.runner.concurrency import _build_inputs
from backend.app.runner.utils import _env_int, _utc_now

logger = logging.getLogger(__name__)


def _classify_non_retryable_task_error(message: str) -> Optional[str]:
    normalized = str(message or "")
    if "Missing required playbook inputs" in normalized:
        return "missing_required_playbook_inputs"
    if "Terminal workflow failure" in normalized:
        return "terminal_workflow_failure"
    return None


def _is_non_retryable_task_error(message: str) -> bool:
    return _classify_non_retryable_task_error(message) is not None


def _resolve_execution_attempt_inputs(
    task: Task,
    task_ctx: Optional[Dict[str, Any]],
) -> tuple[Dict[str, Any], ExecutionIntentResolution]:
    hydrated_context = dict(task_ctx) if isinstance(task_ctx, dict) else {}
    hydrated_inputs = hydrate_execution_inputs(hydrated_context)
    if hydrated_inputs:
        hydrated_context["inputs"] = hydrated_inputs
    raw_inputs = _build_inputs(task.execution_id or task.id, hydrated_context)
    try:
        resolution = ExecutionIntentResolver().resolve(
            task=task,
            execution_context=hydrated_context,
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


def _is_internal_knowledge_projection_task(
    task: Task,
    task_ctx: Optional[Dict[str, Any]],
) -> bool:
    """Keep the pointer-only projection envelope on its admitted local lane."""

    from backend.app.services.knowledge_projection.retrievable.source_admission import (
        INTERNAL_PROJECTION_TOOL,
    )

    context = task_ctx if isinstance(task_ctx, dict) else {}
    return (
        task.task_type == "tool_execution"
        and str(task.pack_id or "").strip() == INTERNAL_PROJECTION_TOOL
        and str(context.get("tool_name") or "").strip()
        == INTERNAL_PROJECTION_TOOL
    )


def _apply_runtime_binding_to_playbook_task(
    task: Task,
    task_ctx: Optional[Dict[str, Any]],
    inputs: Optional[Dict[str, Any]],
    *,
    profile_id: Optional[str],
) -> tuple[Dict[str, Any], Dict[str, Any], Any]:
    updated_inputs = dict(inputs) if isinstance(inputs, dict) else {}
    updated_ctx = dict(task_ctx) if isinstance(task_ctx, dict) else {}

    if task.task_type == "product_outcome_evaluation":
        return updated_inputs, updated_ctx, None

    if _is_internal_knowledge_projection_task(task, updated_ctx):
        return updated_inputs, updated_ctx, None

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
