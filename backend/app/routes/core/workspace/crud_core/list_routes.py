
import asyncio
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Path as PathParam, Query

from backend.app.models.workspace import Workspace

from .schemas import WorkspaceSummary, _workspace_to_summary
from .state import store

router = APIRouter()

@router.get("/", response_model=List[Workspace])
async def list_workspaces(
    owner_user_id: str = Query(..., description="Owner user ID"),
    primary_project_id: Optional[str] = Query(
        None, description="Filter by primary project ID"
    ),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of workspaces"),
    include_system: bool = Query(
        False, description="Include system workspaces (validation, testing, etc.)"
    ),
    group_id: Optional[str] = Query(
        None, description="Group ID filter (Cloud only, ignored in local-core)"
    ),
):
    """
    List workspaces for a user

    Returns list of workspaces owned by the user, optionally filtered by project.
    By default, system workspaces (is_system=true) are excluded from the list.

    Note: group_id parameter is accepted for Cloud compatibility but ignored in local-core.
    """
    try:
        workspaces = await asyncio.to_thread(
            store.list_workspaces,
            owner_user_id=owner_user_id,
            primary_project_id=primary_project_id,
            limit=limit,
        )
        # Filter out system workspaces unless explicitly requested
        if not include_system:
            workspaces = [
                ws for ws in workspaces if not getattr(ws, "is_system", False)
            ]
        # Note: group_id parameter is ignored in local-core (backward compatibility for Cloud)
        return workspaces
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to list workspaces: {str(e)}"
        )


@router.get("/summary", response_model=List[WorkspaceSummary])
async def list_workspace_summaries(
    owner_user_id: str = Query(..., description="Owner user ID"),
    primary_project_id: Optional[str] = Query(
        None, description="Filter by primary project ID"
    ),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of workspaces"),
    include_system: bool = Query(
        False, description="Include system workspaces (validation, testing, etc.)"
    ),
    group_id: Optional[str] = Query(
        None, description="Group ID filter (Cloud only, ignored in local-core)"
    ),
):
    """
    List lightweight workspace summaries for navigation and selectors.

    Full workspace configuration remains available from GET /workspaces/{workspace_id}.
    """
    try:
        if hasattr(store, "list_workspace_summaries"):
            summaries = await asyncio.to_thread(
                store.list_workspace_summaries,
                owner_user_id=owner_user_id,
                primary_project_id=primary_project_id,
                limit=limit,
            )
        else:
            workspaces = await asyncio.to_thread(
                store.list_workspaces,
                owner_user_id=owner_user_id,
                primary_project_id=primary_project_id,
                limit=limit,
            )
            summaries = [_workspace_to_summary(ws) for ws in workspaces]

        if not include_system:
            summaries = [
                summary
                for summary in summaries
                if not (
                    getattr(summary, "is_system", False)
                    if not isinstance(summary, dict)
                    else summary.get("is_system", False)
                )
            ]

        return summaries
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list workspace summaries: {str(e)}",
        )


@router.get("/{workspace_id}/summary", response_model=WorkspaceSummary)
async def get_workspace_summary(
    workspace_id: str = PathParam(..., description="Workspace ID"),
):
    """
    Get lightweight workspace data for route-critical shell rendering.

    Full workspace configuration remains available from GET /workspaces/{workspace_id}.
    """
    try:
        if hasattr(store, "get_workspace_summary"):
            summary = await store.get_workspace_summary(workspace_id)
        else:
            workspace = await store.get_workspace(workspace_id)
            summary = _workspace_to_summary(workspace) if workspace else None

        if not summary:
            raise HTTPException(status_code=404, detail="Workspace not found")

        return summary
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get workspace summary: {str(e)}",
        )
