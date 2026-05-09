"""
Cloud Sync API Routes
API endpoints for cloud sync functionality
"""

import logging
import time
import asyncio
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from ...services.cloud_sync.service import get_cloud_sync_service
from .read_executor import run_ui_read

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/cloud-sync", tags=["cloud-sync"])


class VersionCheckRequest(BaseModel):
    """Version check request"""
    client_version: str
    capabilities: List[Dict[str, str]]
    assets: List[Dict[str, Any]]
    license_id: Optional[str] = None
    device_id: Optional[str] = None


class SyncStatusResponse(BaseModel):
    """Sync status response"""
    configured: bool
    online: bool
    pending_changes: int


_SYNC_STATUS_CACHE_TTL_SECONDS = 15.0
_SYNC_STATUS_CACHE_LOCK = asyncio.Lock()
_SYNC_STATUS_CACHE: tuple[float, SyncStatusResponse] | None = None
_SYNC_STATUS_INFLIGHT: asyncio.Task | None = None


def _read_sync_status() -> SyncStatusResponse:
    service = get_cloud_sync_service()
    if not service:
        return SyncStatusResponse(
            configured=False,
            online=False,
            pending_changes=0,
        )

    pending_changes = service.offline_change_tracker.get_pending_change_count()

    return SyncStatusResponse(
        configured=service.is_configured(),
        online=service.is_online(),
        pending_changes=pending_changes,
    )


@router.get("/status", response_model=SyncStatusResponse)
async def get_sync_status():
    """Get cloud sync status"""
    global _SYNC_STATUS_CACHE, _SYNC_STATUS_INFLIGHT

    now = time.monotonic()
    async with _SYNC_STATUS_CACHE_LOCK:
        if _SYNC_STATUS_CACHE and now - _SYNC_STATUS_CACHE[0] < _SYNC_STATUS_CACHE_TTL_SECONDS:
            return _SYNC_STATUS_CACHE[1]
        if _SYNC_STATUS_INFLIGHT is not None:
            inflight = _SYNC_STATUS_INFLIGHT
        else:
            inflight = asyncio.create_task(run_ui_read(_read_sync_status))
            _SYNC_STATUS_INFLIGHT = inflight

    try:
        status = await inflight
        async with _SYNC_STATUS_CACHE_LOCK:
            _SYNC_STATUS_CACHE = (time.monotonic(), status)
        return status
    finally:
        async with _SYNC_STATUS_CACHE_LOCK:
            if _SYNC_STATUS_INFLIGHT is inflight:
                _SYNC_STATUS_INFLIGHT = None


@router.post("/versions/check")
async def check_versions(request: VersionCheckRequest):
    """Check for version updates"""
    service = get_cloud_sync_service()
    if not service or not service.is_configured():
        raise HTTPException(status_code=503, detail="Cloud sync service not configured")

    try:
        result = await service.check_updates(
            client_version=request.client_version,
            capabilities=request.capabilities,
            assets=request.assets,
            license_id=request.license_id,
            device_id=request.device_id,
        )
        return result
    except Exception as e:
        logger.error(f"Failed to check versions: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to check versions: {str(e)}")


@router.post("/sync/pending")
async def sync_pending_changes():
    """Sync all pending changes"""
    global _SYNC_STATUS_CACHE
    service = get_cloud_sync_service()
    if not service or not service.is_configured():
        raise HTTPException(status_code=503, detail="Cloud sync service not configured")

    try:
        result = await service.sync_pending_changes()
        async with _SYNC_STATUS_CACHE_LOCK:
            _SYNC_STATUS_CACHE = None
        return result
    except Exception as e:
        logger.error(f"Failed to sync pending changes: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to sync pending changes: {str(e)}")


@router.get("/changes/pending")
async def get_pending_changes():
    """Get list of pending changes"""
    service = get_cloud_sync_service()
    if not service:
        return []

    try:
        changes = service.offline_change_tracker.get_pending_changes()
        return changes
    except Exception as e:
        logger.error(f"Failed to get pending changes: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get pending changes: {str(e)}")


@router.get("/changes/summary")
async def get_change_summary():
    """Get summary of pending changes"""
    service = get_cloud_sync_service()
    if not service:
        return {
            "total_changes": 0,
            "affected_instances": 0,
            "instances_with_changes": [],
        }

    try:
        summary = service.offline_change_tracker.get_change_summary()
        return summary
    except Exception as e:
        logger.error(f"Failed to get change summary: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get change summary: {str(e)}")


@router.post("/cache/cleanup")
async def cleanup_cache():
    """Clean up expired cache entries"""
    service = get_cloud_sync_service()
    if not service:
        return {"cleared": 0}

    try:
        cleared = service.cleanup_expired_cache()
        return {"cleared": cleared}
    except Exception as e:
        logger.error(f"Failed to cleanup cache: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to cleanup cache: {str(e)}")
