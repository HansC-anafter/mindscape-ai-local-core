import logging
import time
import asyncio

from fastapi import (
    APIRouter,
    HTTPException,
    Path as PathParam,
    Query,
)

from ....services.mindscape_store import MindscapeStore
from ....services.system_health_checker import (
    SystemHealthChecker,
    run_readiness_coro_in_worker,
)

router = APIRouter()
logger = logging.getLogger(__name__)
store = MindscapeStore()
_WORKSPACE_HEALTH_CACHE_TTL_SECONDS = 30.0
_WORKSPACE_HEALTH_CACHE_LOCK = asyncio.Lock()
_WORKSPACE_HEALTH_CACHE: dict[tuple[str, str], tuple[float, dict]] = {}
_WORKSPACE_HEALTH_INFLIGHT: dict[tuple[str, str], asyncio.Task] = {}


async def _compute_workspace_health(profile_id: str, workspace_id: str) -> dict:
    health_checker = SystemHealthChecker()
    return await run_readiness_coro_in_worker(
        lambda: health_checker.check_workspace_health(profile_id, workspace_id)
    )


@router.get("/{workspace_id}/health")
async def get_workspace_health(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    profile_id: str = Query("default-user", description="Profile ID"),
    refresh: bool = Query(False, description="Bypass the short readiness cache"),
):
    """Get health status for a workspace"""
    try:
        cache_key = (profile_id, workspace_id)
        existing_to_await = None
        task: asyncio.Task | None = None

        if refresh:
            task = asyncio.create_task(_compute_workspace_health(profile_id, workspace_id))
        else:
            async with _WORKSPACE_HEALTH_CACHE_LOCK:
                cached = _WORKSPACE_HEALTH_CACHE.get(cache_key)
                if cached and time.monotonic() - cached[0] < _WORKSPACE_HEALTH_CACHE_TTL_SECONDS:
                    return cached[1]
                inflight = _WORKSPACE_HEALTH_INFLIGHT.get(cache_key)
                if inflight is not None:
                    existing_to_await = inflight
                else:
                    task = asyncio.create_task(_compute_workspace_health(profile_id, workspace_id))
                    _WORKSPACE_HEALTH_INFLIGHT[cache_key] = task
        if existing_to_await is not None:
            return await existing_to_await
        if task is None:
            raise RuntimeError("workspace_health_task_not_scheduled")

        try:
            health = await task
            async with _WORKSPACE_HEALTH_CACHE_LOCK:
                _WORKSPACE_HEALTH_CACHE[cache_key] = (time.monotonic(), health)
            return health
        finally:
            async with _WORKSPACE_HEALTH_CACHE_LOCK:
                if _WORKSPACE_HEALTH_INFLIGHT.get(cache_key) is task:
                    _WORKSPACE_HEALTH_INFLIGHT.pop(cache_key, None)
    except Exception as e:
        logger.error(f"Failed to get workspace health: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
