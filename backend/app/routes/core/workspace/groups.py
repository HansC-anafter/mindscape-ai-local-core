"""Workspace Groups API — thin HTTP boundary over the canonical facade."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError

from backend.app.dependencies.auth import AuthContext, get_current_user
from backend.app.routes.core.workspace.group_schemas import (
    WorkspaceGroupListResponse,
    WorkspaceGroupMembersResponse,
    WorkspaceGroupResponse,
)
from backend.app.services.workspace_groups.contracts import (
    WorkspaceGroupCreate,
    WorkspaceGroupUpdate,
)
from backend.app.services.workspace_groups.facade import WorkspaceGroupFacade
from backend.app.services.workspace_groups.topology_service import (
    WorkspaceGroupAccessError,
    WorkspaceGroupNotFoundError,
)


router = APIRouter(prefix="/api/v1/workspace-groups", tags=["workspace-groups"])
facade = WorkspaceGroupFacade()


def _read_auth(auth: AuthContext) -> dict:
    return {
        "actor_user_id": auth.user_id,
        "allowed_group_ids": auth.group_ids,
    }


def _write_auth(auth: AuthContext) -> dict:
    return {
        **_read_auth(auth),
        "allowed_workspace_ids": auth.workspace_ids,
    }


def _translate_error(exc: Exception) -> HTTPException:
    if isinstance(exc, WorkspaceGroupNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, WorkspaceGroupAccessError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, IntegrityError):
        return HTTPException(status_code=409, detail="workspace group topology conflict")
    return HTTPException(status_code=500, detail="workspace group operation failed")


@router.get("", response_model=WorkspaceGroupListResponse)
async def list_workspace_groups(
    limit: int = Query(default=200, ge=1, le=200),
    auth: AuthContext = Depends(get_current_user),
):
    """Return every authorized group in one aggregate topology query."""
    groups = await asyncio.to_thread(
        facade.list_groups,
        actor_user_id=auth.user_id,
        allowed_group_ids=auth.group_ids,
        limit=limit,
    )
    projections = [WorkspaceGroupResponse.from_topology(group) for group in groups]
    return WorkspaceGroupListResponse(groups=projections, total=len(projections))


@router.post("", response_model=WorkspaceGroupResponse, status_code=status.HTTP_201_CREATED)
async def create_workspace_group(
    command: WorkspaceGroupCreate,
    auth: AuthContext = Depends(get_current_user),
):
    try:
        topology = await asyncio.to_thread(
            facade.create_group,
            command,
            actor_user_id=auth.user_id,
            allowed_workspace_ids=auth.workspace_ids,
        )
        return WorkspaceGroupResponse.from_topology(topology)
    except Exception as exc:
        raise _translate_error(exc) from exc


@router.get("/{group_id}", response_model=WorkspaceGroupResponse)
async def get_workspace_group(
    group_id: str,
    auth: AuthContext = Depends(get_current_user),
):
    try:
        topology = await asyncio.to_thread(
            facade.get_group,
            group_id,
            **_read_auth(auth),
        )
        return WorkspaceGroupResponse.from_topology(topology)
    except Exception as exc:
        raise _translate_error(exc) from exc


@router.patch("/{group_id}", response_model=WorkspaceGroupResponse)
async def update_workspace_group(
    group_id: str,
    command: WorkspaceGroupUpdate,
    auth: AuthContext = Depends(get_current_user),
):
    try:
        topology = await asyncio.to_thread(
            facade.update_group,
            group_id,
            command,
            **_write_auth(auth),
        )
        return WorkspaceGroupResponse.from_topology(topology)
    except Exception as exc:
        raise _translate_error(exc) from exc


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace_group(
    group_id: str,
    auth: AuthContext = Depends(get_current_user),
):
    try:
        await asyncio.to_thread(
            facade.delete_group,
            group_id,
            **_read_auth(auth),
        )
    except Exception as exc:
        raise _translate_error(exc) from exc


@router.get("/{group_id}/members", response_model=WorkspaceGroupMembersResponse)
async def list_group_members(
    group_id: str,
    auth: AuthContext = Depends(get_current_user),
):
    try:
        topology = await asyncio.to_thread(
            facade.get_group,
            group_id,
            **_read_auth(auth),
        )
        return WorkspaceGroupMembersResponse(
            group_id=group_id,
            members=topology.members,
            total=len(topology.members),
        )
    except Exception as exc:
        raise _translate_error(exc) from exc
