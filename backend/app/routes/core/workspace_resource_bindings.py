"""
Workspace Resource Binding API Routes
Endpoints for managing workspace resource bindings (overlay layer)
"""

import asyncio
import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, Path as PathParam

from ...models.workspace_resource_binding import (
    WorkspaceResourceBinding,
    CreateWorkspaceResourceBindingRequest,
    UpdateWorkspaceResourceBindingRequest,
    ResourceType,
)
from ...services.workspace_resource_bindings import (
    WorkspaceResourceBindingConflictError,
    WorkspaceResourceBindingFacade,
    WorkspaceResourceBindingNotFoundError,
    WorkspaceResourceBindingWorkspaceMismatchError,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/resource-bindings",
    tags=["workspace-resource-bindings"],
)


def get_binding_facade() -> WorkspaceResourceBindingFacade:
    """Return the canonical workspace resource binding service."""
    return WorkspaceResourceBindingFacade()


def _translate_error(exc: Exception) -> HTTPException:
    if isinstance(exc, WorkspaceResourceBindingWorkspaceMismatchError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, WorkspaceResourceBindingNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, WorkspaceResourceBindingConflictError):
        return HTTPException(status_code=409, detail=str(exc))
    logger.error("Workspace resource binding operation failed", exc_info=True)
    return HTTPException(status_code=500, detail=str(exc))


@router.post("/", response_model=WorkspaceResourceBinding, status_code=201)
async def create_binding(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    request: CreateWorkspaceResourceBindingRequest = ...,
):
    """
    Create a new workspace resource binding

    Binds a shared resource (playbook, tool, or data_source) to a workspace
    with optional local overrides.
    """
    try:
        return await asyncio.to_thread(
            get_binding_facade().create,
            workspace_id=workspace_id,
            request=request,
        )
    except Exception as e:
        raise _translate_error(e) from e


@router.get("/", response_model=List[WorkspaceResourceBinding])
async def list_bindings(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    resource_type: Optional[ResourceType] = Query(
        None, description="Filter by resource type"
    ),
):
    """
    List all resource bindings for a workspace

    Optionally filter by resource_type.
    """
    try:
        return await asyncio.to_thread(
            get_binding_facade().list_for_workspace,
            workspace_id=workspace_id,
            resource_type=resource_type,
        )
    except Exception as e:
        raise _translate_error(e) from e


@router.get("/{resource_type}/{resource_id}", response_model=WorkspaceResourceBinding)
async def get_binding(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    resource_type: ResourceType = PathParam(..., description="Resource type"),
    resource_id: str = PathParam(..., description="Resource ID"),
):
    """
    Get a specific resource binding

    Returns the binding for a specific resource in a workspace.
    """
    try:
        return await asyncio.to_thread(
            get_binding_facade().get,
            workspace_id=workspace_id,
            resource_type=resource_type,
            resource_id=resource_id,
        )
    except Exception as e:
        raise _translate_error(e) from e


@router.put("/{resource_type}/{resource_id}", response_model=WorkspaceResourceBinding)
async def update_binding(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    resource_type: ResourceType = PathParam(..., description="Resource type"),
    resource_id: str = PathParam(..., description="Resource ID"),
    request: UpdateWorkspaceResourceBindingRequest = ...,
):
    """
    Update a resource binding

    Updates access_mode and/or overrides for a binding.
    """
    try:
        return await asyncio.to_thread(
            get_binding_facade().update,
            workspace_id=workspace_id,
            resource_type=resource_type,
            resource_id=resource_id,
            request=request,
        )
    except Exception as e:
        raise _translate_error(e) from e


@router.delete("/{resource_type}/{resource_id}", status_code=204)
async def delete_binding(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    resource_type: ResourceType = PathParam(..., description="Resource type"),
    resource_id: str = PathParam(..., description="Resource ID"),
):
    """
    Delete a resource binding

    Removes the binding, making the resource unavailable in this workspace.
    """
    try:
        await asyncio.to_thread(
            get_binding_facade().delete,
            workspace_id=workspace_id,
            resource_type=resource_type,
            resource_id=resource_id,
        )
        return None
    except Exception as e:
        raise _translate_error(e) from e


@router.get(
    "/by-resource/{resource_type}/{resource_id}",
    response_model=List[WorkspaceResourceBinding],
)
async def list_workspaces_using_resource(
    resource_type: ResourceType = PathParam(..., description="Resource type"),
    resource_id: str = PathParam(..., description="Resource ID"),
):
    """
    List all workspaces that use a specific resource

    Useful for finding which workspaces are affected when a shared resource changes.
    """
    try:
        return await asyncio.to_thread(
            get_binding_facade().list_workspaces_using_resource,
            resource_type=resource_type,
            resource_id=resource_id,
        )
    except Exception as e:
        raise _translate_error(e) from e
