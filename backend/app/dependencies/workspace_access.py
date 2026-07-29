"""FastAPI permission seam over WorkspaceAccessControlFacade."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException

from backend.app.dependencies.auth import AuthContext, get_current_identity
from backend.app.services.workspace_access_control.contracts import (
    EffectiveAccessContext,
    VerifiedIdentity,
)
from backend.app.services.workspace_access_control.errors import AccessDeniedError
from backend.app.services.workspace_access_control.facade import (
    WorkspaceAccessControlFacade,
)


def verified_identity_from_auth(auth: AuthContext) -> VerifiedIdentity:
    provider = auth.identity_provider or (
        "cloud-integration" if auth.is_cloud_mode else "local"
    )
    issuer = auth.identity_issuer or (
        auth.tenant_id if auth.is_cloud_mode else "local-core"
    )
    subject = auth.identity_subject or auth.user_id
    if not provider or not issuer or not subject:
        raise HTTPException(status_code=401, detail="verified_identity_required")
    return VerifiedIdentity(
        provider=provider,
        issuer=issuer,
        subject=subject,
        verified_email=auth.verified_email,
    )


def require_workspace_permission(
    permission: str,
) -> Callable[..., EffectiveAccessContext]:
    async def dependency(
        workspace_id: str,
        auth: AuthContext = Depends(get_current_identity),
    ) -> EffectiveAccessContext:
        identity = verified_identity_from_auth(auth)
        context = WorkspaceAccessControlFacade().resolve_effective_access(
            identity=identity,
            workspace_id=workspace_id,
        )
        if not context.allows(permission):
            raise HTTPException(status_code=403, detail="workspace_access_denied")
        return context

    return dependency


def require_local_core_permission(
    permission: str,
) -> Callable[..., EffectiveAccessContext]:
    async def dependency(
        auth: AuthContext = Depends(get_current_identity),
    ) -> EffectiveAccessContext:
        identity = verified_identity_from_auth(auth)
        context = WorkspaceAccessControlFacade().resolve_effective_access(
            identity=identity,
            workspace_id=None,
        )
        if not context.allows(permission):
            raise HTTPException(status_code=403, detail="local_core_access_denied")
        return context

    return dependency


def require_permission(
    context: EffectiveAccessContext,
    permission: str,
) -> None:
    if not context.allows(permission):
        raise AccessDeniedError()
