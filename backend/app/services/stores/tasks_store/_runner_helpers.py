"""TasksStore runner helper functions and SQL snippets."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from app.models.workspace import Task, TaskStatus

_WORKSPACE_QUOTA_RELEASE_REASONS = (
    "workspace_allocation_quota_exhausted",
    "workspace_allocation_required",
    "workspace_allocation_disabled",
)

_CLAIM_CONTEXT_STALE_KEYS = (
    "dependency_hold",
    "error",
    "failed_at",
    "heartbeat_at",
    "resource_pressure",
    "resource_pressure_source",
    "resource_retry_delay_sec",
    "resource_snapshot",
    "resume_after",
    "runner_reaper",
    "runner_skip_conflict_lock_key",
    "runner_skip_lock_key",
    "runner_skip_reason",
)


def _parse_heartbeat_datetime(raw_value: Any) -> Optional[datetime]:
    if isinstance(raw_value, datetime):
        heartbeat_at = raw_value
    elif isinstance(raw_value, str) and raw_value:
        try:
            heartbeat_at = datetime.fromisoformat(raw_value)
        except Exception:
            return None
    else:
        return None

    if heartbeat_at.tzinfo is None:
        heartbeat_at = heartbeat_at.replace(tzinfo=timezone.utc)
    return heartbeat_at


def _effective_runner_heartbeat_at(
    task: Task,
    ctx: Dict[str, Any],
    live_state_store: Optional[RunnerLiveStateStore],
) -> Optional[datetime]:
    if live_state_store is not None:
        try:
            live_payload = live_state_store.get_task_heartbeat(task.id)
        except Exception:
            live_payload = None
        if isinstance(live_payload, dict):
            live_heartbeat_at = _parse_heartbeat_datetime(
                live_payload.get("heartbeat_at")
            )
            if live_heartbeat_at is not None:
                return live_heartbeat_at

    heartbeat_at = _parse_heartbeat_datetime(getattr(task, "heartbeat_at", None))
    if heartbeat_at is not None:
        return heartbeat_at
    return _parse_heartbeat_datetime(ctx.get("heartbeat_at"))


def _build_claim_execution_context(
    existing_ctx: Dict[str, Any],
    *,
    task_params: Optional[Dict[str, Any]] = None,
    runner_id: str,
    now: datetime,
) -> Dict[str, Any]:
    ctx = dict(existing_ctx) if isinstance(existing_ctx, dict) else {}
    params_inputs: Dict[str, Any] = {}
    if isinstance(task_params, dict):
        nested_params_inputs = task_params.get("inputs")
        if isinstance(nested_params_inputs, dict):
            params_inputs.update(nested_params_inputs)
        else:
            params_inputs.update(task_params)
    if params_inputs:
        ctx_inputs = ctx.get("inputs")
        merged_inputs = dict(params_inputs)
        if isinstance(ctx_inputs, dict):
            merged_inputs.update(ctx_inputs)
        ctx["inputs"] = merged_inputs
    for key in _CLAIM_CONTEXT_STALE_KEYS:
        ctx.pop(key, None)
    ctx["runner_id"] = runner_id
    ctx["heartbeat_at"] = now.isoformat()
    ctx["status"] = "running"
    return ctx


def _normalize_concurrency_keys(raw_keys: Optional[List[str]]) -> List[str]:
    keys: List[str] = []
    seen: set[str] = set()
    for raw_key in raw_keys or []:
        if not isinstance(raw_key, str):
            continue
        key = raw_key.strip()
        if not key or key in seen:
            continue
        keys.append(key)
        seen.add(key)
    return keys


def _clean_string(value: Any) -> Optional[str]:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _clean_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _decision_to_payload(workspace_quota_decision: Any) -> Optional[Dict[str, Any]]:
    if workspace_quota_decision is None:
        return None
    to_dict = getattr(workspace_quota_decision, "to_dict", None)
    if callable(to_dict):
        try:
            payload = to_dict()
            return payload if isinstance(payload, dict) else None
        except Exception:
            return None
    return workspace_quota_decision if isinstance(workspace_quota_decision, dict) else None


def _json_mapping(raw_value: Any) -> Dict[str, Any]:
    if isinstance(raw_value, dict):
        return raw_value
    if isinstance(raw_value, str) and raw_value.strip():
        try:
            parsed = json.loads(raw_value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _quota_selectors(allocation: Dict[str, Any]) -> List[str]:
    metadata = _json_mapping(allocation.get("metadata"))
    selectors = metadata.get("task_selectors")
    if not isinstance(selectors, list):
        return []
    normalized: List[str] = []
    seen: set[str] = set()
    for selector in selectors:
        value = _clean_string(selector)
        if not value or value in seen:
            continue
        normalized.append(value)
        seen.add(value)
    return normalized


def _workspace_quota_allows_claim(
    conn,
    *,
    task_id: str,
    row: Any,
    workspace_quota_decision: Any,
) -> bool:
    payload = _decision_to_payload(workspace_quota_decision)
    allocation = payload.get("allocation") if isinstance(payload, dict) else None
    if not isinstance(allocation, dict):
        return True

    allocation_id = _clean_string(allocation.get("allocation_id"))
    workspace_id = _clean_string(getattr(row, "workspace_id", None))
    queue_shard = _clean_string(getattr(row, "queue_shard", None))
    if not allocation_id or not workspace_id or not queue_shard:
        return True

    lock_suffix = "" if conn.dialect.name == "sqlite" else " FOR UPDATE"
    locked = conn.execute(
        text(
            f"""
            SELECT allocation_id, state, max_parallel_task_claims, metadata
            FROM host_resource_workspace_allocations
            WHERE allocation_id = :allocation_id
            {lock_suffix}
            """
        ),
        {"allocation_id": allocation_id},
    ).fetchone()
    if not locked:
        return False
    if _clean_string(getattr(locked, "state", None)) != "enabled":
        return False

    locked_allocation = {
        "metadata": getattr(locked, "metadata", None),
    }
    if not _quota_selectors(locked_allocation):
        locked_allocation["metadata"] = allocation.get("metadata")
    selectors = _quota_selectors(locked_allocation)
    max_parallel_task_claims = max(
        1,
        _clean_int(getattr(locked, "max_parallel_task_claims", None), default=1),
    )

    params: Dict[str, Any] = {
        "workspace_id": workspace_id,
        "queue_shard": queue_shard,
        "running_status": TaskStatus.RUNNING.value,
        "task_id": task_id,
    }
    selector_sql = ""
    if selectors:
        placeholders: List[str] = []
        for index, selector in enumerate(selectors):
            key = f"selector_{index}"
            params[key] = selector
            placeholders.append(f":{key}")
        selector_list = ", ".join(placeholders)
        playbook_expr = (
            "json_extract(execution_context, '$.playbook_code')"
            if conn.dialect.name == "sqlite"
            else "execution_context::jsonb->>'playbook_code'"
        )
        selector_sql = f"""
          AND (
                pack_id IN ({selector_list})
                OR task_type IN ({selector_list})
                OR {playbook_expr} IN ({selector_list})
          )
        """

    active_count = conn.execute(
        text(
            f"""
            SELECT COUNT(*)::int
            FROM tasks
            WHERE workspace_id = :workspace_id
              AND queue_shard = :queue_shard
              AND status = :running_status
              AND id <> :task_id
              {selector_sql}
            """
            if conn.dialect.name != "sqlite"
            else f"""
            SELECT COUNT(*)
            FROM tasks
            WHERE workspace_id = :workspace_id
              AND queue_shard = :queue_shard
              AND status = :running_status
              AND id <> :task_id
              {selector_sql}
            """
        ),
        params,
    ).scalar()
    return _clean_int(active_count, default=0) < max_parallel_task_claims


def _running_concurrency_conflict_clause(
    concurrency_keys: List[str],
) -> tuple[str, Dict[str, str]]:
    if not concurrency_keys:
        return "", {}

    params = {f"concurrency_key_{idx}": key for idx, key in enumerate(concurrency_keys)}
    placeholders = ", ".join(f":concurrency_key_{idx}" for idx in range(len(params)))
    return (
        f"""
        AND NOT EXISTS (
            SELECT 1
            FROM tasks running_task
            WHERE running_task.id <> :task_id
              AND running_task.status = :running_status
              AND running_task.concurrency_key IN ({placeholders})
            LIMIT 1
        )
        """,
        params,
    )


def _workspace_quota_selector_sql(
    conn,
    *,
    selectors: List[str],
    params: Dict[str, Any],
    key_prefix: str,
) -> str:
    if not selectors:
        return ""
    placeholders: List[str] = []
    for index, selector in enumerate(selectors):
        key = f"{key_prefix}_{index}"
        params[key] = selector
        placeholders.append(f":{key}")
    selector_list = ", ".join(placeholders)
    playbook_expr = (
        "json_extract(execution_context, '$.playbook_code')"
        if conn.dialect.name == "sqlite"
        else "execution_context::jsonb->>'playbook_code'"
    )
    return f"""
      AND (
            pack_id IN ({selector_list})
            OR task_type IN ({selector_list})
            OR {playbook_expr} IN ({selector_list})
      )
    """


def _workspace_quota_task_selector_sql(conn) -> str:
    playbook_expr = (
        "json_extract(execution_context, '$.playbook_code')"
        if conn.dialect.name == "sqlite"
        else "execution_context::jsonb->>'playbook_code'"
    )
    return f"""
      AND (
            pack_id = :task_selector
            OR task_type = :task_selector
            OR {playbook_expr} = :task_selector
      )
    """
