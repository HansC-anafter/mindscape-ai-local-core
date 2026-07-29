"""Authenticated self-service invitation acceptance."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from backend.app.dependencies.auth import AuthContext, get_current_identity
from backend.app.dependencies.workspace_access import verified_identity_from_auth
from backend.app.services.workspace_access_control.errors import (
    WorkspaceAccessControlError,
)
from backend.app.services.workspace_access_control.facade import (
    WorkspaceAccessControlFacade,
)

from .error_mapping import raise_http_error
from .schemas import InvitationAcceptCommand


router = APIRouter(prefix="/api/v1/access-control", tags=["access-control"])
facade = WorkspaceAccessControlFacade()


@router.post("/invitations/accept")
def accept_invitation(
    command: InvitationAcceptCommand,
    request: Request,
    response: Response,
    auth: AuthContext = Depends(get_current_identity),
):
    if (
        request.headers.get("origin")
        != "https://remote-workbench.mindscapeai.app"
        or request.headers.get("x-mindscape-remote-ingress")
        != "remote_workbench"
    ):
        raise HTTPException(status_code=403, detail="remote_origin_forbidden")
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    try:
        return facade.accept_invitation(
            raw_token=command.invitation_token,
            identity=verified_identity_from_auth(auth),
        )
    except WorkspaceAccessControlError as error:
        raise_http_error(error)
