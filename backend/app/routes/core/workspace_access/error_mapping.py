"""Map typed facade failures without leaking database details."""

from fastapi import HTTPException

from backend.app.services.workspace_access_control.errors import (
    AccessDeniedError,
    AccessRevisionConflictError,
    InvitationEmailMismatchError,
    InvitationExpiredError,
    InvitationInvalidError,
    LastAdministratorError,
    LastOwnerError,
    WorkspaceAccessControlError,
)


def raise_http_error(error: WorkspaceAccessControlError) -> None:
    if isinstance(error, AccessRevisionConflictError):
        raise HTTPException(status_code=409, detail=error.code) from error
    if isinstance(error, (LastOwnerError, LastAdministratorError)):
        raise HTTPException(status_code=409, detail=error.code) from error
    if isinstance(error, (InvitationInvalidError, InvitationExpiredError)):
        raise HTTPException(status_code=410, detail=error.code) from error
    if isinstance(error, InvitationEmailMismatchError):
        raise HTTPException(status_code=403, detail=error.code) from error
    if isinstance(error, AccessDeniedError):
        raise HTTPException(status_code=403, detail=error.code) from error
    raise HTTPException(status_code=400, detail=error.code) from error
