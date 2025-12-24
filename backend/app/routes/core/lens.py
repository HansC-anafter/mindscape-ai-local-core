"""Mind Lens core API routes."""
from fastapi import APIRouter, HTTPException, Query, Body
from typing import Optional, Dict, Any, List
from pydantic import BaseModel

from ...models.mind_lens import (
    MindLensSchema,
    MindLensInstance,
    RuntimeMindLens
)
from ...services.lens.mind_lens_service import MindLensService

router = APIRouter(prefix="/api/v1/lenses", tags=["lenses"])

mind_lens_service = MindLensService()


class ResolveRequest(BaseModel):
    """Request model for resolving Mind Lens."""
    user_id: str
    workspace_id: str
    playbook_id: Optional[str] = None
    role_hint: Optional[str] = None


@router.get("/schemas/{role}", response_model=MindLensSchema)
async def get_schema(role: str) -> MindLensSchema:
    """
    Get Mind Lens schema for a role.

    Returns the schema definition for a specific role.
    """
    schema = mind_lens_service.get_schema_by_role(role)
    if not schema:
        raise HTTPException(status_code=404, detail=f"Schema for role {role} not found")
    return schema


@router.get("/instances/{instance_id}", response_model=MindLensInstance)
async def get_instance(instance_id: str) -> MindLensInstance:
    """
    Get Mind Lens instance by ID.

    Returns a specific Mind Lens instance.
    """
    instance = mind_lens_service.get_instance(instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail=f"Instance {instance_id} not found")
    return instance


@router.post("/instances", response_model=MindLensInstance, status_code=201)
async def create_instance(instance: MindLensInstance = Body(...)) -> MindLensInstance:
    """
    Create a new Mind Lens instance.

    Creates a new Mind Lens instance with the provided data.
    """
    try:
        return mind_lens_service.create_instance(instance)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create instance: {str(e)}")


@router.put("/instances/{instance_id}", response_model=MindLensInstance)
async def update_instance(
    instance_id: str,
    updates: Dict[str, Any] = Body(...)
) -> MindLensInstance:
    """
    Update a Mind Lens instance.

    Updates an existing Mind Lens instance with the provided data.
    """
    instance = mind_lens_service.update_instance(instance_id, updates)
    if not instance:
        raise HTTPException(status_code=404, detail=f"Instance {instance_id} not found")
    return instance


@router.post("/resolve", response_model=RuntimeMindLens)
async def resolve(request: ResolveRequest = Body(...)) -> RuntimeMindLens:
    """
    Resolve Mind Lens for execution context.

    Resolves and returns a RuntimeMindLens for the given context.
    """
    resolved = mind_lens_service.resolve_lens(
        user_id=request.user_id,
        workspace_id=request.workspace_id,
        playbook_id=request.playbook_id,
        role_hint=request.role_hint
    )
    if not resolved:
        raise HTTPException(status_code=404, detail="Could not resolve Mind Lens for the given context")
    return resolved

