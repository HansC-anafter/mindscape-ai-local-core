"""Resource governance API for global and workspace-scoped runtime control."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from backend.app.dependencies.auth import AuthContext, get_current_user
from backend.app.services.resource_governance import build_resource_governance_context


router = APIRouter(prefix="/api/v1/resource-governance")


@router.get("/context")
async def get_resource_governance_context(
    workspace_id: str | None = Query(default=None),
    mode: str | None = Query(default=None),
    current_user: AuthContext = Depends(get_current_user),
) -> dict:
    return build_resource_governance_context(
        current_user,
        workspace_id=workspace_id,
        requested_mode=mode,
    )
