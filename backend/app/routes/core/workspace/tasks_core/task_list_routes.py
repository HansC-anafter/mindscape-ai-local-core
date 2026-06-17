"""Workspace task list routes and cache state."""

import asyncio
import logging
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi import Path as PathParam

from backend.app.routes.core.read_executor import run_ui_read
from backend.app.services.stores.postgres.task_projection_store import (
    TasksProjectionStore,
)

router = APIRouter()
logger = logging.getLogger(__name__)
_WORKSPACE_TASKS_CACHE_TTL_SECONDS = 2.0
_WORKSPACE_TASKS_INFLIGHT_TIMEOUT_SECONDS = 18.0
_WORKSPACE_TASKS_CACHE: dict[tuple[Any, ...], tuple[float, Dict[str, Any]]] = {}
_WORKSPACE_TASKS_INFLIGHT: dict[tuple[Any, ...], asyncio.Task[Dict[str, Any]]] = {}
_WORKSPACE_TASKS_CACHE_LOCK = asyncio.Lock()


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
) -> Dict[str, Any]:
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
