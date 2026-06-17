"""Workspace task route facade."""

from fastapi import APIRouter

from .tasks_core.control_routes import router as control_router
from .tasks_core.execution_routes import router as execution_router
from .tasks_core.progress_snapshot_routes import router as progress_snapshot_router
from .tasks_core.stream_routes import router as stream_router
from .tasks_core.task_list_routes import router as task_list_router

router = APIRouter()
router.include_router(task_list_router)
router.include_router(execution_router)
router.include_router(progress_snapshot_router)
router.include_router(stream_router)
router.include_router(control_router)
