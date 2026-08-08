"""Local Core and exact-workspace management adapters."""

from fastapi import APIRouter, Depends, Query

from backend.app.dependencies.auth import AuthContext, get_current_identity
from backend.app.dependencies.workspace_access import (
    require_local_core_permission,
    require_workspace_permission,
    verified_identity_from_auth,
)
from backend.app.services.workspace_access_control.catalog import (
    LOCAL_CORE_ACCESS_MANAGE,
    WORKSPACE_MEMBERS_MANAGE,
)
from backend.app.services.workspace_access_control.contracts import (
    EffectiveAccessContext,
)
from backend.app.services.workspace_access_control.errors import (
    WorkspaceAccessControlError,
)
from backend.app.services.workspace_access_control.facade import (
    WorkspaceAccessControlFacade,
)

from .error_mapping import raise_http_error
from .schemas import (
    LocalCoreInvitationRequest,
    WorkspaceGrantRequest,
    WorkspaceInvitationRequest,
)


router = APIRouter(prefix="/api/v1/access-control", tags=["access-control"])
facade = WorkspaceAccessControlFacade()


@router.get("/local-core")
def read_local_core_access(
    limit: int = Query(default=64, ge=1, le=64),
    _access: EffectiveAccessContext = Depends(
        require_local_core_permission(LOCAL_CORE_ACCESS_MANAGE)
    ),
):
    return facade.read_scope(
        scope_type="local_core",
        scope_id="local-core",
        limit=limit,
    )


@router.post("/local-core/invitations")
def invite_local_core_member(
    request: LocalCoreInvitationRequest,
    access: EffectiveAccessContext = Depends(
        require_local_core_permission(LOCAL_CORE_ACCESS_MANAGE)
    ),
):
    try:
        return facade.create_invitation(
            command=request.to_command(),
            actor_principal_id=str(access.principal_id),
        )
    except WorkspaceAccessControlError as error:
        raise_http_error(error)


@router.delete("/local-core/members/{principal_id}")
def revoke_local_core_member(
    principal_id: str,
    expected_revision: int = Query(ge=1),
    access: EffectiveAccessContext = Depends(
        require_local_core_permission(LOCAL_CORE_ACCESS_MANAGE)
    ),
):
    try:
        revision = facade.revoke_grant(
            principal_id=principal_id,
            scope_type="local_core",
            scope_id="local-core",
            expected_revision=expected_revision,
            actor_principal_id=str(access.principal_id),
        )
        return {"revision": revision}
    except WorkspaceAccessControlError as error:
        raise_http_error(error)


@router.get("/workspaces/{workspace_id}")
def read_workspace_access(
    workspace_id: str,
    limit: int = Query(default=64, ge=1, le=64),
    _access: EffectiveAccessContext = Depends(
        require_workspace_permission(WORKSPACE_MEMBERS_MANAGE)
    ),
):
    return facade.read_scope(
        scope_type="workspace",
        scope_id=workspace_id,
        limit=limit,
    )


@router.post("/workspaces/{workspace_id}/invitations")
def invite_workspace_member(
    workspace_id: str,
    request: WorkspaceInvitationRequest,
    access: EffectiveAccessContext = Depends(
        require_workspace_permission(WORKSPACE_MEMBERS_MANAGE)
    ),
):
    try:
        return facade.create_invitation(
            command=request.to_command(workspace_id),
            actor_principal_id=str(access.principal_id),
        )
    except WorkspaceAccessControlError as error:
        raise_http_error(error)


@router.put("/workspaces/{workspace_id}/members/{principal_id}")
def change_workspace_member(
    workspace_id: str,
    principal_id: str,
    request: WorkspaceGrantRequest,
    access: EffectiveAccessContext = Depends(
        require_workspace_permission(WORKSPACE_MEMBERS_MANAGE)
    ),
):
    try:
        revision = facade.change_grant(
            command=request.to_command(
                principal_id=principal_id,
                workspace_id=workspace_id,
            ),
            actor_principal_id=str(access.principal_id),
        )
        return {"revision": revision}
    except WorkspaceAccessControlError as error:
        raise_http_error(error)


@router.delete("/workspaces/{workspace_id}/members/{principal_id}")
def revoke_workspace_member(
    workspace_id: str,
    principal_id: str,
    expected_revision: int = Query(ge=1),
    access: EffectiveAccessContext = Depends(
        require_workspace_permission(WORKSPACE_MEMBERS_MANAGE)
    ),
):
    try:
        revision = facade.revoke_grant(
            principal_id=principal_id,
            scope_type="workspace",
            scope_id=workspace_id,
            expected_revision=expected_revision,
            actor_principal_id=str(access.principal_id),
        )
        return {"revision": revision}
    except WorkspaceAccessControlError as error:
        raise_http_error(error)


@router.get("/workspaces/{workspace_id}/remote-projection")
def read_remote_projection(
    workspace_id: str,
    _access: EffectiveAccessContext = Depends(
        require_workspace_permission(WORKSPACE_MEMBERS_MANAGE)
    ),
):
    return facade.read_remote_identity_projection(workspace_id=workspace_id)
