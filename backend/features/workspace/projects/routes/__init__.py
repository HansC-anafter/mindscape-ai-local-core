from fastapi import APIRouter
from .crud import router as crud_router
from .execution import router as execution_router
from .stats import router as stats_router

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspace-projects"])

router.include_router(crud_router)
router.include_router(execution_router)
router.include_router(stats_router)
