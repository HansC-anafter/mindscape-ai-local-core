"""
GCA Pool API

REST endpoints for managing the GCA multi-account pool.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/gca-pool", tags=["gca-pool"])


class UpdateAccountRequest(BaseModel):
    enabled: Optional[bool] = None
    priority: Optional[int] = None


def _get_service():
    from ..services.gca_pool_service import GCAPoolService

    return GCAPoolService()


@router.get("")
async def list_pool():
    """List all accounts in the GCA pool."""
    service = _get_service()
    accounts = service.list_pool()
    return {"accounts": accounts, "count": len(accounts)}


@router.post("/add")
async def add_account(user_id: str = "default"):
    """Create a new pool runtime for OAuth enrollment.

    Returns the new runtime info. Caller should redirect to
    /api/v1/runtime-oauth/{runtime_id}/authorize to start OAuth.
    """
    service = _get_service()
    account = service.add_account(user_id=user_id)
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
