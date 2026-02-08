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
from .projects import router as projects_router
from .flows.routes import router as flows_router
from .threads import router as threads_router

# mindscape_graph module was removed - graph functionality moved elsewhere
from .workspace_indexing import router as workspace_indexing_router

router = APIRouter()

router.include_router(timeline_router)
router.include_router(chat_router)
router.include_router(background_routines_router)
router.include_router(executions_router)
router.include_router(artifacts_router)
router.include_router(projects_router)
router.include_router(flows_router)
router.include_router(threads_router)
# router.include_router(mindscape_graph_router)  # Disabled - module removed
router.include_router(workspace_indexing_router)
