"""
Workspace Background Routines Routes

Handles /workspaces/{id}/background-routines endpoints.
"""

import logging
import traceback
import sys
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Path, Query, Depends, Body
from pydantic import BaseModel

from backend.app.models.workspace import BackgroundRoutine, Workspace
from backend.app.routes.workspace_dependencies import get_workspace, get_store
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.stores.background_routines_store import BackgroundRoutinesStore

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspaces-background-routines"])
logger = logging.getLogger(__name__)


class BackgroundRoutineResponse(BaseModel):
    """Background routine response model"""
    id: str
    workspace_id: str
    playbook_code: str
    enabled: bool
    config: dict
    last_run_at: Optional[str] = None
    next_run_at: Optional[str] = None
    last_status: Optional[str] = None
    readiness_status: Optional[str] = None
    tool_statuses: Optional[dict] = None
    error_count: int = 0
    auto_paused: bool = False
    created_at: str
    updated_at: str


class BackgroundRoutinesListResponse(BaseModel):
    """Background routines list response model"""
    workspace_id: str
    routines: List[BackgroundRoutineResponse]


@router.get("/{workspace_id}/background-routines", response_model=BackgroundRoutinesListResponse)
async def get_workspace_background_routines(
    workspace_id: str = Path(..., description="Workspace ID"),
    enabled_only: bool = Query(False, description="Only return enabled routines"),
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store)
):
    """
    Get background routines for a workspace
    """
    try:
        routines_store = BackgroundRoutinesStore(db_path=store.db_path)
        routines = routines_store.list_background_routines_by_workspace(
            workspace_id=workspace_id,
            enabled_only=enabled_only
        )

        routine_responses = []
        for routine in routines:
            routine_responses.append(BackgroundRoutineResponse(
                id=routine.id,
                workspace_id=routine.workspace_id,
                playbook_code=routine.playbook_code,
                enabled=routine.enabled,
                config=routine.config or {},
                last_run_at=routine.last_run_at.isoformat() if routine.last_run_at else None,
                next_run_at=routine.next_run_at.isoformat() if routine.next_run_at else None,
                last_status=routine.last_status,
                readiness_status=routine.readiness_status,
                tool_statuses=routine.tool_statuses,
                error_count=routine.error_count or 0,
                auto_paused=routine.auto_paused or False,
                created_at=routine.created_at.isoformat() if routine.created_at else "",
                updated_at=routine.updated_at.isoformat() if routine.updated_at else ""
            ))

        return BackgroundRoutinesListResponse(
            workspace_id=workspace_id,
            routines=routine_responses
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get background routines: {str(e)}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to get background routines: {str(e)}")


@router.post("/{workspace_id}/background-routines/{routine_id}/enable")
async def enable_background_routine(
    workspace_id: str = Path(..., description="Workspace ID"),
    routine_id: str = Path(..., description="Background Routine ID"),
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store)
):
    """
    Enable a background routine
    """
    try:
        routines_store = BackgroundRoutinesStore(db_path=store.db_path)
        routine = routines_store.update_background_routine(
            routine_id=routine_id,
            enabled=True
        )
        if not routine:
            raise HTTPException(status_code=404, detail="Background routine not found")

        return {"status": "ok", "routine_id": routine_id, "enabled": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to enable background routine: {str(e)}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to enable background routine: {str(e)}")


@router.delete("/{workspace_id}/background-routines/{routine_id}")
async def delete_background_routine(
    workspace_id: str = Path(..., description="Workspace ID"),
    routine_id: str = Path(..., description="Background Routine ID"),
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store)
):
    """
    Delete a background routine
    """
    try:
        routines_store = BackgroundRoutinesStore(db_path=store.db_path)
        routines_store.delete_background_routine(routine_id)

        return {"status": "ok", "routine_id": routine_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete background routine: {str(e)}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to delete background routine: {str(e)}")

