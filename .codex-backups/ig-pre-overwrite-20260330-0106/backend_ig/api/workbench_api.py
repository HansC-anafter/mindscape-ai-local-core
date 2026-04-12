"""
IG Workbench sidebar summary API.

Phase A target:
- keep only running debug cards in the sidebar
- move backlog/total information to lightweight highlight cards
- avoid the heavyweight core executions list route
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from capabilities.ig.services.confirmed_targets import load_confirmed_targets_total

logger = logging.getLogger(__name__)

router = APIRouter(tags=["IG Workbench"])

_ACTIVE_STATUSES = ("running", "queued", "pending", "paused")
_ACTIVE_STATUS_ORDER = {
    "running": 0,
    "queued": 1,
    "paused": 2,
    "pending": 3,
}
_INPUT_KEYS = {
    "post_path",
    "profile_name",
    "reference_id",
    "run_mode",
    "seed",
    "source_handle",
    "target_handle",
    "target_username",
    "trigger",
    "user_data_dir",
    "visit_account_pages",
}
_CTX_KEYS = {
    "playbook_code",
    "runner_lock_key",
    "runner_skip_conflict_lock_key",
    "runner_skip_lock_key",
    "runner_skip_owner",
    "runner_skip_reason",
    "target_username",
    "trigger",
}
_COMPLETED_STATUSES = ("SUCCEEDED", "COMPLETED")
_FAILED_STATUSES = ("FAILED", "CANCELLED", "CANCELLED_BY_USER", "EXPIRED")


class VisionRuntimePolicyRequest(BaseModel):
    workspace_id: str
    vision_execution_mode: str = "local"
    vision_target_device_id: str | None = None


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _normalize_status(value: Any) -> str:
    if hasattr(value, "value"):
        value = value.value
    return str(value or "").strip().upper()


def _status_bucket(value: Any) -> str:
    normalized = _normalize_status(value)
    if normalized in _COMPLETED_STATUSES:
        return "completed"
    if normalized in _FAILED_STATUSES:
        return "failed"
    if normalized == "RUNNING":
        return "running"
    if normalized in {"PENDING", "QUEUED", "PAUSED"}:
        return "pending"
    return "other"


def _build_minimal_execution_context(value: Any) -> Dict[str, Any]:
    ctx = _as_dict(value)
    inputs = _as_dict(ctx.get("inputs"))

    minimal_inputs = {
        key: inputs[key]
        for key in _INPUT_KEYS
        if key in inputs and inputs.get(key) not in (None, "", [], {})
    }
    minimal_ctx = {
        key: ctx[key]
        for key in _CTX_KEYS
        if key in ctx and ctx.get(key) not in (None, "", [], {})
    }
    if minimal_inputs:
        minimal_ctx["inputs"] = minimal_inputs
    return minimal_ctx


def _build_run_info_from_row(row: Dict[str, Any]) -> Dict[str, Any]:
    status_text = str(row.get("status") or "").strip().lower()
    return {
        "id": row.get("id"),
        "execution_id": row.get("execution_id") or row.get("id"),
        "parent_execution_id": row.get("parent_execution_id"),
        "playbook_code": row.get("pack_id"),
        "status": status_text,
        "created_at": row.get("created_at"),
        "started_at": row.get("started_at"),
        "completed_at": row.get("completed_at"),
        "task": {
            "created_at": row.get("created_at"),
            "started_at": row.get("started_at"),
            "error": row.get("error"),
        },
        "failure_reason": row.get("error"),
        "execution_context": _build_minimal_execution_context(
            row.get("execution_context")
        ),
    }


def _load_reference_counts(workspace_id: str) -> Dict[str, int]:
    from capabilities.ig.api.references_api import (
        _apply_live_reference_state,
        _load_latest_reference_analysis_tasks,
    )
    from capabilities.ig.services.reference_index import ReferenceIndex
    from capabilities.ig.services.workspace_storage import WorkspaceStorage

    storage = WorkspaceStorage(workspace_id, "ig")
    refs_path = storage.get_references_path()
    index = ReferenceIndex(refs_path)
    data = index._read_index()
    count_reference_ids: set[str] = set()
    counts = {"total": 0, "completed": 0, "running": 0, "pending": 0, "failed": 0}

    for entry in index._iter_filtered_entries(data):
        counts["total"] += 1
        reference_id = str(entry.get("reference_id") or "").strip()
        status = _normalize_status(entry.get("analysis_status"))
        if status != "COMPLETED" and reference_id:
            count_reference_ids.add(reference_id)
        if status == "COMPLETED":
            counts["completed"] += 1
        elif status == "RUNNING":
            counts["running"] += 1
        elif status == "FAILED":
            counts["failed"] += 1
        else:
            counts["pending"] += 1

    if not count_reference_ids or len(count_reference_ids) > 200:
        return counts

    count_live_task_states = _load_latest_reference_analysis_tasks(
        workspace_id,
        count_reference_ids,
    )

    reconciled_counts = {"total": 0, "completed": 0, "running": 0, "pending": 0, "failed": 0}
    for entry in index._iter_filtered_entries(data):
        reconciled_counts["total"] += 1
        reference_id = str(entry.get("reference_id") or "").strip()
        resolved = _apply_live_reference_state(
            entry,
            count_live_task_states.get(reference_id),
        )
        status = _normalize_status(resolved.get("analysis_status"))
        if status == "COMPLETED":
            reconciled_counts["completed"] += 1
        elif status == "RUNNING":
            reconciled_counts["running"] += 1
        elif status == "FAILED":
            reconciled_counts["failed"] += 1
        else:
            reconciled_counts["pending"] += 1

    return reconciled_counts


def _load_targets_total(workspace_id: str) -> int:
    from sqlalchemy import text

    from backend.app.services.stores.tasks_store import TasksStore

    tasks_store = TasksStore()
    with tasks_store.get_connection() as conn:
        total = load_confirmed_targets_total(
            conn,
            workspace_id=workspace_id,
        )
        if total is None:
            from capabilities.ig.source_filters import confirmed_target_condition_sql

            query = f"""
                SELECT COUNT(DISTINCT a.handle)
                FROM ig_accounts_flat a
                WHERE a.workspace_id = :workspace_id
                  AND {confirmed_target_condition_sql("a")}
            """
            total = (
                conn.execute(text(query), {"workspace_id": workspace_id}).scalar() or 0
            )
    return int(total)


def _load_active_executions(
    workspace_id: str,
    *,
    playbook_code_prefix: Optional[str],
    limit: int,
) -> List[Dict[str, Any]]:
    from sqlalchemy import text

    from backend.app.services.stores.tasks_store import TasksStore

    tasks_store = TasksStore()
    query = """
        SELECT
            id,
            execution_id,
            parent_execution_id,
            pack_id,
            status,
            created_at,
            started_at,
            completed_at,
            error,
            execution_context
        FROM tasks
        WHERE workspace_id = :workspace_id
          AND lower(status) IN ('running', 'queued', 'pending', 'paused')
          AND COALESCE(blocked_reason, '') <> 'admission_deferred'
          AND NOT (
              lower(status) <> 'running'
              AND pack_id = 'ig_analyze_pinned_reference'
          )
    """
    params: Dict[str, Any] = {"workspace_id": workspace_id, "limit": limit}
    if playbook_code_prefix:
        query += " AND pack_id LIKE :pack_prefix"
        params["pack_prefix"] = f"{playbook_code_prefix}%"
    query += """
        ORDER BY
            CASE lower(status)
                WHEN 'running' THEN 0
                WHEN 'queued' THEN 1
                WHEN 'paused' THEN 2
                WHEN 'pending' THEN 3
                ELSE 4
            END,
            COALESCE(started_at, created_at) DESC
        LIMIT :limit
    """

    with tasks_store.get_connection() as conn:
        rows = conn.execute(text(query), params).mappings().all()

    projected: List[Dict[str, Any]] = [_build_run_info_from_row(dict(row)) for row in rows]

    projected.sort(
        key=lambda item: (
            _ACTIVE_STATUS_ORDER.get((item.get("status") or "").lower(), 99),
            -(
                (
                    item.get("started_at")
                    or item.get("created_at")
                    or ""
                ).timestamp()
                if hasattr(item.get("started_at") or item.get("created_at"), "timestamp")
                else 0
            ),
        )
    )
    return projected


def _load_queue_groups(
    workspace_id: str,
    *,
    playbook_code_prefix: Optional[str],
    limit: int,
    offset: int,
) -> Dict[str, Any]:
    from sqlalchemy import text

    from backend.app.services.stores.tasks_store import TasksStore

    tasks_store = TasksStore()
    filter_sql = """
        FROM tasks
        WHERE workspace_id = :workspace_id
          AND parent_execution_id IS NOT NULL
    """
    params: Dict[str, Any] = {
        "workspace_id": workspace_id,
        "limit": limit,
        "offset": offset,
    }
    if playbook_code_prefix:
        filter_sql += " AND pack_id LIKE :pack_prefix"
        params["pack_prefix"] = f"{playbook_code_prefix}%"

    total_sql = f"SELECT COUNT(DISTINCT parent_execution_id) {filter_sql}"
    groups_sql = f"""
        WITH filtered AS (
            SELECT
                id,
                parent_execution_id,
                status,
                created_at,
                started_at,
                COALESCE(started_at, created_at) AS sort_at
            {filter_sql}
        ),
        grouped AS (
            SELECT
                parent_execution_id,
                COUNT(*) AS total,
                SUM(CASE WHEN upper(status) IN ('SUCCEEDED', 'COMPLETED') THEN 1 ELSE 0 END) AS completed,
                SUM(CASE WHEN upper(status) IN ('FAILED', 'CANCELLED', 'CANCELLED_BY_USER', 'EXPIRED') THEN 1 ELSE 0 END) AS failed,
                SUM(CASE WHEN upper(status) = 'RUNNING' THEN 1 ELSE 0 END) AS running,
                SUM(CASE WHEN upper(status) IN ('PENDING', 'QUEUED', 'PAUSED') THEN 1 ELSE 0 END) AS pending,
                MAX(sort_at) AS latest_at
            FROM filtered
            GROUP BY parent_execution_id
        ),
        paged AS (
            SELECT *
            FROM grouped
            ORDER BY latest_at DESC
            LIMIT :limit OFFSET :offset
        ),
        ranked AS (
            SELECT
                id,
                parent_execution_id,
                ROW_NUMBER() OVER (
                    PARTITION BY parent_execution_id
                    ORDER BY sort_at DESC, created_at DESC, id DESC
                ) AS rn
            FROM filtered
        )
        SELECT
            paged.parent_execution_id,
            paged.total,
            paged.completed,
            paged.failed,
            paged.running,
            paged.pending,
            paged.latest_at,
            t.id,
            t.execution_id,
            t.pack_id,
            t.status,
            t.created_at,
            t.started_at,
            t.completed_at,
            t.error,
            t.execution_context
        FROM paged
        JOIN ranked
          ON ranked.parent_execution_id = paged.parent_execution_id
         AND ranked.rn = 1
        JOIN tasks t
          ON t.id = ranked.id
        ORDER BY paged.latest_at DESC
    """
    ungrouped_sql = f"""
        SELECT
            id,
            execution_id,
            parent_execution_id,
            pack_id,
            status,
            created_at,
            started_at,
            completed_at,
            error,
            execution_context
        {filter_sql.replace('AND parent_execution_id IS NOT NULL', 'AND parent_execution_id IS NULL')}
        ORDER BY COALESCE(started_at, created_at) DESC
        LIMIT 10
    """

    with tasks_store.get_connection() as conn:
        total_groups = conn.execute(text(total_sql), params).scalar() or 0
        group_rows = conn.execute(text(groups_sql), params).mappings().all()
        ungrouped_rows = conn.execute(text(ungrouped_sql), params).mappings().all()

    groups: List[Dict[str, Any]] = []
    for row in group_rows:
        groups.append(
            {
                "parent_execution_id": row.get("parent_execution_id"),
                "summary": {
                    "total": int(row.get("total") or 0),
                    "completed": int(row.get("completed") or 0),
                    "failed": int(row.get("failed") or 0),
                    "running": int(row.get("running") or 0),
                    "pending": int(row.get("pending") or 0),
                },
                "latest_at": row.get("latest_at"),
                "representative_run": _build_run_info_from_row(dict(row)),
            }
        )

    ungrouped = [_build_run_info_from_row(dict(row)) for row in ungrouped_rows]
    return {
        "groups": groups,
        "total_groups": int(total_groups),
        "offset": offset,
        "limit": limit,
        "returned_groups": len(groups),
        "has_more_groups": offset + len(groups) < int(total_groups),
        "ungrouped": ungrouped,
    }


def _load_queue_group_children(
    workspace_id: str,
    *,
    parent_execution_id: str,
    playbook_code_prefix: Optional[str],
    limit: int,
    offset: int,
) -> Dict[str, Any]:
    from sqlalchemy import text

    from backend.app.services.stores.tasks_store import TasksStore

    tasks_store = TasksStore()
    filter_sql = """
        FROM tasks
        WHERE workspace_id = :workspace_id
          AND parent_execution_id = :parent_execution_id
    """
    params: Dict[str, Any] = {
        "workspace_id": workspace_id,
        "parent_execution_id": parent_execution_id,
        "limit": limit,
        "offset": offset,
    }
    if playbook_code_prefix:
        filter_sql += " AND pack_id LIKE :pack_prefix"
        params["pack_prefix"] = f"{playbook_code_prefix}%"

    total_sql = f"SELECT COUNT(*) {filter_sql}"
    children_sql = f"""
        SELECT
            id,
            execution_id,
            parent_execution_id,
            pack_id,
            status,
            created_at,
            started_at,
            completed_at,
            error,
            execution_context
        {filter_sql}
        ORDER BY COALESCE(started_at, created_at) DESC
        LIMIT :limit OFFSET :offset
    """
    with tasks_store.get_connection() as conn:
        total_children = conn.execute(text(total_sql), params).scalar() or 0
        child_rows = conn.execute(text(children_sql), params).mappings().all()

    executions = [_build_run_info_from_row(dict(row)) for row in child_rows]
    return {
        "parent_execution_id": parent_execution_id,
        "executions": executions,
        "total": int(total_children),
        "offset": offset,
        "limit": limit,
        "returned": len(executions),
        "has_more": offset + len(executions) < int(total_children),
    }


@router.get("/sidebar-summary")
async def get_sidebar_summary(
    workspace_id: str = Query(..., description="Workspace ID"),
    playbook_code_prefix: str = Query("ig_", description="Filter active executions by playbook code prefix"),
    active_limit: int = Query(100, ge=1, le=200, description="Maximum active executions to include"),
):
    try:
        counts = _load_reference_counts(workspace_id)
        active_executions = _load_active_executions(
            workspace_id,
            playbook_code_prefix=playbook_code_prefix,
            limit=active_limit,
        )
        return {
            "counts": counts,
            "active_executions": active_executions,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("[IG Workbench] Failed to build sidebar summary: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to build workbench sidebar summary")


@router.get("/runtime-policy")
async def get_runtime_policy(
    workspace_id: str = Query(..., description="Workspace ID"),
):
    try:
        from capabilities.ig.services.vision_runtime_policy import (
            load_workspace_vision_runtime_policy,
        )

        return load_workspace_vision_runtime_policy(workspace_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "[IG Workbench] Failed to load runtime policy: %s",
            exc,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Failed to load runtime policy")


@router.put("/runtime-policy")
async def put_runtime_policy(req: VisionRuntimePolicyRequest):
    try:
        from capabilities.ig.services.vision_runtime_policy import (
            save_workspace_vision_runtime_policy,
        )

        return save_workspace_vision_runtime_policy(
            req.workspace_id,
            vision_execution_mode=req.vision_execution_mode,
            vision_target_device_id=req.vision_target_device_id,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "[IG Workbench] Failed to save runtime policy: %s",
            exc,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Failed to save runtime policy")


@router.get("/sidebar-targets-total")
async def get_sidebar_targets_total(
    workspace_id: str = Query(..., description="Workspace ID"),
):
    try:
        return {"total": _load_targets_total(workspace_id)}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("[IG Workbench] Failed to load sidebar targets total: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to load sidebar targets total")


@router.get("/queue-groups")
async def get_queue_groups(
    workspace_id: str = Query(..., description="Workspace ID"),
    playbook_code_prefix: str = Query("ig_", description="Filter by playbook code prefix"),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of queue groups to include"),
    offset: int = Query(0, ge=0, description="Queue group offset"),
):
    try:
        return _load_queue_groups(
            workspace_id,
            playbook_code_prefix=playbook_code_prefix,
            limit=limit,
            offset=offset,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("[IG Workbench] Failed to load queue groups: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to load IG queue groups")


@router.get("/queue-groups/{parent_execution_id}/children")
async def get_queue_group_children(
    parent_execution_id: str,
    workspace_id: str = Query(..., description="Workspace ID"),
    playbook_code_prefix: str = Query("ig_", description="Filter by playbook code prefix"),
    limit: int = Query(20, ge=1, le=100, description="Maximum child executions to include"),
    offset: int = Query(0, ge=0, description="Child execution offset"),
):
    try:
        return _load_queue_group_children(
            workspace_id,
            parent_execution_id=parent_execution_id,
            playbook_code_prefix=playbook_code_prefix,
            limit=limit,
            offset=offset,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("[IG Workbench] Failed to load queue group children: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to load IG queue group children")
