"""
Story Thread API Proxy Routes
Proxy endpoints for Cloud Story Thread API to maintain architectural boundaries.

Story Thread is a Cloud feature, but local-core needs to integrate with it.
Frontend should call local-core backend, which then proxies to Cloud API.
"""

import logging
import os
from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel
import httpx

from ...services.system_settings_store import SystemSettingsStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/story-threads", tags=["story-threads"])

settings_store = SystemSettingsStore()


def get_cloud_api_url() -> Optional[str]:
    """
    Get Cloud API URL from settings or environment.

    Returns:
        Cloud API URL or None if not configured

    Raises:
        HTTPException: If Cloud API is required but not configured
    """
    api_url = settings_store.get("cloud_api_url", default="") or os.getenv("CLOUD_API_URL")
    if not api_url:
        raise HTTPException(
            status_code=503,
            detail="Cloud API not configured. Story Thread feature requires CLOUD_API_URL to be configured in settings or environment variables."
        )
    return api_url


@router.get("/{thread_id}")
async def get_thread(thread_id: str):
    """Get Story Thread by ID."""
    cloud_api_url = get_cloud_api_url()

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{cloud_api_url}/api/v1/story-threads/{thread_id}",
            )
            if response.status_code == 404:
                raise HTTPException(status_code=404, detail="Story Thread not found")
            response.raise_for_status()
            return response.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Timeout connecting to Cloud API")
    except httpx.RequestError as e:
        logger.error(f"Failed to proxy Story Thread request: {e}")
        raise HTTPException(status_code=502, detail=f"Failed to connect to Cloud API: {str(e)}")


@router.post("")
async def create_thread(request: Dict[str, Any] = Body(...)):
    """Create a new Story Thread."""
    cloud_api_url = get_cloud_api_url()

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{cloud_api_url}/api/v1/story-threads",
                json=request,
            )
            response.raise_for_status()
            return response.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Timeout connecting to Cloud API")
    except httpx.RequestError as e:
        logger.error(f"Failed to proxy Story Thread creation: {e}")
        raise HTTPException(status_code=502, detail=f"Failed to connect to Cloud API: {str(e)}")


@router.put("/{thread_id}")
async def update_thread(thread_id: str, request: Dict[str, Any] = Body(...)):
    """Update Story Thread."""
    cloud_api_url = get_cloud_api_url()

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.put(
                f"{cloud_api_url}/api/v1/story-threads/{thread_id}",
                json=request,
            )
            if response.status_code == 404:
                raise HTTPException(status_code=404, detail="Story Thread not found")
            response.raise_for_status()
            return response.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Timeout connecting to Cloud API")
    except httpx.RequestError as e:
        logger.error(f"Failed to proxy Story Thread update: {e}")
        raise HTTPException(status_code=502, detail=f"Failed to connect to Cloud API: {str(e)}")


@router.delete("/{thread_id}")
async def delete_thread(thread_id: str):
    """Delete Story Thread."""
    cloud_api_url = get_cloud_api_url()

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.delete(
                f"{cloud_api_url}/api/v1/story-threads/{thread_id}",
            )
            if response.status_code == 404:
                raise HTTPException(status_code=404, detail="Story Thread not found")
            response.raise_for_status()
            return {"success": True}
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Timeout connecting to Cloud API")
    except httpx.RequestError as e:
        logger.error(f"Failed to proxy Story Thread deletion: {e}")
        raise HTTPException(status_code=502, detail=f"Failed to connect to Cloud API: {str(e)}")


@router.get("/{thread_id}/chapters")
async def get_chapters(thread_id: str):
    """Get chapters for a Story Thread."""
    cloud_api_url = get_cloud_api_url()

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{cloud_api_url}/api/v1/story-threads/{thread_id}/chapters",
            )
            if response.status_code == 404:
                raise HTTPException(status_code=404, detail="Story Thread not found")
            response.raise_for_status()
            return response.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Timeout connecting to Cloud API")
    except httpx.RequestError as e:
        logger.error(f"Failed to proxy chapters request: {e}")
        raise HTTPException(status_code=502, detail=f"Failed to connect to Cloud API: {str(e)}")


@router.post("/{thread_id}/chapters")
async def create_chapter(thread_id: str, request: Dict[str, Any] = Body(...)):
    """Create a new chapter for a Story Thread."""
    cloud_api_url = get_cloud_api_url()

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{cloud_api_url}/api/v1/story-threads/{thread_id}/chapters",
                json=request,
            )
            response.raise_for_status()
            return response.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Timeout connecting to Cloud API")
    except httpx.RequestError as e:
        logger.error(f"Failed to proxy chapter creation: {e}")
        raise HTTPException(status_code=502, detail=f"Failed to connect to Cloud API: {str(e)}")


@router.get("/{thread_id}/timeline")
async def get_timeline(thread_id: str):
    """Get timeline events for a Story Thread."""
    cloud_api_url = get_cloud_api_url()

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{cloud_api_url}/api/v1/story-threads/{thread_id}/timeline",
            )
            if response.status_code == 404:
                raise HTTPException(status_code=404, detail="Story Thread not found")
            response.raise_for_status()
            return response.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Timeout connecting to Cloud API")
    except httpx.RequestError as e:
        logger.error(f"Failed to proxy timeline request: {e}")
        raise HTTPException(status_code=502, detail=f"Failed to connect to Cloud API: {str(e)}")


@router.get("/{thread_id}/context")
async def get_context(thread_id: str):
    """Get shared context for a Story Thread."""
    cloud_api_url = get_cloud_api_url()

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{cloud_api_url}/api/v1/story-threads/{thread_id}/context",
            )
            if response.status_code == 404:
                raise HTTPException(status_code=404, detail="Story Thread not found")
            response.raise_for_status()
            return response.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Timeout connecting to Cloud API")
    except httpx.RequestError as e:
        logger.error(f"Failed to proxy context request: {e}")
        raise HTTPException(status_code=502, detail=f"Failed to connect to Cloud API: {str(e)}")


@router.put("/{thread_id}/context")
async def update_context(thread_id: str, request: Dict[str, Any] = Body(...)):
    """Update shared context for a Story Thread."""
    cloud_api_url = get_cloud_api_url()

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.put(
                f"{cloud_api_url}/api/v1/story-threads/{thread_id}/context",
                json=request,
            )
            if response.status_code == 404:
                raise HTTPException(status_code=404, detail="Story Thread not found")
            response.raise_for_status()
            return response.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Timeout connecting to Cloud API")
    except httpx.RequestError as e:
        logger.error(f"Failed to proxy context update: {e}")
        raise HTTPException(status_code=502, detail=f"Failed to connect to Cloud API: {str(e)}")


@router.get("")
async def list_threads(
    workspace_id: Optional[str] = Query(None),
    mind_lens_id: Optional[str] = Query(None),
    owner_user_id: Optional[str] = Query(None),
):
    """List Story Threads with optional filters."""
    cloud_api_url = get_cloud_api_url()

    params = {}
    if workspace_id:
        params["workspace_id"] = workspace_id
    if mind_lens_id:
        params["mind_lens_id"] = mind_lens_id
    if owner_user_id:
        params["owner_user_id"] = owner_user_id

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{cloud_api_url}/api/v1/story-threads",
                params=params,
            )
            response.raise_for_status()
            return response.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Timeout connecting to Cloud API")
    except httpx.RequestError as e:
        logger.error(f"Failed to proxy list threads request: {e}")
        raise HTTPException(status_code=502, detail=f"Failed to connect to Cloud API: {str(e)}")


@router.get("/{thread_id}/chapters/{chapter_id}")
async def get_chapter(thread_id: str, chapter_id: str):
    """Get a specific chapter by ID."""
    cloud_api_url = get_cloud_api_url()

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{cloud_api_url}/api/v1/story-threads/{thread_id}/chapters/{chapter_id}",
            )
            if response.status_code == 404:
                raise HTTPException(status_code=404, detail="Chapter not found")
            response.raise_for_status()
            return response.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Timeout connecting to Cloud API")
    except httpx.RequestError as e:
        logger.error(f"Failed to proxy chapter request: {e}")
        raise HTTPException(status_code=502, detail=f"Failed to connect to Cloud API: {str(e)}")


@router.put("/{thread_id}/chapters/{chapter_id}")
async def update_chapter(thread_id: str, chapter_id: str, request: Dict[str, Any] = Body(...)):
    """Update a chapter."""
    cloud_api_url = get_cloud_api_url()

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.put(
                f"{cloud_api_url}/api/v1/story-threads/{thread_id}/chapters/{chapter_id}",
                json=request,
            )
            if response.status_code == 404:
                raise HTTPException(status_code=404, detail="Chapter not found")
            response.raise_for_status()
            return response.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Timeout connecting to Cloud API")
    except httpx.RequestError as e:
        logger.error(f"Failed to proxy chapter update: {e}")
        raise HTTPException(status_code=502, detail=f"Failed to connect to Cloud API: {str(e)}")


@router.post("/{thread_id}/timeline/events")
async def create_timeline_event(thread_id: str, request: Dict[str, Any] = Body(...)):
    """Create a timeline event for a Story Thread."""
    cloud_api_url = get_cloud_api_url()

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{cloud_api_url}/api/v1/story-threads/{thread_id}/timeline/events",
                json=request,
            )
            if response.status_code == 404:
                raise HTTPException(status_code=404, detail="Story Thread not found")
            response.raise_for_status()
            return response.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Timeout connecting to Cloud API")
    except httpx.RequestError as e:
        logger.error(f"Failed to proxy timeline event creation: {e}")
        raise HTTPException(status_code=502, detail=f"Failed to connect to Cloud API: {str(e)}")


@router.get("/{thread_id}/snapshots")
async def get_snapshots(thread_id: str):
    """Get snapshots for a Story Thread."""
    cloud_api_url = get_cloud_api_url()

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{cloud_api_url}/api/v1/story-threads/{thread_id}/snapshots",
            )
            if response.status_code == 404:
                raise HTTPException(status_code=404, detail="Story Thread not found")
            response.raise_for_status()
            return response.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Timeout connecting to Cloud API")
    except httpx.RequestError as e:
        logger.error(f"Failed to proxy snapshots request: {e}")
        raise HTTPException(status_code=502, detail=f"Failed to connect to Cloud API: {str(e)}")


@router.post("/{thread_id}/snapshots")
async def create_snapshot(thread_id: str, created_by: str = Query(...)):
    """Create a snapshot for a Story Thread."""
    cloud_api_url = get_cloud_api_url()

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{cloud_api_url}/api/v1/story-threads/{thread_id}/snapshots",
                params={"created_by": created_by},
            )
            if response.status_code == 404:
                raise HTTPException(status_code=404, detail="Story Thread not found")
            response.raise_for_status()
            return response.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Timeout connecting to Cloud API")
    except httpx.RequestError as e:
        logger.error(f"Failed to proxy snapshot creation: {e}")
        raise HTTPException(status_code=502, detail=f"Failed to connect to Cloud API: {str(e)}")

