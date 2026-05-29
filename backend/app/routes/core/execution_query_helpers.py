"""Query helpers for playbook execution routes."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from sqlalchemy import text

from backend.app.services.runner_live_state import RunnerLiveStateStore
from backend.app.services.runner_resources import (
    STATUS_SNAPSHOT_TTL_SECONDS,
    SyncRedisTtlSnapshotStore,
    build_status_snapshot_key,
    get_ttl_snapshot_sync,
    set_ttl_snapshot_sync,
)

from .execution_ordering import build_execution_order_clause
from .execution_status_utils import trim_execution_context_for_status

_STATUS_SNAPSHOT_STORE = SyncRedisTtlSnapshotStore()
_RUNNING_STATUS = "running"


def _get_row_value(row: Any, key: str) -> Any:
    """Read a value from a SQLAlchemy row or row mapping."""
    value = getattr(row, key, None)
    if value is None and hasattr(row, "_mapping"):
        value = row._mapping.get(key)
    return value


def parse_execution_context(raw_ctx: Any) -> Dict[str, Any]:
    """Normalize execution_context payloads to a dictionary."""
    if isinstance(raw_ctx, dict):
        return raw_ctx
    if isinstance(raw_ctx, str):
        try:
            parsed = json.loads(raw_ctx)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def build_status_payload_from_row(
    row: Any,
    *,
    execution_id: str,
) -> Optional[Dict[str, Any]]:
    """Build the /status payload from a database row."""
    if not row:
        return None

    execution_context = trim_execution_context_for_status(
        parse_execution_context(_get_row_value(row, "execution_context"))
    )
    task_status = _get_row_value(row, "status")
    payload_execution_id = _get_row_value(row, "execution_id")
    return {
        "execution_id": payload_execution_id or execution_id,
        "task_status": task_status,
        "execution_context": execution_context,
    }


def attach_runner_resource_snapshot(
    payload: Optional[Dict[str, Any]],
    heartbeats: list[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Attach runner resource telemetry without deriving task progress from it."""
    if not payload:
        return payload
    ctx = payload.get("execution_context")
    if not isinstance(ctx, dict):
        return payload
    runner_id = str(ctx.get("runner_id") or "").strip()
    if not runner_id:
        return payload
    for heartbeat in heartbeats or []:
        if str(heartbeat.get("runner_id") or "").strip() != runner_id:
            continue
        snapshot = heartbeat.get("resource_snapshot")
        if isinstance(snapshot, dict):
            ctx["runner_resource_snapshot"] = snapshot
        heartbeat_at = heartbeat.get("heartbeat_at")
        if heartbeat_at and not ctx.get("runner_heartbeat_at"):
            ctx["runner_heartbeat_at"] = heartbeat_at
        break
    return payload


def _apply_live_task_heartbeat(
    payload: Optional[Dict[str, Any]],
    *,
    task_id: Any,
) -> Optional[Dict[str, Any]]:
    """Overlay Redis live heartbeat onto running execution status payloads."""
    if not payload:
        return payload
    if str(payload.get("task_status") or "").strip().lower() != _RUNNING_STATUS:
        return payload
    ctx = payload.get("execution_context")
    if not isinstance(ctx, dict):
        return payload
    task_id_text = str(task_id or "").strip()
    if not task_id_text:
        return payload
    try:
        live_payload = RunnerLiveStateStore().get_task_heartbeat(task_id_text)
    except Exception:
        live_payload = None
    if not isinstance(live_payload, dict):
        return payload
    heartbeat_at = live_payload.get("heartbeat_at")
    if heartbeat_at:
        ctx["heartbeat_at"] = heartbeat_at
        ctx.setdefault("runner_heartbeat_at", heartbeat_at)
    runner_id = live_payload.get("runner_id")
    if runner_id:
        ctx["runner_id"] = runner_id
    return payload


def _read_execution_status_hot_cache(execution_id: str) -> Optional[Dict[str, Any]]:
    try:
        return get_ttl_snapshot_sync(
            _STATUS_SNAPSHOT_STORE,
            build_status_snapshot_key(execution_id),
        )
    except Exception:
        return None


def _write_execution_status_hot_cache(
    execution_id: str,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    try:
        set_ttl_snapshot_sync(
            _STATUS_SNAPSHOT_STORE,
            build_status_snapshot_key(execution_id),
            payload,
            ttl_seconds=STATUS_SNAPSHOT_TTL_SECONDS,
        )
    except Exception:
        pass
    return payload


def load_execution_status_payload(tasks_store, execution_id: str):
    """Load a lightweight execution status payload from the tasks table."""
    cached = _read_execution_status_hot_cache(execution_id)
    if cached:
        return cached

    with tasks_store.get_connection() as conn:
        row = conn.execute(
            text(
                """
                SELECT
                    id,
                    execution_id,
                    status,
                    jsonb_strip_nulls(
                        COALESCE(
                            (
                                execution_context::jsonb
                                - 'result'
                                - 'workflow_result'
                                - 'step_outputs'
                                - 'outputs'
                                - 'conversation_state'
                            ),
                            '{}'::jsonb
                        )
                        || jsonb_build_object(
                            'runner_id', runner_id,
                            'heartbeat_at', heartbeat_at
                        )
                    )::json AS execution_context
                FROM tasks
                WHERE execution_id = :execution_id OR id = :execution_id
                ORDER BY CASE WHEN execution_id = :execution_id THEN 0 ELSE 1 END, created_at DESC
                LIMIT 1
                """
            ),
            {"execution_id": execution_id},
        ).fetchone()
    payload = build_status_payload_from_row(row, execution_id=execution_id)
    if payload:
        payload = _apply_live_task_heartbeat(
            payload,
            task_id=_get_row_value(row, "id"),
        )
        try:
            heartbeats = tasks_store.list_runner_heartbeats(
                max_age_seconds=300,
                limit=100,
            )
        except Exception:
            heartbeats = []
        payload = attach_runner_resource_snapshot(payload, heartbeats)
        payload = _write_execution_status_hot_cache(execution_id, payload)
    return payload


def parse_status_filter(status_filter: Optional[str]) -> list[str]:
    """Normalize comma-separated execution statuses."""
    if not status_filter:
        return []
    return [status.strip().lower() for status in status_filter.split(",") if status.strip()]


def load_global_execution_rows(
    tasks_store,
    *,
    limit: int,
    playbook_code_prefix: Optional[str],
    status_filter: Optional[str],
):
    """Load global execution rows with optional route-level filters."""
    query_parts = [
        """
        SELECT
            t.id,
            t.workspace_id,
            t.message_id,
            t.execution_id,
            t.parent_execution_id,
            t.project_id,
            t.pack_id,
            t.task_type,
            t.status,
            t.params,
            t.result,
            (
                t.execution_context::jsonb
                - 'result'
                - 'workflow_result'
                - 'step_outputs'
                - 'outputs'
            )::json AS execution_context,
            t.storyline_tags,
            t.created_at,
            t.next_eligible_at,
            t.blocked_reason,
            t.blocked_payload,
            t.queue_shard,
            t.concurrency_key,
            t.frontier_state,
            t.frontier_enqueued_at,
            t.started_at,
            t.completed_at,
            t.error,
            w.title AS workspace_name
        FROM tasks t
        LEFT JOIN workspaces w ON w.id = t.workspace_id
        WHERE 1=1
        """
    ]
    params: dict[str, Any] = {}

    if playbook_code_prefix:
        query_parts.append("AND t.pack_id LIKE :pack_prefix")
        params["pack_prefix"] = f"{playbook_code_prefix}%"

    statuses = parse_status_filter(status_filter)
    if statuses:
        query_parts.append("AND LOWER(t.status) = ANY(:statuses)")
        params["statuses"] = statuses

    query_parts.append(
        build_execution_order_clause(
            "created_at",
            "desc",
            status_expr="t.status",
            column_prefix="t.",
        )
    )
    query_parts.append("LIMIT :limit")
    params["limit"] = limit

    with tasks_store.get_connection() as conn:
        return conn.execute(text(" ".join(query_parts)), params).fetchall()


def serialize_global_execution(tasks_store, task, row: Any, queue_cache) -> Dict[str, Any]:
    """Convert a task row into the public global-execution payload."""
    from backend.app.services.task_execution_projection import project_execution_for_api

    payload = project_execution_for_api(
        task.model_dump(),
        queue_position=queue_cache.get_position(tasks_store, task),
        queue_total=queue_cache.get_total(task.queue_shard or "default"),
    )
    payload["workspace_name"] = _get_row_value(row, "workspace_name")
    return payload
