"""Query helpers for playbook execution routes."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from sqlalchemy import text

from .execution_ordering import build_execution_order_clause
from .execution_status_utils import trim_execution_context_for_status


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


def load_execution_status_payload(tasks_store, execution_id: str):
    """Load a lightweight execution status payload from the tasks table."""
    with tasks_store.get_connection() as conn:
        row = conn.execute(
            text(
                """
                SELECT
                    execution_id,
                    status,
                    CASE
                        WHEN execution_context IS NULL THEN NULL
                        ELSE (
                            execution_context::jsonb
                            - 'result'
                            - 'workflow_result'
                            - 'step_outputs'
                            - 'outputs'
                            - 'conversation_state'
                        )::json
                    END AS execution_context
                FROM tasks
                WHERE execution_id = :execution_id OR id = :execution_id
                ORDER BY CASE WHEN execution_id = :execution_id THEN 0 ELSE 1 END, created_at DESC
                LIMIT 1
                """
            ),
            {"execution_id": execution_id},
        ).fetchone()
    return build_status_payload_from_row(row, execution_id=execution_id)


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
    payload = task.model_dump()
    execution_context = payload.get("execution_context") or {}
    payload["playbook_code"] = payload.get("pack_id") or execution_context.get("playbook_code")
    payload["execution_id"] = payload.get("execution_id") or payload.get("id")
    payload["workspace_name"] = _get_row_value(row, "workspace_name")
    payload["queue_position"] = queue_cache.get_position(tasks_store, task)
    payload["queue_total"] = queue_cache.get_total(payload.get("queue_shard") or "default")
    return payload
