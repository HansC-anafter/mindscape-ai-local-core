from typing import List

from fastapi import APIRouter

from ....models.workspace import Workspace
from . import (
    activity_stream,
    crud,
    launchpad,
    files,
    intents,
    instruction,
    tasks,
    workbench,
    health,
    profiles,
    runtime,
    pinned,
    stubs,
)

# Initialize the main workspace router
# This router will be imported by the application/pack registry
router = APIRouter(prefix="/api/v1/workspaces", tags=["workspaces"])

# Mount sub-routers
# Note: These sub-routers define their own paths relative to the prefix (usually empty or specific subpaths)
router.include_router(crud.router)
router.include_router(activity_stream.router)
router.include_router(launchpad.router)
router.include_router(files.router)
router.include_router(intents.router)
router.include_router(instruction.router)
router.include_router(tasks.router)
router.include_router(workbench.router)
router.include_router(health.router)
router.include_router(profiles.router)
router.include_router(runtime.router)
router.include_router(pinned.router)
router.include_router(stubs.router)

# Allow no-trailing-slash access for workspace collection routes.
# This avoids proxy-induced redirects leaking the internal backend hostname.
router.add_api_route(
    "",
    crud.list_workspaces,
    methods=["GET"],
    response_model=List[Workspace],
    include_in_schema=False,
)
router.add_api_route(
    "",
    crud.create_workspace,
    methods=["POST"],
    response_model=Workspace,
    status_code=201,
    include_in_schema=False,
)

# Import and mount workspace governance router
# This was previously in workspace.py at the end
# workspace_governance.py is in backend/app/routes/core/
from .. import workspace_governance

router.include_router(workspace_governance.router)
