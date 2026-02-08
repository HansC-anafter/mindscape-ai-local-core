import logging
from typing import Any, Dict

from fastapi import (
    APIRouter,
    HTTPException,
    Path as PathParam,
    Body,
)

from ....services.mindscape_store import MindscapeStore

router = APIRouter()
logger = logging.getLogger(__name__)
store = MindscapeStore()


@router.get("/{workspace_id}/runtime")
async def get_workspace_runtime(
    workspace_id: str = PathParam(..., description="Workspace ID")
) -> Dict[str, Any]:
    """
    Get runtime configuration for a workspace.

    Returns:
        Dictionary containing:
        - runtime_id: Current runtime ID
        - status: Connection status
        - group_id: Workspace group ID (if exists, for future use)
        - workspace_role: "dispatch" or "cell" (default: "cell")
        - group_runtime: Group-level runtime (if exists)
        - effective_runtime: Effective runtime after priority resolution
    """
    try:
        # Get workspace
        workspace = await store.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(
                status_code=404, detail=f"Workspace '{workspace_id}' not found"
            )

        # Get workspace runtime configuration
        # For now, we'll store it in workspace metadata
        workspace_runtime_id = None
        if hasattr(workspace, "metadata") and workspace.metadata:
            if isinstance(workspace.metadata, dict):
                workspace_runtime_id = workspace.metadata.get("runtime_id")

        # Get group runtime (if exists, for future use)
        group_runtime_id = None
        # TODO: Implement group-level runtime when WorkspaceGroup is available

        # Determine effective runtime (priority: workspace > group > default)
        effective_runtime_id = workspace_runtime_id or group_runtime_id or "local-core"

        # Get runtime status
        runtime_status = "connected"
        if effective_runtime_id != "local-core":
            # Check if external runtime exists and is configured
            # Note: This requires database access, which we'll need to implement
            # For now, return "not_configured" if not local-core
            runtime_status = "not_configured"
            # TODO: Query RuntimeEnvironment table to get actual status

        return {
            "runtime_id": effective_runtime_id,
            "status": runtime_status,
            "group_id": None,  # TODO: Implement when WorkspaceGroup is available
            "workspace_role": "cell",  # Local-Core default is cell
            "group_runtime": group_runtime_id,
            "workspace_runtime": workspace_runtime_id,
            "effective_runtime": effective_runtime_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get workspace runtime: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get workspace runtime")


@router.put("/{workspace_id}/runtime")
async def update_workspace_runtime(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    request: Dict[str, Any] = Body(..., description="Runtime update request"),
) -> Dict[str, Any]:
    """
    Update runtime configuration for a workspace.

    Args:
        workspace_id: Workspace ID
        request: Request body containing runtime_id

    Returns:
        Updated runtime configuration
    """
    try:
        runtime_id = request.get("runtime_id")
        if not runtime_id:
            raise HTTPException(
                status_code=400, detail="runtime_id is required in request body"
            )

        # Validate runtime_id
        if runtime_id != "local-core":
            # TODO: Check if runtime exists and user has access
            # This requires database access to RuntimeEnvironment table
            pass

        # Get workspace
        workspace = await store.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(
                status_code=404, detail=f"Workspace '{workspace_id}' not found"
            )

        # Update workspace runtime
        # Store in metadata for now (can be moved to dedicated field later)
        if not hasattr(workspace, "metadata") or not workspace.metadata:
            workspace.metadata = {}
        elif not isinstance(workspace.metadata, dict):
            workspace.metadata = {}

        workspace.metadata["runtime_id"] = runtime_id

        # Update workspace
        updated = await store.update_workspace(workspace)

        # Get effective runtime
        effective_runtime_id = runtime_id

        # Get runtime status
        runtime_status = "connected"
        if effective_runtime_id != "local-core":
            runtime_status = "not_configured"
            # TODO: Query RuntimeEnvironment table to get actual status

        return {
            "success": True,
            "runtime_id": effective_runtime_id,
            "effective_runtime": effective_runtime_id,
            "status": runtime_status,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update workspace runtime: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail="Failed to update workspace runtime"
        )
