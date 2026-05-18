"""Sandbox CRUD routes."""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Path as PathParam, Query

from .schemas import CreateSandboxRequest
from .state import sandbox_manager

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/sandboxes",
    tags=["sandboxes"],
)

@router.get("", response_model=List[Dict[str, Any]])
async def list_sandboxes(
    workspace_id: str = PathParam(..., description="Workspace identifier"),
    sandbox_type: Optional[str] = Query(None, description="Filter by sandbox type")
):
    """
    List all sandboxes in workspace

    Returns list of sandbox metadata dictionaries.
    """
    try:
        sandboxes = await sandbox_manager.list_sandboxes(
            workspace_id=workspace_id,
            sandbox_type=sandbox_type
        )
        return sandboxes
    except Exception as e:
        logger.error(f"Failed to list sandboxes: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("", status_code=201)
async def create_sandbox(
    workspace_id: str = PathParam(..., description="Workspace identifier"),
    request: CreateSandboxRequest = Body(...)
):
    """
    Create a new sandbox

    Returns sandbox identifier.
    """
    try:
        sandbox_id = await sandbox_manager.create_sandbox(
            sandbox_type=request.sandbox_type,
            workspace_id=workspace_id,
            context=request.context
        )
        return {"sandbox_id": sandbox_id}
    except ValueError as e:
        logger.error(f"Invalid sandbox type: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create sandbox: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{sandbox_id}", response_model=Dict[str, Any])
async def get_sandbox(
    workspace_id: str = PathParam(..., description="Workspace identifier"),
    sandbox_id: str = PathParam(..., description="Sandbox identifier")
):
    """
    Get sandbox details

    Returns sandbox metadata dictionary.
    """
    try:
        sandbox = await sandbox_manager.get_sandbox(sandbox_id, workspace_id)
        if not sandbox:
            raise HTTPException(status_code=404, detail="Sandbox not found")
        return sandbox.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get sandbox: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{sandbox_id}", status_code=204)
async def delete_sandbox(
    workspace_id: str = PathParam(..., description="Workspace identifier"),
    sandbox_id: str = PathParam(..., description="Sandbox identifier")
):
    """
    Delete sandbox

    Returns 204 No Content on success.
    """
    try:
        success = await sandbox_manager.delete_sandbox(sandbox_id, workspace_id)
        if not success:
            raise HTTPException(status_code=404, detail="Sandbox not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete sandbox: {e}")
        raise HTTPException(status_code=500, detail=str(e))
