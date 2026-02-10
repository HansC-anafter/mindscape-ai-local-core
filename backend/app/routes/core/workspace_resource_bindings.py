"""
Workspace Resource Binding API Routes
Endpoints for managing workspace resource bindings (overlay layer)
"""

import asyncio
import logging
import uuid
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, Path as PathParam

from ...models.workspace_resource_binding import (
    WorkspaceResourceBinding,
    CreateWorkspaceResourceBindingRequest,
    UpdateWorkspaceResourceBindingRequest,
    ResourceType,
)
from ...services.stores.workspace_resource_binding_store import (
    WorkspaceResourceBindingStore,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/resource-bindings",
    tags=["workspace-resource-bindings"],
)


# Initialize store
def get_binding_store() -> WorkspaceResourceBindingStore:
    """Get WorkspaceResourceBindingStore instance"""
    return WorkspaceResourceBindingStore()


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
        # Ensure workspace_id matches
        if request.workspace_id != workspace_id:
            raise HTTPException(
                status_code=400, detail="Workspace ID in path must match request body"
            )

        store = get_binding_store()

        # Check if binding already exists
        existing = await asyncio.to_thread(
            store.get_binding_by_resource,
            workspace_id=workspace_id,
            resource_type=request.resource_type,
            resource_id=request.resource_id,
        )
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Binding already exists for {request.resource_type}:{request.resource_id}",
            )

        # Create binding
        binding = WorkspaceResourceBinding(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            resource_type=request.resource_type,
            resource_id=request.resource_id,
            access_mode=request.access_mode,
            overrides=request.overrides,
        )

        saved_binding = await asyncio.to_thread(store.save_binding, binding)
        return saved_binding

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create binding: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


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
        store = get_binding_store()
        bindings = await asyncio.to_thread(
            store.list_bindings_by_workspace,
            workspace_id=workspace_id,
            resource_type=resource_type,
        )
        return bindings
    except Exception as e:
        logger.error(f"Failed to list bindings: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


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
        store = get_binding_store()
        binding = await asyncio.to_thread(
            store.get_binding_by_resource,
            workspace_id=workspace_id,
            resource_type=resource_type,
            resource_id=resource_id,
        )

        if not binding:
            raise HTTPException(
                status_code=404,
                detail=f"Binding not found for {resource_type}:{resource_id}",
            )

        return binding
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get binding: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


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
        store = get_binding_store()
        binding = await asyncio.to_thread(
            store.get_binding_by_resource,
            workspace_id=workspace_id,
            resource_type=resource_type,
            resource_id=resource_id,
        )

        if not binding:
            raise HTTPException(
                status_code=404,
                detail=f"Binding not found for {resource_type}:{resource_id}",
            )

        # Update fields
        if request.access_mode is not None:
            binding.access_mode = request.access_mode
        if request.overrides is not None:
            binding.overrides = request.overrides

        saved_binding = await asyncio.to_thread(store.save_binding, binding)
        return saved_binding

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update binding: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


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
        store = get_binding_store()
        deleted = await asyncio.to_thread(
            store.delete_binding_by_resource,
            workspace_id=workspace_id,
            resource_type=resource_type,
            resource_id=resource_id,
        )

        if not deleted:
            raise HTTPException(
                status_code=404,
                detail=f"Binding not found for {resource_type}:{resource_id}",
            )

        return None
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete binding: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


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
        store = get_binding_store()
        bindings = await asyncio.to_thread(
            store.list_bindings_by_resource,
            resource_type=resource_type,
            resource_id=resource_id,
        )
        return bindings
    except Exception as e:
        logger.error(f"Failed to list workspaces using resource: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
