"""
Generic Resources API - Neutral interface for all workspace resources

This module provides generic CRUD operations for workspace resources.
All resources use the same routing pattern: /api/v1/workspaces/{workspace_id}/resources/{resource_type}

Resource handlers are registered through the ResourceRegistry, similar to playbook pack registry.
This allows developers to add custom resource types through registration.
"""

import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Path as PathParam, Query, Body

from ...services.resource_registry import get_registry

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/resources",
    tags=["resources"]
)

registry = get_registry()


@router.get("/{resource_type}")
async def list_resources(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    resource_type: str = PathParam(..., description="Resource type (e.g., 'intents', 'chapters', 'artifacts')"),
    tree: Optional[bool] = Query(None, description="Return as tree structure (for hierarchical resources)"),
    status: Optional[str] = Query(None, description="Filter by status"),
    filter: Optional[str] = Query(None, description="Additional filter (JSON string)")
):
    """
    List all resources of a specific type for a workspace

    Generic endpoint that works for any registered resource type.
    Supports resource-specific query parameters through filters.

    Examples:
    - /api/v1/workspaces/123/resources/intents?tree=true
    - /api/v1/workspaces/123/resources/chapters
    - /api/v1/workspaces/123/resources/artifacts?type=illustration
    """
    try:
        handler = registry.get(resource_type)
        if not handler:
            raise HTTPException(
                status_code=404,
                detail=f"Resource type '{resource_type}' not found. Available types: {', '.join(registry.list_types())}"
            )

        # Build filters from query parameters
        filters = {}
        if tree is not None:
            filters['tree'] = tree
        if status:
            filters['status'] = status
        if filter:
            import json
            try:
                filters.update(json.loads(filter))
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid filter JSON")

        resources = await handler.list(workspace_id, filters)

        return {
            "resource_type": resource_type,
            "resources": resources,
            "total": len(resources)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list resources: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list resources: {str(e)}")


@router.get("/{resource_type}/{resource_id}")
async def get_resource(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    resource_type: str = PathParam(..., description="Resource type"),
    resource_id: str = PathParam(..., description="Resource ID")
):
    """
    Get a specific resource

    Generic endpoint that works for any registered resource type.

    Example: /api/v1/workspaces/123/resources/intents/intent-uuid
    """
    try:
        handler = registry.get(resource_type)
        if not handler:
            raise HTTPException(
                status_code=404,
                detail=f"Resource type '{resource_type}' not found"
            )

        resource = await handler.get(workspace_id, resource_id)

        if not resource:
            raise HTTPException(status_code=404, detail=f"Resource {resource_id} not found")

        return resource

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get resource: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get resource: {str(e)}")


@router.post("/{resource_type}", status_code=201)
async def create_resource(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    resource_type: str = PathParam(..., description="Resource type"),
    data: Dict[str, Any] = Body(..., description="Resource data")
):
    """
    Create a new resource

    Generic endpoint that works for any registered resource type.
    """
    try:
        handler = registry.get(resource_type)
        if not handler:
            raise HTTPException(
                status_code=404,
                detail=f"Resource type '{resource_type}' not found"
            )

        created_resource = await handler.create(workspace_id, data)
        return created_resource

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create resource: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create resource: {str(e)}")


@router.put("/{resource_type}/{resource_id}")
async def update_resource(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    resource_type: str = PathParam(..., description="Resource type"),
    resource_id: str = PathParam(..., description="Resource ID"),
    data: Dict[str, Any] = Body(..., description="Updated resource data")
):
    """
    Update an existing resource

    Generic endpoint that works for any registered resource type.
    """
    try:
        handler = registry.get(resource_type)
        if not handler:
            raise HTTPException(
                status_code=404,
                detail=f"Resource type '{resource_type}' not found"
            )

        updated_resource = await handler.update(workspace_id, resource_id, data)
        return updated_resource

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update resource: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update resource: {str(e)}")


@router.delete("/{resource_type}/{resource_id}", status_code=204)
async def delete_resource(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    resource_type: str = PathParam(..., description="Resource type"),
    resource_id: str = PathParam(..., description="Resource ID")
):
    """
    Delete a resource

    Generic endpoint that works for any registered resource type.
    """
    try:
        handler = registry.get(resource_type)
        if not handler:
            raise HTTPException(
                status_code=404,
                detail=f"Resource type '{resource_type}' not found"
            )

        deleted = await handler.delete(workspace_id, resource_id)

        if not deleted:
            raise HTTPException(status_code=404, detail=f"Resource {resource_id} not found")

        return None

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete resource: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete resource: {str(e)}")


@router.get("/{resource_type}/schema")
async def get_resource_schema(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    resource_type: str = PathParam(..., description="Resource type")
):
    """
    Get schema for a resource type

    Returns the schema definition for the resource type.
    Useful for frontend form generation and validation.
    """
    try:
        handler = registry.get(resource_type)
        if not handler:
            raise HTTPException(
                status_code=404,
                detail=f"Resource type '{resource_type}' not found"
            )

        schema = handler.get_schema()
        return schema

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get resource schema: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get resource schema: {str(e)}")

