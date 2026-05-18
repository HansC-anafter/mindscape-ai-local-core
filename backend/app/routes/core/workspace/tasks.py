import asyncio
import logging
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi import Path as PathParam
from fastapi.encoders import jsonable_encoder

from ....services.json_safety import json_value_without_nul
from ....services.runner_resources import (
    PROGRESS_SNAPSHOT_TTL_SECONDS,
    RedisTtlSnapshotStore,
    build_progress_snapshot_key,
    get_ttl_snapshot,
    set_ttl_snapshot,
)
from ....services.stores.postgres.task_projection_store import TasksProjectionStore
from ....services.stores.redis.runner_queue_store import RedisRunnerQueueStore
from ....services.task_execution_projection import (
    build_execution_group_summary,
    project_execution_for_api,
)
from ..read_executor import run_ui_read
from .tasks_core.control_routes import router as control_router
from .tasks_core.progress_snapshot import (
    load_execution_progress_snapshot_payload,
)
from .tasks_core.stream_routes import router as stream_router

router = APIRouter()
logger = logging.getLogger(__name__)
_WORKSPACE_TASKS_CACHE_TTL_SECONDS = 2.0
_WORKSPACE_TASKS_INFLIGHT_TIMEOUT_SECONDS = 18.0
_PROGRESS_SNAPSHOT_CACHE_TTL_SECONDS = float(PROGRESS_SNAPSHOT_TTL_SECONDS)
_WORKSPACE_TASKS_CACHE: dict[tuple[Any, ...], tuple[float, Dict[str, Any]]] = {}
_WORKSPACE_TASKS_INFLIGHT: dict[tuple[Any, ...], asyncio.Task[Dict[str, Any]]] = {}
_WORKSPACE_TASKS_CACHE_LOCK = asyncio.Lock()
_PROGRESS_SNAPSHOT_CACHE: dict[tuple[str, str], tuple[float, Dict[str, Any]]] = {}
_PROGRESS_SNAPSHOT_INFLIGHT: dict[tuple[str, str], asyncio.Task[Dict[str, Any]]] = {}
_PROGRESS_SNAPSHOT_CACHE_LOCK = asyncio.Lock()
_PROGRESS_SNAPSHOT_STORE = RedisTtlSnapshotStore(
    RedisRunnerQueueStore(pack_id="progress_snapshot")
)


def _workspace_tasks_cache_key(
    workspace_id: str,
    limit: int,
    include_completed: bool,
    task_type: Optional[str],
) -> tuple[Any, ...]:
    return (
        workspace_id,
        int(limit),
        bool(include_completed),
        (task_type or "").strip().lower(),
    )


async def _load_workspace_tasks_payload(
    workspace_id: str,
    limit: int,
    include_completed: bool,
    task_type: Optional[str],
) -> Dict[str, Any]:
    projection_store = TasksProjectionStore()
    tasks = await run_ui_read(
        projection_store.list_workspace_tasks,
        workspace_id,
        limit,
        include_completed,
        task_type,
    )
    return {"tasks": tasks}


@router.get("/{workspace_id}/tasks")
async def get_workspace_tasks(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of tasks"),
    include_completed: bool = Query(False, description="Include completed tasks"),
    task_type: Optional[str] = Query(None, description="Optional task type filter"),
):
    """Get tasks for a workspace"""
    cache_key = _workspace_tasks_cache_key(
        workspace_id,
        limit,
        include_completed,
        task_type,
    )
    try:
        now = time.monotonic()
        async with _WORKSPACE_TASKS_CACHE_LOCK:
            cached = _WORKSPACE_TASKS_CACHE.get(cache_key)
            if cached and now - cached[0] < _WORKSPACE_TASKS_CACHE_TTL_SECONDS:
                return cached[1]

            task = _WORKSPACE_TASKS_INFLIGHT.get(cache_key)
            if task is None:
                task = asyncio.create_task(
                    _load_workspace_tasks_payload(
                        workspace_id,
                        limit,
                        include_completed,
                        task_type,
                    )
                )
                _WORKSPACE_TASKS_INFLIGHT[cache_key] = task

        try:
            payload = await asyncio.wait_for(
                task,
                timeout=_WORKSPACE_TASKS_INFLIGHT_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            async with _WORKSPACE_TASKS_CACHE_LOCK:
                if _WORKSPACE_TASKS_INFLIGHT.get(cache_key) is task:
                    _WORKSPACE_TASKS_INFLIGHT.pop(cache_key, None)
            task.cancel()
            raise HTTPException(
                status_code=504,
                detail="Workspace tasks request timed out",
            )

        async with _WORKSPACE_TASKS_CACHE_LOCK:
            if _WORKSPACE_TASKS_INFLIGHT.get(cache_key) is task:
                _WORKSPACE_TASKS_INFLIGHT.pop(cache_key, None)
            _WORKSPACE_TASKS_CACHE[cache_key] = (time.monotonic(), payload)

        return payload
    except HTTPException:
        raise
    except Exception as e:
        async with _WORKSPACE_TASKS_CACHE_LOCK:
            _WORKSPACE_TASKS_INFLIGHT.pop(cache_key, None)
        logger.error(f"Failed to get workspace tasks: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{workspace_id}/executions")
async def get_workspace_executions(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    limit: int = Query(30, ge=1, le=200, description="Maximum number of executions"),
    playbook_code_prefix: Optional[str] = Query(
        None, description="Filter by playbook code prefix (e.g., 'ig_')"
    ),
    playbook_code: Optional[str] = Query(
        None, description="Filter by exact playbook code"
    ),
    parent_execution_id: Optional[str] = Query(
        None,
        description="Filter child executions by exact parent execution ID",
    ),
    order_by: str = Query("created_at", description="Field to order by"),
    order: str = Query("desc", description="Sort order: asc or desc"),
    include_execution_context: bool = Query(
        False,
        description=(
            "Legacy parameter. Execution lists always return compact projection context."
        ),
    ),
    group_by_parent: bool = Query(
        False, description="Group results by parent_execution_id"
    ),
):
    """List executions (tasks) for a workspace with optional playbook filters."""
    try:
        projection_store = TasksProjectionStore()
        task_payloads = await run_ui_read(
            projection_store.list_workspace_executions,
            workspace_id,
            limit,
            playbook_code=playbook_code,
            playbook_code_prefix=playbook_code_prefix,
            parent_execution_id=parent_execution_id,
            order_by=order_by,
            order=order,
        )

        executions = []
        for task_payload in task_payloads:
            executions.append(
                project_execution_for_api(
                    task_payload,
                    queue_position=None,
                    queue_total=None,
                )
            )

        if group_by_parent:
            groups = {}
            ungrouped = []
            for d in executions:
                pid = d.get("parent_execution_id")
                if pid:
                    groups.setdefault(pid, []).append(d)
                else:
                    ungrouped.append(d)

            group_summaries = []
            for pid, tasks_list in groups.items():
                group_summaries.append(
                    {
                        "parent_execution_id": pid,
                        "tasks": tasks_list,
                        "summary": build_execution_group_summary(tasks_list),
                    }
                )
            return {"groups": group_summaries, "ungrouped": ungrouped}

        return {"executions": executions}
    except Exception as e:
        logger.error(f"Failed to get workspace executions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def _load_execution_progress_snapshot_payload(
    workspace_id: str,
    execution_id: str,
) -> Dict[str, Any]:
    _ = json_value_without_nul
    return load_execution_progress_snapshot_payload(workspace_id, execution_id)


async def _read_progress_snapshot_hot_cache(
    workspace_id: str,
    execution_id: str,
) -> Optional[Dict[str, Any]]:
    try:
        return await get_ttl_snapshot(
            _PROGRESS_SNAPSHOT_STORE,
            build_progress_snapshot_key(workspace_id, execution_id),
        )
    except Exception:
        return None


async def _write_progress_snapshot_hot_cache(
    workspace_id: str,
    execution_id: str,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    encoded_payload = jsonable_encoder(payload)
    if not isinstance(encoded_payload, dict):
        return payload
    try:
        await set_ttl_snapshot(
            _PROGRESS_SNAPSHOT_STORE,
            build_progress_snapshot_key(workspace_id, execution_id),
            encoded_payload,
            ttl_seconds=PROGRESS_SNAPSHOT_TTL_SECONDS,
        )
    except Exception:
        pass
    return encoded_payload


@router.get("/{workspace_id}/executions/{execution_id}/progress-snapshot")
async def get_execution_progress_snapshot(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    execution_id: str = PathParam(..., description="Execution ID"),
):
    """Return a lightweight progress snapshot for one execution."""
    cache_key = (workspace_id, execution_id)
    try:
        hot_cached = await _read_progress_snapshot_hot_cache(
            workspace_id,
            execution_id,
        )
        if hot_cached:
            return hot_cached

        now = time.monotonic()
        async with _PROGRESS_SNAPSHOT_CACHE_LOCK:
            cached = _PROGRESS_SNAPSHOT_CACHE.get(cache_key)
            if cached and now - cached[0] < _PROGRESS_SNAPSHOT_CACHE_TTL_SECONDS:
                return cached[1]

            task = _PROGRESS_SNAPSHOT_INFLIGHT.get(cache_key)
            if task is None:
                task = asyncio.create_task(
                    run_ui_read(
                        _load_execution_progress_snapshot_payload,
                        workspace_id,
                        execution_id,
                    )
                )
                _PROGRESS_SNAPSHOT_INFLIGHT[cache_key] = task

        payload = await task
        payload = await _write_progress_snapshot_hot_cache(
            workspace_id,
            execution_id,
            payload,
        )

        async with _PROGRESS_SNAPSHOT_CACHE_LOCK:
            if _PROGRESS_SNAPSHOT_INFLIGHT.get(cache_key) is task:
                _PROGRESS_SNAPSHOT_INFLIGHT.pop(cache_key, None)
            _PROGRESS_SNAPSHOT_CACHE[cache_key] = (time.monotonic(), payload)

        return payload
    except HTTPException:
        async with _PROGRESS_SNAPSHOT_CACHE_LOCK:
            _PROGRESS_SNAPSHOT_INFLIGHT.pop(cache_key, None)
        raise
    except Exception as e:
        async with _PROGRESS_SNAPSHOT_CACHE_LOCK:
            _PROGRESS_SNAPSHOT_INFLIGHT.pop(cache_key, None)
        logger.error(
            f"Failed to get execution progress snapshot for {execution_id}: {e}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=str(e))


router.include_router(stream_router)
router.include_router(control_router)
