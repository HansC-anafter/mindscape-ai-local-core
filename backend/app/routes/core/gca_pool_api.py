"""
GCA Pool API

REST endpoints for managing the GCA multi-account pool.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

try:
    from ...auth import get_current_user
except ImportError:
    from typing import Any

    async def get_current_user() -> Any:
        """Placeholder for development"""
        return type("User", (), {"id": "dev-user"})()


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/gca-pool", tags=["gca-pool"])


class UpdateAccountRequest(BaseModel):
    enabled: Optional[bool] = None
    priority: Optional[int] = None


def _get_service():
    from backend.app.services.gca_pool_service import GCAPoolService

    return GCAPoolService()


@router.get("")
async def list_pool():
    """List all accounts in the GCA pool."""
    service = _get_service()
    accounts = service.list_pool()
    return {"accounts": accounts, "count": len(accounts)}


@router.get("/workspace-status")
async def workspace_status(
    workspace_id: str = Query(...),
    auth_workspace_id: str | None = Query(None),
    source_workspace_id: str | None = Query(None),
):
    """Return workspace-scoped GCA policy and current pool resolution."""
    from ...services.gca_workspace_resolver import GCAWorkspaceResolver

    service = _get_service()
    try:
        selection = GCAWorkspaceResolver().resolve(
            workspace_id=workspace_id,
            auth_workspace_id=auth_workspace_id,
            source_workspace_id=source_workspace_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    is_pinned = bool(selection.selected_runtime_id)
    preview = service.preview_active_runtime(
        preferred_runtime_id=selection.selected_runtime_id,
        allow_fallback=not is_pinned,
    )
    account = preview.get("account") or {}

    return {
        "requested_workspace_id": selection.requested_workspace_id,
        "effective_workspace_id": selection.effective_workspace_id,
        "auth_workspace_id": selection.auth_workspace_id,
        "source_workspace_id": selection.source_workspace_id,
        "selection_reason": selection.selection_reason,
        "selection_trace": list(selection.trace),
        "policy_mode": "pinned_runtime" if is_pinned else "pool_rotation",
        "preferred_runtime_id": selection.selected_runtime_id,
        "resolved_runtime_id": preview.get("selected_runtime_id"),
        "resolved_email": account.get("email"),
        "resolved_status": preview.get("status", "unavailable"),
        "cooldown_until": preview.get("cooldown_until"),
        "next_reset_at": preview.get("next_reset_at"),
        "available_count": preview.get("available_count", 0),
        "cooling_count": preview.get("cooling_count", 0),
        "pool_count": preview.get("pool_count", 0),
        "error": preview.get("error"),
    }


@router.post("/add")
async def add_account(current_user=Depends(get_current_user)):
    """Create a new pool runtime for OAuth enrollment.

    Returns the new runtime info. Caller should redirect to
    /api/v1/runtime-oauth/{runtime_id}/authorize to start OAuth.
    """
    service = _get_service()
    account = service.add_account(user_id=current_user.id)
    return {
        "account": account,
        "authorize_url": f"/api/v1/runtime-oauth/{account['id']}/authorize",
    }


@router.patch("/{runtime_id}")
async def update_account(runtime_id: str, body: UpdateAccountRequest):
    """Toggle enabled/disabled or set priority for a pool account."""
    service = _get_service()
    result = service.update_account(
        runtime_id=runtime_id,
        enabled=body.enabled,
        priority=body.priority,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Runtime not found in pool")
    return result


@router.delete("/{runtime_id}")
async def remove_account(runtime_id: str):
    """Remove an account from the pool."""
    service = _get_service()
    removed = service.remove_account(runtime_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Runtime not found in pool")
    return {"removed": True, "runtime_id": runtime_id}


@router.post("/{runtime_id}/quota-exhausted")
async def report_quota_exhausted(runtime_id: str):
    """Report that a runtime hit 429 quota exhaustion.

    Applies exponential cooldown (5min -> 15min -> 30min cap).
    Called by the bridge when RESOURCE_EXHAUSTED is detected.
    """
    service = _get_service()
    result = service.report_quota_exhausted(runtime_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Runtime not found in pool")
    return {
        "runtime_id": runtime_id,
        "cooldown_until": result.get("cooldown_until"),
    }
