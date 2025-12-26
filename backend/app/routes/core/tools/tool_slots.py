"""
Tool Slot Mapping API Routes

CRUD operations for tool slot mappings at workspace and project levels.
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
import uuid
from datetime import datetime

from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.stores.tool_slot_mappings_store import (
    ToolSlotMappingsStore,
    ToolSlotMapping
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/tool-slots", tags=["tool-slots"])


# Request/Response models
class ToolSlotMappingRequest(BaseModel):
    """Request model for creating/updating tool slot mapping"""
    slot: str = Field(..., description="Tool slot identifier (e.g., 'cms.footer.apply_style')")
    tool_id: str = Field(..., description="Concrete tool ID (e.g., 'wp-ets1.wordpress.update_footer')")
    priority: int = Field(default=0, description="Priority (higher = preferred, default 0)")
    enabled: bool = Field(default=True, description="Whether mapping is enabled")
    metadata: Optional[dict] = Field(default_factory=dict, description="Optional metadata")


class ToolSlotMappingResponse(BaseModel):
    """Response model for tool slot mapping"""
    id: str
    workspace_id: str
    project_id: Optional[str]
    slot: str
    tool_id: str
    priority: int
    enabled: bool
    metadata: dict
    created_at: str
    updated_at: str


class ToolSlotMappingUpdateRequest(BaseModel):
    """Request model for updating tool slot mapping"""
    tool_id: Optional[str] = Field(None, description="Concrete tool ID to update")
    priority: Optional[int] = Field(None, description="Priority to update")
    enabled: Optional[bool] = Field(None, description="Enable/disable mapping")
    metadata: Optional[dict] = Field(None, description="Metadata to update")


# Dependency injection
def get_store() -> MindscapeStore:
    """Get MindscapeStore instance"""
    return MindscapeStore()


def get_mappings_store(store: MindscapeStore = Depends(get_store)) -> ToolSlotMappingsStore:
    """Get ToolSlotMappingsStore instance"""
    return ToolSlotMappingsStore(store.db_path)


# Routes
@router.post("/workspaces/{workspace_id}/mappings", response_model=ToolSlotMappingResponse)
async def create_workspace_mapping(
    workspace_id: str,
    request: ToolSlotMappingRequest,
    mappings_store: ToolSlotMappingsStore = Depends(get_mappings_store)
):
    """
    Create a workspace-level tool slot mapping

    Args:
        workspace_id: Workspace ID
        request: Mapping request
        mappings_store: ToolSlotMappingsStore instance

    Returns:
        Created mapping
    """
    try:
        mapping = ToolSlotMapping(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            project_id=None,  # Workspace-level
            slot=request.slot,
            tool_id=request.tool_id,
            priority=request.priority,
            enabled=request.enabled,
            metadata=request.metadata
        )

        created = mappings_store.create_mapping(mapping)
        return ToolSlotMappingResponse(**created.to_dict())

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create workspace mapping: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create mapping: {str(e)}")


@router.post("/workspaces/{workspace_id}/projects/{project_id}/mappings", response_model=ToolSlotMappingResponse)
async def create_project_mapping(
    workspace_id: str,
    project_id: str,
    request: ToolSlotMappingRequest,
    mappings_store: ToolSlotMappingsStore = Depends(get_mappings_store)
):
    """
    Create a project-level tool slot mapping

    Project-level mappings have higher priority than workspace-level mappings.

    Args:
        workspace_id: Workspace ID
        project_id: Project ID
        request: Mapping request
        mappings_store: ToolSlotMappingsStore instance

    Returns:
        Created mapping
    """
    try:
        mapping = ToolSlotMapping(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            project_id=project_id,  # Project-level
            slot=request.slot,
            tool_id=request.tool_id,
            priority=request.priority,
            enabled=request.enabled,
            metadata=request.metadata
        )

        created = mappings_store.create_mapping(mapping)
        return ToolSlotMappingResponse(**created.to_dict())

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create project mapping: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create mapping: {str(e)}")


@router.get("/workspaces/{workspace_id}/mappings", response_model=List[ToolSlotMappingResponse])
async def list_workspace_mappings(
    workspace_id: str,
    slot: Optional[str] = Query(None, description="Filter by slot"),
    enabled_only: bool = Query(False, description="Only return enabled mappings"),
    mappings_store: ToolSlotMappingsStore = Depends(get_mappings_store)
):
    """
    List workspace-level tool slot mappings

    Args:
        workspace_id: Workspace ID
        slot: Optional slot filter
        enabled_only: Only return enabled mappings
        mappings_store: ToolSlotMappingsStore instance

    Returns:
        List of mappings
    """
    try:
        mappings = mappings_store.get_mappings(
            slot=slot,
            workspace_id=workspace_id,
            project_id=None,  # Workspace-level only
            enabled_only=enabled_only
        )
        return [ToolSlotMappingResponse(**m) for m in mappings]
    except Exception as e:
        logger.error(f"Failed to list workspace mappings: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list mappings: {str(e)}")


@router.get("/workspaces/{workspace_id}/projects/{project_id}/mappings", response_model=List[ToolSlotMappingResponse])
async def list_project_mappings(
    workspace_id: str,
    project_id: str,
    slot: Optional[str] = Query(None, description="Filter by slot"),
    enabled_only: bool = Query(False, description="Only return enabled mappings"),
    mappings_store: ToolSlotMappingsStore = Depends(get_mappings_store)
):
    """
    List project-level tool slot mappings

    Args:
        workspace_id: Workspace ID
        project_id: Project ID
        slot: Optional slot filter
        enabled_only: Only return enabled mappings
        mappings_store: ToolSlotMappingsStore instance

    Returns:
        List of mappings
    """
    try:
        mappings = mappings_store.get_mappings(
            slot=slot,
            workspace_id=workspace_id,
            project_id=project_id,
            enabled_only=enabled_only
        )
        return [ToolSlotMappingResponse(**m) for m in mappings]
    except Exception as e:
        logger.error(f"Failed to list project mappings: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list mappings: {str(e)}")


@router.get("/mappings/{mapping_id}", response_model=ToolSlotMappingResponse)
async def get_mapping(
    mapping_id: str,
    mappings_store: ToolSlotMappingsStore = Depends(get_mappings_store)
):
    """
    Get a specific tool slot mapping by ID

    Args:
        mapping_id: Mapping ID
        mappings_store: ToolSlotMappingsStore instance

    Returns:
        Mapping details
    """
    try:
        mapping = mappings_store.get_mapping(mapping_id)
        if not mapping:
            raise HTTPException(status_code=404, detail=f"Mapping not found: {mapping_id}")
        return ToolSlotMappingResponse(**mapping.to_dict())
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get mapping {mapping_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get mapping: {str(e)}")


@router.patch("/mappings/{mapping_id}", response_model=ToolSlotMappingResponse)
async def update_mapping(
    mapping_id: str,
    request: ToolSlotMappingUpdateRequest,
    mappings_store: ToolSlotMappingsStore = Depends(get_mappings_store)
):
    """
    Update a tool slot mapping

    Args:
        mapping_id: Mapping ID
        request: Update request
        mappings_store: ToolSlotMappingsStore instance

    Returns:
        Updated mapping
    """
    try:
        updates = {}
        if request.tool_id is not None:
            updates['tool_id'] = request.tool_id
        if request.priority is not None:
            updates['priority'] = request.priority
        if request.enabled is not None:
            updates['enabled'] = request.enabled
        if request.metadata is not None:
            updates['metadata'] = request.metadata

        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        updated = mappings_store.update_mapping(mapping_id, **updates)
        if not updated:
            raise HTTPException(status_code=404, detail=f"Mapping not found: {mapping_id}")

        return ToolSlotMappingResponse(**updated.to_dict())
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update mapping {mapping_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update mapping: {str(e)}")


@router.delete("/mappings/{mapping_id}")
async def delete_mapping(
    mapping_id: str,
    mappings_store: ToolSlotMappingsStore = Depends(get_mappings_store)
):
    """
    Delete a tool slot mapping

    Args:
        mapping_id: Mapping ID
        mappings_store: ToolSlotMappingsStore instance

    Returns:
        Success status
    """
    try:
        success = mappings_store.delete_mapping(mapping_id)
        if not success:
            raise HTTPException(status_code=404, detail=f"Mapping not found: {mapping_id}")
        return {"success": True, "message": f"Mapping {mapping_id} deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete mapping {mapping_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete mapping: {str(e)}")


@router.post("/resolve")
async def resolve_slot(
    slot: str = Query(..., description="Tool slot to resolve"),
    workspace_id: str = Query(..., description="Workspace ID"),
    project_id: Optional[str] = Query(None, description="Optional project ID"),
    mappings_store: ToolSlotMappingsStore = Depends(get_mappings_store)
):
    """
    Resolve a tool slot to concrete tool ID

    This endpoint demonstrates how slot resolution works.
    In practice, resolution happens automatically during playbook execution.

    Args:
        slot: Tool slot identifier
        workspace_id: Workspace ID
        project_id: Optional project ID
        mappings_store: ToolSlotMappingsStore instance

    Returns:
        Resolved tool ID and mapping details
    """
    try:
        from backend.app.services.tool_slot_resolver import get_tool_slot_resolver, SlotNotFoundError

        resolver = get_tool_slot_resolver()
        try:
            tool_id = await resolver.resolve(
                slot=slot,
                workspace_id=workspace_id,
                project_id=project_id
            )

            # Get mapping details
            mappings = mappings_store.get_mappings(
                slot=slot,
                workspace_id=workspace_id,
                project_id=project_id,
                enabled_only=True
            )
            mapping = mappings[0] if mappings else None

            return {
                "slot": slot,
                "tool_id": tool_id,
                "workspace_id": workspace_id,
                "project_id": project_id,
                "mapping": mapping,
                "resolved": True
            }
        except SlotNotFoundError as e:
            return {
                "slot": slot,
                "tool_id": None,
                "workspace_id": workspace_id,
                "project_id": project_id,
                "error": str(e),
                "resolved": False
            }
    except Exception as e:
        logger.error(f"Failed to resolve slot '{slot}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to resolve slot: {str(e)}")









