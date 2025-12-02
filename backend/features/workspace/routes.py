"""
Workspace Feature Routes

Unified router that combines all workspace feature routes.
This is the entry point for pack registry to load workspace features.
"""

from fastapi import APIRouter
from .timeline import router as timeline_router
from .chat import router as chat_router
from .background_routines import router as background_routines_router
from .executions import router as executions_router
from .artifacts import router as artifacts_router

router = APIRouter()

router.include_router(timeline_router)
router.include_router(chat_router)
router.include_router(background_routines_router)
router.include_router(executions_router)
router.include_router(artifacts_router)

