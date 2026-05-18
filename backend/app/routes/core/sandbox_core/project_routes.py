"""Sandbox project lookup routes."""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Path as PathParam

from .state import sandbox_manager

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/by-project/{project_id}", response_model=Optional[Dict[str, Any]])
async def get_sandbox_by_project(
    workspace_id: str = PathParam(..., description="Workspace identifier"),
    project_id: str = PathParam(..., description="Project identifier")
):
    """
    Get sandbox for a project

    Returns sandbox metadata if found, None otherwise.
    """
    try:
        sandboxes = await sandbox_manager.list_sandboxes(
            workspace_id=workspace_id
        )

        project_sandbox = next(
            (s for s in sandboxes if s.get("metadata", {}).get("context", {}).get("project_id") == project_id),
            None
        )

        if project_sandbox:
            sandbox = await sandbox_manager.get_sandbox(
                project_sandbox["sandbox_id"],
                workspace_id
            )
            if sandbox:
                return sandbox.to_dict()

        return None
    except Exception as e:
        logger.error(f"Failed to get sandbox by project: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Preview Server API
# =============================================================================
