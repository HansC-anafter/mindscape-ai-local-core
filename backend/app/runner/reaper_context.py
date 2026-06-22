"""Shared runner reaper state helpers."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Optional

from backend.app.models.workspace import Task
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.runner_live_state import RunnerLiveStateStore
from backend.app.services.runner_resources import (
    RESOURCE_WAIT_REASON,
    ResourceRequirements,
    resource_lease_keys_from_context,
)
from backend.app.services.host_resources.workspace_quota_admission import (
    WORKSPACE_ALLOCATION_DISABLED_REASON,
    WORKSPACE_ALLOCATION_REQUIRED_REASON,
    WORKSPACE_QUOTA_EXHAUSTED_REASON,
)
from backend.app.runner.redis_transport_repair import (
    normalize_task_id as _normalize_transport_task_id,
)
from backend.app.runner.utils import _env_int, _parse_utc_iso

logger = logging.getLogger("backend.app.runner.reaper")

_CONCURRENCY_LOCKED_REASON = "concurrency_locked"
_DEPENDENCY_HOLD_REASON = "dependency_hold"
_RESOURCE_WAIT_REASON = RESOURCE_WAIT_REASON
_WORKSPACE_QUOTA_EXHAUSTED_REASON = WORKSPACE_QUOTA_EXHAUSTED_REASON
_WORKSPACE_ALLOCATION_REQUIRED_REASON = WORKSPACE_ALLOCATION_REQUIRED_REASON
_WORKSPACE_ALLOCATION_DISABLED_REASON = WORKSPACE_ALLOCATION_DISABLED_REASON
_WORKSPACE_QUOTA_RELEASE_REASONS = frozenset(
    {
        _WORKSPACE_QUOTA_EXHAUSTED_REASON,
        _WORKSPACE_ALLOCATION_REQUIRED_REASON,
        _WORKSPACE_ALLOCATION_DISABLED_REASON,
    }
)
_BROWSER_LOCAL_QUEUE_SHARD = "browser_local"
_DEFAULT_LOCAL_BROWSER_QUEUE_SHARD = "default_local_browser"


def _browser_peer_frontier_lanes() -> frozenset[str]:
    try:
        from backend.app.services.runner_topology.task_family_registry import (
            managed_browser_batch_peer_frontier_lanes,
        )

        return managed_browser_batch_peer_frontier_lanes()
    except Exception:
        return frozenset()

def _task_runner_id(task: Task, ctx: dict[str, Any]) -> Optional[str]:
    runner_id = getattr(task, "runner_id", None)
    if isinstance(runner_id, str) and runner_id.strip():
        return runner_id.strip()
    raw_runner_id = ctx.get("runner_id")
    if isinstance(raw_runner_id, str) and raw_runner_id.strip():
        return raw_runner_id.strip()
    return None

def _task_heartbeat_at(task: Task, ctx: dict[str, Any]) -> Optional[datetime]:
    heartbeat_at = getattr(task, "heartbeat_at", None)
    if isinstance(heartbeat_at, datetime):
        return heartbeat_at
    return _parse_utc_iso(ctx.get("heartbeat_at"))

def _live_task_heartbeat_at(
    task_id: str,
    live_state_store: Optional[RunnerLiveStateStore] = None,
) -> Optional[datetime]:
    try:
        live_state = live_state_store or RunnerLiveStateStore()
        payload = live_state.get_task_heartbeat(task_id)
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return _parse_utc_iso(payload.get("heartbeat_at"))

def _effective_task_heartbeat_at(
    task: Task,
    ctx: dict[str, Any],
    live_state_store: Optional[RunnerLiveStateStore] = None,
) -> Optional[datetime]:
    live_heartbeat_at = _live_task_heartbeat_at(task.id, live_state_store)
    if live_heartbeat_at is not None:
        return live_heartbeat_at
    return _task_heartbeat_at(task, ctx)

def _heartbeat_log_value(heartbeat_at: Optional[datetime], ctx: dict[str, Any]) -> Any:
    if isinstance(heartbeat_at, datetime):
        return heartbeat_at.isoformat()
    return ctx.get("heartbeat_at")

def _blocked_release_limit(ready_target: int, ready_depth: int) -> int:
    capacity_limit = max(0, ready_target - ready_depth)
    floor_limit = max(
        0,
        _env_int("LOCAL_CORE_RUNNER_BLOCKED_RELEASE_MINIMUM", 4),
    )
    return max(capacity_limit, floor_limit)

def _browser_peer_frontier_refill_limit() -> int:
    return max(0, _env_int("LOCAL_CORE_RUNNER_BROWSER_PEER_REFILL_LIMIT", 4))

def _resource_wait_keys_from_context(ctx: dict[str, Any]) -> list[str]:
    keys = resource_lease_keys_from_context(ctx)
    admission = ctx.get("resource_admission")
    if isinstance(admission, dict):
        for field_name in ("resource_keys", "lease_keys"):
            raw_keys = admission.get(field_name)
            if isinstance(raw_keys, list):
                keys.extend(str(key).strip() for key in raw_keys if str(key).strip())
        raw_key = admission.get("resource_key")
        if isinstance(raw_key, str) and raw_key.strip():
            keys.append(raw_key.strip())
    return list(dict.fromkeys(keys))

def _resource_wait_requirements_from_context(ctx: dict[str, Any]) -> Optional[ResourceRequirements]:
    admission = ctx.get("resource_admission")
    if not isinstance(admission, dict):
        return None
    raw_requirements = admission.get("requirements")
    if not isinstance(raw_requirements, dict):
        return None
    try:
        base = ResourceRequirements()
        return ResourceRequirements(
            browser_contexts=int(raw_requirements.get("browser_contexts") or base.browser_contexts),
            ig_profile_lock=raw_requirements.get("ig_profile_lock") or base.ig_profile_lock,
            cpu_weight=int(raw_requirements.get("cpu_weight") or base.cpu_weight),
            memory_mb=int(raw_requirements.get("memory_mb") or base.memory_mb),
            vision_lane=raw_requirements.get("vision_lane") or base.vision_lane,
            llm_lane=raw_requirements.get("llm_lane") or base.llm_lane,
            db_write_budget=raw_requirements.get("db_write_budget") or base.db_write_budget,
            expected_duration_class=raw_requirements.get("expected_duration_class") or base.expected_duration_class,
        )
    except Exception:
        return None

def _host_resource_wait_still_blocked(ctx: dict[str, Any]) -> Optional[Any]:
    requirements = _resource_wait_requirements_from_context(ctx)
    if requirements is None:
        return None
    try:
        from backend.app.services.host_resources import evaluate_runner_requirements

        advice = evaluate_runner_requirements(requirements)
        if advice is not None and not bool(getattr(advice, "allow", False)):
            return advice
    except Exception:
        return None
    return None

def _workspace_quota_payload(decision: Any) -> dict[str, Any]:
    to_dict = getattr(decision, "to_dict", None)
    if callable(to_dict):
        try:
            payload = to_dict()
            if isinstance(payload, dict):
                return payload
        except Exception:
            return {}
    payload: dict[str, Any] = {
        "allow": getattr(decision, "allow", None),
        "reason": getattr(decision, "reason", None),
        "active_count": getattr(decision, "active_count", None),
        "max_parallel_task_claims": getattr(decision, "max_parallel_task_claims", None),
    }
    allocation = getattr(decision, "allocation", None)
    if isinstance(allocation, dict):
        payload["allocation"] = allocation
    return {key: value for key, value in payload.items() if value is not None}

def _workspace_quota_allocation(decision: Any, payload: dict[str, Any]) -> dict[str, Any]:
    allocation = getattr(decision, "allocation", None)
    if isinstance(allocation, dict):
        return allocation
    payload_allocation = payload.get("allocation")
    return payload_allocation if isinstance(payload_allocation, dict) else {}

def _workspace_quota_task_selectors(allocation: dict[str, Any]) -> list[str]:
    metadata = allocation.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    selectors = metadata.get("task_selectors")
    if not isinstance(selectors, list):
        return []
    return [
        normalized
        for normalized in (str(selector).strip() for selector in selectors)
        if normalized
    ]

def _workspace_quota_release_key(task: Task, allocation: dict[str, Any]) -> str:
    allocation_id = str(allocation.get("allocation_id") or "").strip()
    if allocation_id:
        return allocation_id
    workspace_id = str(getattr(task, "workspace_id", "") or "").strip()
    queue_shard = str(getattr(task, "queue_shard", "") or "").strip()
    task_family = str(allocation.get("task_family") or "").strip()
    return f"{workspace_id}:{queue_shard}:{task_family}"

def _workspace_quota_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default

def _is_stale_started_task(task: Task, threshold: datetime) -> bool:
    started_at = getattr(task, "started_at", None)
    return bool(started_at and started_at <= threshold)

def _emit_run_state_changed_for_task(
    task: Task,
    *,
    previous_state: str,
    new_state: str,
    reason: str,
) -> None:
    """Emit the workspace lifecycle event when reaper owns a terminal transition."""
    try:
        from backend.app.services.playbook_runner_core.run_state import (
            build_run_state_changed_event,
        )

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
        event = build_run_state_changed_event(
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
            "Failed to emit %s RUN_STATE_CHANGED event for stale task %s (%s): %s",
            new_state,
            task.id,
            task.execution_id,
            emit_error,
        )

def _normalize_task_id(raw_value: object) -> str:
    return _normalize_transport_task_id(raw_value)
