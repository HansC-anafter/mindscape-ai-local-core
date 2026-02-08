import logging

from fastapi import (
    APIRouter,
    HTTPException,
    Path as PathParam,
    Query,
)

from ....services.mindscape_store import MindscapeStore
from ....services.system_health_checker import SystemHealthChecker

router = APIRouter()
logger = logging.getLogger(__name__)
store = MindscapeStore()


@router.get("/{workspace_id}/health")
async def get_workspace_health(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    profile_id: str = Query("default-user", description="Profile ID"),
):
    """Get health status for a workspace"""
    try:
        health_checker = SystemHealthChecker()
        health = await health_checker.check_workspace_health(profile_id, workspace_id)
        return health
    except Exception as e:
        logger.error(f"Failed to get workspace health: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
