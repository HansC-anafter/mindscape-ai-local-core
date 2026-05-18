from typing import Any, Dict

from fastapi import HTTPException

from backend.app.models.workspace import TaskStatus
from backend.app.services.json_safety import json_value_without_nul
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.queue_position_cache import QUEUE_CACHE as _QUEUE_CACHE
from backend.app.services.stores.tasks_store import TasksStore
from .streaming import _build_admission_state, _extract_artifact_progress_from_content

store = MindscapeStore()


def load_execution_progress_snapshot_payload(
    workspace_id: str,
    execution_id: str,
) -> Dict[str, Any]:
    from sqlalchemy import text

    tasks_store = TasksStore()
    task = tasks_store.get_task_by_execution_id(execution_id)
    if not task:
        task = tasks_store.get_task(execution_id)
    if not task:
        raise HTTPException(status_code=404, detail="Execution not found")
    if task.workspace_id != workspace_id:
        raise HTTPException(
            status_code=403, detail="Execution does not belong to this workspace"
        )

    artifact_id = None
    artifact_updated_at = None
    progress = None
    artifact_metadata = {}
    content_metadata = {}

    try:
        with tasks_store.get_connection() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT
                        id,
                        updated_at,
                        created_at,
                        metadata,
                        content
                    FROM artifacts
                    WHERE workspace_id = :workspace_id
                      AND execution_id = :execution_id
                      AND content IS NOT NULL
                    ORDER BY updated_at DESC
                    LIMIT 5
                    """
                ),
                {
                    "workspace_id": workspace_id,
                    "execution_id": execution_id,
                },
            ).fetchall()
        for row in rows:
            row_progress, row_content_metadata = _extract_artifact_progress_from_content(
                row.content
            )
            if not isinstance(row_progress, dict):
                continue
            artifact_id = str(row.id)
            ts = row.updated_at or row.created_at
            artifact_updated_at = ts.isoformat() if ts else None
            artifact_metadata = json_value_without_nul(row.metadata, {}) or {}
            progress = row_progress
            content_metadata = row_content_metadata
            break
    except Exception:
        artifact = store.artifacts.get_by_execution_id(execution_id)
        if artifact and artifact.workspace_id == workspace_id:
            content = artifact.content or {}
            artifact_id = artifact.id
            ts = artifact.updated_at or artifact.created_at
            artifact_updated_at = ts.isoformat() if ts else None
            artifact_metadata = artifact.metadata or {}
            if isinstance(content, dict):
                p = content.get("progress")
                progress = p if isinstance(p, dict) else {}
                cm = content.get("metadata")
                content_metadata = cm if isinstance(cm, dict) else {}

    ctx = task.execution_context if isinstance(task.execution_context, dict) else {}
    _QUEUE_CACHE.refresh_if_stale(tasks_store)

    return {
        "workspace_id": workspace_id,
        "execution_id": execution_id,
        "task_status": task.status,
        "artifact_id": artifact_id,
        "artifact_updated_at": artifact_updated_at,
        "progress": progress if isinstance(progress, dict) else None,
        "queue_position": _QUEUE_CACHE.get_position(tasks_store, task),
        "queue_total": _QUEUE_CACHE.get_total(task.queue_shard or "default"),
        "blocked_reason": task.blocked_reason,
        "blocked_payload": task.blocked_payload,
        "frontier_state": task.frontier_state,
        "next_eligible_at": (
            task.next_eligible_at.isoformat() if task.next_eligible_at else None
        ),
        "admission_state": _build_admission_state(task, ctx),
        "artifact_metadata": artifact_metadata,
        "content_metadata": content_metadata,
        "execution_context": {
            "heartbeat_at": (
                task.heartbeat_at.isoformat()
                if getattr(task, "heartbeat_at", None)
                else (
                    ctx.get("heartbeat_at")
                    if task.status == TaskStatus.RUNNING
                    else None
                )
            ),
            "runner_id": getattr(task, "runner_id", None)
            or (ctx.get("runner_id") if task.status == TaskStatus.RUNNING else None),
            "execution_backend_hint": ctx.get("execution_backend_hint"),
            "inputs": ctx.get("inputs") if isinstance(ctx.get("inputs"), dict) else {},
            "dependency_hold": ctx.get("dependency_hold"),
            "admission_policy": (
                ctx.get("admission_policy")
                if isinstance(ctx.get("admission_policy"), dict)
                else None
            ),
            "admission": ctx.get("admission") if isinstance(ctx.get("admission"), dict) else None,
        },
    }
