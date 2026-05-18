"""Sandbox workspace sync routes."""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Body, Path as PathParam

from backend.app.services.sandbox.workspace_sync import get_workspace_sync_service

from .schemas import SyncToWorkspaceRequest
from .state import store

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/{sandbox_id}/sync/diff", response_model=Dict[str, Any])
async def get_sync_diff(
    workspace_id: str = PathParam(..., description="Workspace identifier"),
    sandbox_id: str = PathParam(..., description="Sandbox identifier")
):
    """
    Get diff between workspace and sandbox.

    Shows what files would change if syncing sandbox to workspace.
    Useful for user confirmation before save.

    Returns:
        - added: Files in sandbox but not workspace
        - modified: Files that differ
        - deleted: Files in workspace but not sandbox
        - unchanged: Files that are identical
    """
    try:
        sync_service = get_workspace_sync_service(store)
        diff = await sync_service.get_sync_diff(workspace_id, sandbox_id)
        return diff
    except Exception as e:
        logger.error(f"Failed to get sync diff: {e}")
        return {"error": str(e)}

@router.post("/{sandbox_id}/sync/to-workspace", response_model=Dict[str, Any])
async def sync_sandbox_to_workspace(
    workspace_id: str = PathParam(..., description="Workspace identifier"),
    sandbox_id: str = PathParam(..., description="Sandbox identifier"),
    request: SyncToWorkspaceRequest = Body(...)
):
    """
    Save sandbox files to workspace (persist changes).

    This is the "save" operation. Syncs sandbox changes back to workspace.
    Creates backups of existing files by default.

    **Safety**: Requires `confirmed: true` to proceed.
    Call GET /sync/diff first to preview changes.

    Returns:
        - synced_files: Files saved to workspace
        - backed_up_files: Files that were backed up
        - status: success/error
    """
    try:
        if not request.confirmed:
            # Return diff instead of syncing
            sync_service = get_workspace_sync_service(store)
            diff = await sync_service.get_sync_diff(workspace_id, sandbox_id)
            return {
                "status": "confirmation_required",
                "message": "Please review changes and set confirmed=true",
                "diff": diff
            }

        sync_service = get_workspace_sync_service(store)
        result = await sync_service.sync_sandbox_to_workspace(
            workspace_id=workspace_id,
            sandbox_id=sandbox_id,
            create_backup=request.create_backup
        )
        return result

    except Exception as e:
        logger.error(f"Failed to sync to workspace: {e}")
        return {"status": "error", "error": str(e)}
