"""Scheduler field derivation helpers for TasksStore CRUD."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.models.workspace import Task, TaskStatus
from backend.app.services.runner_topology import (
    BROWSER_LOCAL_QUEUE_PARTITION,
    VISION_LOCAL_QUEUE_PARTITION,
    canonical_queue_partition_for_pack,
    merge_runner_metadata_into_context,
    normalize_queue_partition,
    resolve_managed_batch_binding,
    resolve_default_local_browser_queue_override,
    resolve_installed_playbook_runner_metadata,
)

_RUNNER_TASK_TYPES = {"playbook_execution", "tool_execution"}
_TERMINAL_TASK_STATUSES = {
    TaskStatus.SUCCEEDED.value,
    TaskStatus.FAILED.value,
    TaskStatus.CANCELLED_BY_USER.value,
    TaskStatus.EXPIRED.value,
}


def _normalize_frontier_updates_for_status(kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """Keep scheduler frontier fields consistent with authoritative task status."""
    normalized = dict(kwargs)
    status_val = normalized.get("status")
    if status_val is None:
        return normalized

    status_raw = normalize_task_status_value(status_val)

    if status_raw in _TERMINAL_TASK_STATUSES:
        normalized["frontier_state"] = "done"
        normalized["frontier_enqueued_at"] = None
        normalized["runner_id"] = None
        normalized["heartbeat_at"] = None
    elif status_raw == TaskStatus.RUNNING.value:
        normalized["frontier_state"] = "running"
        normalized["frontier_enqueued_at"] = None

    return normalized


def _utc_now() -> datetime:
    """Return timezone-aware UTC now. Fixes Postgres timestamptz offset bug."""
    return datetime.now(timezone.utc)


def _coerce_task_status(status: Any) -> str:
    return normalize_task_status_value(status)


def normalize_task_status_value(status: Any) -> str:
    if hasattr(status, "value"):
        raw_value = str(status.value)
    else:
        raw_value = str(status)
    normalized = raw_value.strip().lower()
    if normalized == "cancelled":
        return TaskStatus.CANCELLED_BY_USER.value
    return normalized


def coerce_task_status_enum(status: Any) -> TaskStatus:
    return TaskStatus(normalize_task_status_value(status))


def _parse_resume_after(raw_value: Any) -> Optional[datetime]:
    if not isinstance(raw_value, str) or not raw_value.strip():
        return None
    try:
        dt = datetime.fromisoformat(raw_value)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _normalize_queue_shard(value: Any) -> Optional[str]:
    return normalize_queue_partition(value, fallback=None)


def _clean_queue_shard(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _resolve_queue_shard(
    pack_id: str, execution_context: Optional[Dict[str, Any]] = None
) -> str:
    binding = resolve_managed_batch_binding(pack_id, execution_context)
    queue_override = binding.queue_shard if binding else resolve_default_local_browser_queue_override(
        pack_id,
        execution_context,
    )
    if queue_override:
        return queue_override

    explicit_queue_shard = None
    if isinstance(execution_context, dict):
        explicit_queue_shard = _normalize_queue_shard(
            execution_context.get("queue_partition")
        ) or _clean_queue_shard(
            execution_context.get("queue_shard")
        )
    if explicit_queue_shard:
        return explicit_queue_shard
    spec_metadata = resolve_installed_playbook_runner_metadata(pack_id)
    if spec_metadata:
        metadata_queue_shard = _normalize_queue_shard(
            spec_metadata.get("queue_partition")
        ) or _normalize_queue_shard(
            spec_metadata.get("queue_shard")
        )
        if metadata_queue_shard:
            return metadata_queue_shard
    if isinstance(execution_context, dict):
        resource_class = str(execution_context.get("resource_class") or "").strip().lower()
        if resource_class == "browser":
            return BROWSER_LOCAL_QUEUE_PARTITION
        if resource_class == "compute":
            return VISION_LOCAL_QUEUE_PARTITION
    return canonical_queue_partition_for_pack(pack_id)


def _resolve_hydrated_queue_shard(
    pack_id: str, execution_context: Optional[Dict[str, Any]] = None
) -> str:
    binding = resolve_managed_batch_binding(pack_id, execution_context)
    queue_override = binding.queue_shard if binding else resolve_default_local_browser_queue_override(
        pack_id,
        execution_context,
    )
    if queue_override:
        return queue_override

    if isinstance(execution_context, dict):
        resource_class = str(execution_context.get("resource_class") or "").strip().lower()
        if resource_class == "browser":
            return BROWSER_LOCAL_QUEUE_PARTITION
        if resource_class == "compute":
            return VISION_LOCAL_QUEUE_PARTITION
    return _resolve_queue_shard(pack_id, execution_context)


def _enrich_runner_task_context(task: Task) -> None:
    if task.task_type not in _RUNNER_TASK_TYPES:
        return
    playbook_code = ""
    if isinstance(task.execution_context, dict):
        playbook_code = str(task.execution_context.get("playbook_code") or "").strip()
    playbook_code = playbook_code or str(task.pack_id or "").strip()
    if not playbook_code:
        return

    metadata = resolve_installed_playbook_runner_metadata(playbook_code)
    if not metadata:
        return
    task.execution_context = merge_runner_metadata_into_context(
        task.execution_context,
        metadata,
        playbook_code=playbook_code,
    )


def _resolve_concurrency_key(
    execution_context: Optional[Dict[str, Any]], pack_id: str
) -> Optional[str]:
    try:
        from backend.app.runner.concurrency import _resolve_lock_key

        return _resolve_lock_key(execution_context, pack_id)
    except Exception:
        return None


def _derive_blocked_payload(
    execution_context: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    if not isinstance(execution_context, dict):
        return None

    payload: Dict[str, Any] = {}

    dependency_hold = execution_context.get("dependency_hold")
    if isinstance(dependency_hold, dict) and dependency_hold:
        payload["dependency_hold"] = dependency_hold

    if execution_context.get("runner_skip_lock_key"):
        payload["lock_key"] = execution_context.get("runner_skip_lock_key")
    if execution_context.get("runner_skip_conflict_lock_key"):
        payload["conflicting_lock_key"] = execution_context.get(
            "runner_skip_conflict_lock_key"
        )

    return payload or None


def _derive_scheduler_fields(task: Task) -> Dict[str, Any]:
    ctx = task.execution_context if isinstance(task.execution_context, dict) else {}
    now = _utc_now()
    status_value = _coerce_task_status(task.status)
    explicit_fields = getattr(task, "model_fields_set", set()) or set()

    next_eligible_at = (
        (task.next_eligible_at if "next_eligible_at" in explicit_fields else None)
        or _parse_resume_after(ctx.get("resume_after"))
        or task.created_at
        or now
    )

    blocked_reason = (task.blocked_reason if "blocked_reason" in explicit_fields else None) or ctx.get(
        "runner_skip_reason"
    )
    if not blocked_reason and isinstance(ctx.get("dependency_hold"), dict):
        blocked_reason = "dependency_hold"

    blocked_payload = task.blocked_payload if "blocked_payload" in explicit_fields else None
    if blocked_payload is None:
        blocked_payload = _derive_blocked_payload(ctx)

    binding = resolve_managed_batch_binding(task.pack_id, ctx)
    facade_queue_shard = binding.queue_shard if binding else resolve_default_local_browser_queue_override(task.pack_id, ctx)
    explicit_queue_shard = (
        task.queue_shard if "queue_shard" in explicit_fields and task.queue_shard else None
    )
    queue_shard = facade_queue_shard or explicit_queue_shard or _resolve_queue_shard(task.pack_id, ctx)
    concurrency_key = (
        task.concurrency_key
        if "concurrency_key" in explicit_fields and task.concurrency_key
        else None
    ) or _resolve_concurrency_key(
        ctx, task.pack_id
    )

    frontier_state = (
        task.frontier_state
        if "frontier_state" in explicit_fields and task.frontier_state
        else None
    )
    if not frontier_state:
        if status_value == TaskStatus.RUNNING.value:
            frontier_state = "running"
        elif status_value in _TERMINAL_TASK_STATUSES:
            frontier_state = "done"
        elif (
            blocked_reason
            or next_eligible_at > now
            or task.task_type not in _RUNNER_TASK_TYPES
        ):
            frontier_state = "cold"
        else:
            frontier_state = "ready"

    frontier_enqueued_at = (
        task.frontier_enqueued_at
        if "frontier_enqueued_at" in explicit_fields
        else None
    )
    if frontier_enqueued_at is None and frontier_state == "ready":
        frontier_enqueued_at = task.created_at or now

    return {
        "next_eligible_at": next_eligible_at,
        "blocked_reason": blocked_reason,
        "blocked_payload": blocked_payload,
        "queue_shard": queue_shard,
        "concurrency_key": concurrency_key,
        "frontier_state": frontier_state,
        "frontier_enqueued_at": frontier_enqueued_at,
    }
