"""Workspace list endpoints with explicit normalized group context."""

import asyncio
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Path as PathParam, Query

from backend.app.dependencies.auth import AuthContext, get_current_user
from backend.app.models.workspace import Workspace
from backend.app.services.workspace_groups.facade import WorkspaceGroupFacade
from backend.app.services.workspace_groups.topology_service import (
    WorkspaceGroupAccessError,
    WorkspaceGroupNotFoundError,
)

from .schemas import WorkspaceSummary, _workspace_to_summary
from .state import store


router = APIRouter()
group_facade = WorkspaceGroupFacade()


def _normalize_active_group(query_group_id: Optional[str], header_group_id: Optional[str]):
    if query_group_id and header_group_id and query_group_id != header_group_id:
        raise HTTPException(status_code=400, detail="active group header/query mismatch")
    return query_group_id or header_group_id


async def _authorized_group(
    group_id: Optional[str], auth: AuthContext
):
    if not group_id:
        return None
    try:
        return await asyncio.to_thread(
            group_facade.get_group,
            group_id,
            actor_user_id=auth.user_id,
            allowed_group_ids=auth.group_ids,
        )
    except WorkspaceGroupNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except WorkspaceGroupAccessError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


async def _attach_memberships(items: List[Any], active_group) -> None:
    workspace_ids = [
        item["id"] if isinstance(item, dict) else item.id
        for item in items
    ]
    refs = await asyncio.to_thread(group_facade.membership_refs, workspace_ids)
    active_roles = active_group.role_map if active_group else {}
    for item in items:
        workspace_id = item["id"] if isinstance(item, dict) else item.id
        values = {
            "group_memberships": refs.get(workspace_id, []),
            "group_id": active_group.id if active_group else None,
            "workspace_role": active_roles.get(workspace_id),
        }
        if isinstance(item, dict):
            item.update(values)
        else:
            for key, value in values.items():
                setattr(item, key, value)


@router.get("/", response_model=List[Workspace])
async def list_workspaces(
    owner_user_id: Optional[str] = Query(
        None, description="Deprecated compatibility input; authenticated identity is authoritative"
    ),
    primary_project_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    include_system: bool = Query(False),
    group_id: Optional[str] = Query(None, description="Explicit active group filter"),
    x_group_id: Optional[str] = Header(None, alias="X-Group-ID"),
    auth: AuthContext = Depends(get_current_user),
):
    """List authorized workspaces, optionally constrained to one active group."""
    del owner_user_id
    active_group_id = _normalize_active_group(group_id, x_group_id)
    active_group = await _authorized_group(active_group_id, auth)
    try:
        workspaces = await asyncio.to_thread(
            store.list_workspaces,
            owner_user_id=auth.user_id,
            primary_project_id=primary_project_id,
            group_id=active_group_id,
            limit=limit,
        )
        if not include_system:
            workspaces = [
                workspace
                for workspace in workspaces
                if not getattr(workspace, "is_system", False)
            ]
        await _attach_memberships(workspaces, active_group)
        return workspaces
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail="failed to list workspaces") from exc


@router.get("/summary", response_model=List[WorkspaceSummary])
async def list_workspace_summaries(
    owner_user_id: Optional[str] = Query(
        None, description="Deprecated compatibility input; authenticated identity is authoritative"
    ),
    primary_project_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    include_system: bool = Query(False),
    group_id: Optional[str] = Query(None, description="Explicit active group filter"),
    x_group_id: Optional[str] = Header(None, alias="X-Group-ID"),
    auth: AuthContext = Depends(get_current_user),
):
    """List compact workspace projections with normalized memberships."""
    del owner_user_id
    active_group_id = _normalize_active_group(group_id, x_group_id)
    active_group = await _authorized_group(active_group_id, auth)
    try:
        if hasattr(store, "list_workspace_summaries"):
            summaries = await asyncio.to_thread(
                store.list_workspace_summaries,
                owner_user_id=auth.user_id,
                primary_project_id=primary_project_id,
                group_id=active_group_id,
                limit=limit,
            )
        else:
            workspaces = await asyncio.to_thread(
                store.list_workspaces,
                owner_user_id=auth.user_id,
                primary_project_id=primary_project_id,
                group_id=active_group_id,
                limit=limit,
            )
            summaries = [_workspace_to_summary(workspace).model_dump() for workspace in workspaces]
        if not include_system:
            summaries = [
                summary
                for summary in summaries
                if not (
                    summary.get("is_system", False)
                    if isinstance(summary, dict)
                    else getattr(summary, "is_system", False)
                )
            ]
        await _attach_memberships(summaries, active_group)
        return summaries
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail="failed to list workspace summaries") from exc


@router.get("/{workspace_id}/summary", response_model=WorkspaceSummary)
async def get_workspace_summary(
    workspace_id: str = PathParam(...),
    group_id: Optional[str] = Query(None),
    x_group_id: Optional[str] = Header(None, alias="X-Group-ID"),
    auth: AuthContext = Depends(get_current_user),
):
    """Get one compact workspace projection under an optional active group."""
    active_group_id = _normalize_active_group(group_id, x_group_id)
    active_group = await _authorized_group(active_group_id, auth)
    if active_group and workspace_id not in active_group.role_map:
        raise HTTPException(status_code=403, detail="workspace is not in active group")
    try:
        if hasattr(store, "get_workspace_summary"):
            summary = await store.get_workspace_summary(workspace_id)
        else:
            workspace = await store.get_workspace(workspace_id)
            summary = _workspace_to_summary(workspace).model_dump() if workspace else None
        if not summary:
            raise HTTPException(status_code=404, detail="Workspace not found")
        owner = summary.get("owner_user_id") if isinstance(summary, dict) else summary.owner_user_id
        if owner != auth.user_id and workspace_id not in auth.workspace_ids:
            raise HTTPException(status_code=403, detail="workspace access denied")
        items = [summary if isinstance(summary, dict) else summary.model_dump()]
        await _attach_memberships(items, active_group)
        return items[0]
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail="failed to get workspace summary") from exc
