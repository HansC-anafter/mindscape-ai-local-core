from fastapi import APIRouter

from .memory_routes import router as memory_router
from .metrics_routes import router as metrics_router

router = APIRouter(prefix="/{workspace_id}/governance", tags=["workspace-governance"])
router.include_router(memory_router)
router.include_router(metrics_router)
