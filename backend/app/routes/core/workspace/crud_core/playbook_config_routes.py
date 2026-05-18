
from typing import Optional

from fastapi import APIRouter, Body, HTTPException, Path as PathParam

from backend.app.models.workspace import Workspace

from .state import store

router = APIRouter()

@router.patch("/{workspace_id}/playbook-auto-exec-config", response_model=Workspace)
async def update_playbook_auto_exec_config(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    playbook_code: str = Body(..., description="Playbook code"),
    confidence_threshold: Optional[float] = Body(
        None, description="Confidence threshold (0.0-1.0)"
    ),
    auto_execute: Optional[bool] = Body(None, description="Enable auto-execute"),
):
    """
    Update playbook auto-execution configuration

    Sets the confidence threshold and auto-execute flag for a specific playbook in this workspace.
    """
    try:
        workspace = await store.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

        # Initialize config if not exists
        if workspace.playbook_auto_execution_config is None:
            workspace.playbook_auto_execution_config = {}

        # Update or create playbook config
        if playbook_code not in workspace.playbook_auto_execution_config:
            workspace.playbook_auto_execution_config[playbook_code] = {}

        if confidence_threshold is not None:
            workspace.playbook_auto_execution_config[playbook_code][
                "confidence_threshold"
            ] = confidence_threshold
        if auto_execute is not None:
            workspace.playbook_auto_execution_config[playbook_code][
                "auto_execute"
            ] = auto_execute

        updated = await store.update_workspace(workspace)
        return updated
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update playbook auto-exec config: {str(e)}",
        )
