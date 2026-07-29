"""Typed access-control failures mapped by the HTTP adapter."""


class WorkspaceAccessControlError(RuntimeError):
    code = "workspace_access_control_error"

    def __init__(self, message: str | None = None):
        super().__init__(message or self.code)


class AccessDeniedError(WorkspaceAccessControlError):
    code = "access_denied"


class AccessRevisionConflictError(WorkspaceAccessControlError):
    code = "access_revision_conflict"


class InvitationInvalidError(WorkspaceAccessControlError):
    code = "invitation_invalid"


class InvitationExpiredError(WorkspaceAccessControlError):
    code = "invitation_expired"


class InvitationEmailMismatchError(WorkspaceAccessControlError):
    code = "invitation_email_mismatch"


class LastOwnerError(WorkspaceAccessControlError):
    code = "last_workspace_owner"


class LastAdministratorError(WorkspaceAccessControlError):
    code = "last_local_core_super_admin"
