"""Sandbox version routes."""

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Body, HTTPException, Path as PathParam

from .schemas import CreateVersionRequest
from .state import sandbox_manager

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/{sandbox_id}/versions", status_code=201)
async def create_version(
    workspace_id: str = PathParam(..., description="Workspace identifier"),
    sandbox_id: str = PathParam(..., description="Sandbox identifier"),
    request: CreateVersionRequest = Body(...)
):
    """
    Create a new version snapshot

    Returns version identifier.
    """
    try:
        sandbox = await sandbox_manager.get_sandbox(sandbox_id, workspace_id)
        if not sandbox:
            raise HTTPException(status_code=404, detail="Sandbox not found")

        success = await sandbox.create_version(request.version, request.source_version)
        if not success:
            raise HTTPException(status_code=400, detail="Failed to create version")

        return {"version": request.version}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create version: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{sandbox_id}/versions", response_model=List[str])
async def list_versions(
    workspace_id: str = PathParam(..., description="Workspace identifier"),
    sandbox_id: str = PathParam(..., description="Sandbox identifier")
):
    """
    List all versions

    Returns list of version identifiers.
    """
    try:
        sandbox = await sandbox_manager.get_sandbox(sandbox_id, workspace_id)
        if not sandbox:
            raise HTTPException(status_code=404, detail="Sandbox not found")

        versions = await sandbox.list_versions()
        return versions
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list versions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{sandbox_id}/versions/{version}", response_model=Dict[str, Any])
async def get_version_metadata(
    workspace_id: str = PathParam(..., description="Workspace identifier"),
    sandbox_id: str = PathParam(..., description="Sandbox identifier"),
    version: str = PathParam(..., description="Version identifier")
):
    """
    Get version metadata

    Returns version metadata dictionary.
    """
    try:
        sandbox = await sandbox_manager.get_sandbox(sandbox_id, workspace_id)
        if not sandbox:
            raise HTTPException(status_code=404, detail="Sandbox not found")

        metadata = await sandbox.get_version_metadata(version)
        if not metadata:
            raise HTTPException(status_code=404, detail="Version not found")

        return metadata
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get version metadata: {e}")
        raise HTTPException(status_code=500, detail=str(e))
