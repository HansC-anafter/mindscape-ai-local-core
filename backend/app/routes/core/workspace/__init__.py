from fastapi import APIRouter
from . import (
    crud,
    launchpad,
    files,
    intents,
    tasks,
    workbench,
    health,
    profiles,
    runtime,
    pinned,
)

# Initialize the main workspace router
# This router will be imported by the application/pack registry
router = APIRouter(prefix="/api/v1/workspaces", tags=["workspaces"])

# Mount sub-routers
# Note: These sub-routers define their own paths relative to the prefix (usually empty or specific subpaths)
router.include_router(crud.router)
router.include_router(launchpad.router)
router.include_router(files.router)
router.include_router(intents.router)
router.include_router(tasks.router)
router.include_router(workbench.router)
router.include_router(health.router)
router.include_router(profiles.router)
router.include_router(runtime.router)
router.include_router(pinned.router)

# Import and mount workspace governance router
# This was previously in workspace.py at the end
# workspace_governance.py is in backend/app/routes/core/
from .. import workspace_governance

router.include_router(workspace_governance.router)
