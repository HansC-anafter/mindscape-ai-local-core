"""
Projects API routes for Workspace-based projects - Stats and Analytics
"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Path

from backend.app.models.workspace import Workspace
from backend.app.routes.workspace_dependencies import get_store, get_workspace
from backend.app.services.mindscape_store import MindscapeStore

from .stats_card_executions import build_project_card_payload
from .stats_execution_tree import build_project_execution_tree

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get(
    "/{workspace_id}/projects/{project_id}/execution-tree",
    response_model=Dict[str, Any],
)
async def get_project_execution_tree(
    workspace_id: str = Path(..., description="Workspace ID"),
    project_id: str = Path(..., description="Project ID"),
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store),
):
    """
    Get execution tree for a project, grouped by playbook.
    """
    try:
        return await build_project_execution_tree(
            workspace_id=workspace_id,
            project_id=project_id,
            store=store,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get project execution tree: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{workspace_id}/projects/{project_id}/card", response_model=Dict[str, Any])
async def get_project_card(
    workspace_id: str = Path(..., description="Workspace ID"),
    project_id: str = Path(..., description="Project ID"),
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store),
):
    """
    Get project card data with stats, progress, and recent events.
    """
    try:
        return await build_project_card_payload(
            workspace_id=workspace_id,
            project_id=project_id,
            workspace=workspace,
            store=store,
        )
    except PermissionError as e:
        logger.error(f"Permission error getting project card: {e}")
        raise HTTPException(status_code=403, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get project card: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
