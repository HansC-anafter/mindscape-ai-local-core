import logging
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
from ....services.readiness_request_coordinator import (
    get_readiness_request_coordinator,
)

router = APIRouter()
logger = logging.getLogger(__name__)
store = MindscapeStore()
_WORKSPACE_HEALTH_CACHE_TTL_SECONDS = 30.0


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
        coordinator = get_readiness_request_coordinator()
        return await coordinator.run(
            key=("workspace-health", profile_id),
            producer=lambda: _compute_workspace_health(profile_id, workspace_id),
            ttl_seconds=_WORKSPACE_HEALTH_CACHE_TTL_SECONDS,
            force=refresh,
        )
    except Exception as e:
        logger.error(f"Failed to get workspace health: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
