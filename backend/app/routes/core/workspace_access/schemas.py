"""HTTP-only request contracts for access-control routes."""

from pydantic import BaseModel, Field

from backend.app.services.workspace_access_control.contracts import (
    GrantChangeCommand,
    InvitationAcceptCommand,
    InvitationCreateCommand,
)


class WorkspaceInvitationRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    role_key: str = Field(min_length=1, max_length=64)
    expected_revision: int = Field(ge=0)
    expires_in_days: int = Field(default=7, ge=1, le=30)

    def to_command(self, workspace_id: str) -> InvitationCreateCommand:
        return InvitationCreateCommand(
            scope_type="workspace",
            scope_id=workspace_id,
            email=self.email,
            role_key=self.role_key,
            expected_revision=self.expected_revision,
            expires_in_days=self.expires_in_days,
        )


class LocalCoreInvitationRequest(WorkspaceInvitationRequest):
    def to_command(self) -> InvitationCreateCommand:
        return InvitationCreateCommand(
            scope_type="local_core",
            scope_id="local-core",
            email=self.email,
            role_key=self.role_key,
            expected_revision=self.expected_revision,
            expires_in_days=self.expires_in_days,
        )


class WorkspaceGrantRequest(BaseModel):
    role_key: str = Field(min_length=1, max_length=64)
    expected_revision: int = Field(ge=1)

    def to_command(
        self,
        *,
        principal_id: str,
        workspace_id: str,
    ) -> GrantChangeCommand:
        return GrantChangeCommand(
            principal_id=principal_id,
            scope_type="workspace",
            scope_id=workspace_id,
            role_key=self.role_key,
            expected_revision=self.expected_revision,
        )


__all__ = [
    "InvitationAcceptCommand",
    "LocalCoreInvitationRequest",
    "WorkspaceGrantRequest",
    "WorkspaceInvitationRequest",
]
