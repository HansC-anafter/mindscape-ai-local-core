"""
Playbook Resources API - Generic resource management for all playbooks

This module provides generic CRUD operations for playbook-specific resources.
All playbooks can use these endpoints by specifying their resource types.

Resource storage structure (new overlay architecture):
- Shared resources: Based on playbook scope (system/tenant/profile)
- Workspace overlay: {workspace_storage}/workspace_overlays/playbooks/{playbook_code}/resources/{resource_type}/
- Old path (backward compatibility): {workspace_storage}/playbooks/{playbook_code}/resources/{resource_type}/

Reading strategy:
1. Check workspace overlay path (new path)
2. Check shared resource path (if template playbook)
3. Fallback to old workspace path

Writing strategy:
- Always write to workspace overlay path (new path)
"""

import logging
import json
from typing import List, Optional, Dict, Any
from pathlib import Path
from fastapi import APIRouter, HTTPException, Path as PathParam, Query, Body

from ....models.workspace import Workspace
from ....services.mindscape_store import MindscapeStore
from ....services.playbook_resource_overlay_service import PlaybookResourceOverlayService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/playbooks/{playbook_code}/resources",
    tags=["playbook-resources"]
)

store = MindscapeStore()
overlay_service = PlaybookResourceOverlayService(store=store)


@router.get("/{resource_type}", response_model=List[Dict[str, Any]])
async def list_resources(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    playbook_code: str = PathParam(..., description="Playbook code"),
    resource_type: str = PathParam(..., description="Resource type (e.g., 'chapters', 'lessons', 'sections')")
):
    """
    List all resources of a specific type for a playbook

    Generic endpoint that works for any playbook and resource type.
    Supports overlay architecture:
    - Reads from shared resources (if template playbook)
    - Applies workspace overlay
    - Falls back to old workspace path (backward compatibility)

    Examples:
    - /api/v1/workspaces/123/playbooks/yearly_personal_book/resources/chapters
    - /api/v1/workspaces/123/playbooks/course_writing/resources/lessons
    """
    try:
        resources = await overlay_service.list_resources(
            workspace_id=workspace_id,
            playbook_code=playbook_code,
            resource_type=resource_type
        )
        return resources

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list resources: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{resource_type}/{resource_id}", response_model=Dict[str, Any])
async def get_resource(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    playbook_code: str = PathParam(..., description="Playbook code"),
    resource_type: str = PathParam(..., description="Resource type"),
    resource_id: str = PathParam(..., description="Resource ID")
):
    """
    Get a specific resource

    Supports overlay architecture:
    - Reads from workspace overlay path (new path)
    - Reads from shared resources (if template playbook)
    - Falls back to old workspace path (backward compatibility)
    - Applies overlay from workspace_resource_binding

    Example: /api/v1/workspaces/123/playbooks/yearly_personal_book/resources/chapters/chapter-01
    """
    try:
        resource = await overlay_service.get_resource(
            workspace_id=workspace_id,
            playbook_code=playbook_code,
            resource_type=resource_type,
            resource_id=resource_id
        )

        if not resource:
            raise HTTPException(status_code=404, detail=f"Resource {resource_id} not found")

        return resource

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get resource: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{resource_type}", response_model=Dict[str, Any], status_code=201)
async def create_resource(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    playbook_code: str = PathParam(..., description="Playbook code"),
    resource_type: str = PathParam(..., description="Resource type"),
    resource: Dict[str, Any] = Body(..., description="Resource data")
):
    """
    Create a new resource

    The resource must include an 'id' field. If not provided, a UUID will be generated.
    Always writes to workspace overlay path (new path).

    Writing strategy:
    - Only write to workspace overlay path
    - Never write to shared path or old workspace path
    """
    try:
        import uuid
        from datetime import datetime, timezone

        if 'id' not in resource:
            resource['id'] = str(uuid.uuid4())

        resource_id = resource['id']
        resource['created_at'] = resource.get('created_at', _utc_now().isoformat())
        resource['updated_at'] = resource.get('updated_at', _utc_now().isoformat())

        # Check if resource already exists
        existing = await overlay_service.get_resource(
            workspace_id=workspace_id,
            playbook_code=playbook_code,
            resource_type=resource_type,
            resource_id=resource_id
        )

        if existing:
            raise HTTPException(status_code=409, detail=f"Resource {resource_id} already exists")

        # Save to overlay path
        saved_resource = await overlay_service.save_resource(
            workspace_id=workspace_id,
            playbook_code=playbook_code,
            resource_type=resource_type,
            resource=resource
        )

        logger.info(f"Created resource {resource_type}/{resource_id} for playbook {playbook_code} in workspace {workspace_id}")
        return saved_resource

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create resource: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{resource_type}/{resource_id}", response_model=Dict[str, Any])
async def update_resource(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    playbook_code: str = PathParam(..., description="Playbook code"),
    resource_type: str = PathParam(..., description="Resource type"),
    resource_id: str = PathParam(..., description="Resource ID"),
    resource: Dict[str, Any] = Body(..., description="Updated resource data")
):
    """
    Update an existing resource

    Always writes to workspace overlay path (new path).
    """
    try:
        from datetime import datetime, timezone

        # Check if resource exists
        existing = await overlay_service.get_resource(
            workspace_id=workspace_id,
            playbook_code=playbook_code,
            resource_type=resource_type,
            resource_id=resource_id
        )

        if not existing:
            raise HTTPException(status_code=404, detail=f"Resource {resource_id} not found")

        # Preserve created_at
        resource['id'] = resource_id
        resource['created_at'] = resource.get('created_at', existing.get('created_at', _utc_now().isoformat()))
        resource['updated_at'] = _utc_now().isoformat()

        # Save to overlay path
        updated_resource = await overlay_service.save_resource(
            workspace_id=workspace_id,
            playbook_code=playbook_code,
            resource_type=resource_type,
            resource=resource
        )

        logger.info(f"Updated resource {resource_type}/{resource_id} for playbook {playbook_code} in workspace {workspace_id}")
        return updated_resource

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update resource: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{resource_type}/{resource_id}", status_code=204)
async def delete_resource(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    playbook_code: str = PathParam(..., description="Playbook code"),
    resource_type: str = PathParam(..., description="Resource type"),
    resource_id: str = PathParam(..., description="Resource ID")
):
    """
    Delete a resource

    Deletes from overlay path (new path) or old workspace path (backward compatibility).
    """
    try:
        deleted = await overlay_service.delete_resource(
            workspace_id=workspace_id,
            playbook_code=playbook_code,
            resource_type=resource_type,
            resource_id=resource_id
        )

        if not deleted:
            raise HTTPException(status_code=404, detail=f"Resource {resource_id} not found")

        logger.info(f"Deleted resource {resource_type}/{resource_id} for playbook {playbook_code} in workspace {workspace_id}")
        return None

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete resource: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{resource_type}/schema", response_model=Dict[str, Any])
async def get_resource_schema(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    playbook_code: str = PathParam(..., description="Playbook code"),
    resource_type: str = PathParam(..., description="Resource type")
):
    """
    Get schema for a resource type

    Returns the schema definition from the playbook's resource_types configuration.
    """
    try:
        from ....services.playbook_service import PlaybookService

        playbook_service = PlaybookService(store=store)
        playbook = await playbook_service.get_playbook(playbook_code)

        if not playbook:
            raise HTTPException(status_code=404, detail=f"Playbook {playbook_code} not found")

        # Try to get schema from playbook definition
        # This would be in playbook.json under resource_types
        # For now, return a generic schema
        return {
            "resource_type": resource_type,
            "schema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "title": {"type": "string"},
                    "content": {"type": "string"},
                    "created_at": {"type": "string"},
                    "updated_at": {"type": "string"}
                },
                "required": ["id"]
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get resource schema: {e}")
        raise HTTPException(status_code=500, detail=str(e))

