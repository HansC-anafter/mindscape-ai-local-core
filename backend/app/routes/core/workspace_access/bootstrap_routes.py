"""Loopback-only bootstrap/import seam; never a human authorization actor."""

from fastapi import APIRouter, Depends

from backend.app.dependencies.auth import (
    AuthContext,
    get_current_operator,
    get_default_user_id,
)
from backend.app.services.workspace_access_control.facade import (
    WorkspaceAccessControlFacade,
)


router = APIRouter(prefix="/api/v1/access-control", tags=["access-control"])
facade = WorkspaceAccessControlFacade()


@router.post("/bootstrap")
def bootstrap_access_control(
    _operator: AuthContext = Depends(get_current_operator),
):
    return facade.bootstrap_local_state(local_user_id=get_default_user_id())
