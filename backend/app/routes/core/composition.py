"""Lens Composition core API routes."""
from fastapi import APIRouter, HTTPException, Query, Body
from typing import Optional, Dict, Any, List
from pydantic import BaseModel

from ...models.lens_composition import (
    LensComposition,
    FusedLensContext
)
from ...services.lens.composition_service import CompositionService
from ...services.lens.fusion_service import FusionService

router = APIRouter(prefix="/api/v1/compositions", tags=["compositions"])

composition_service = CompositionService()
fusion_service = FusionService()


class FuseRequest(BaseModel):
    """Request model for fusing composition."""
    composition_id: str
    lens_instances: Dict[str, Dict[str, Any]]


@router.post("", response_model=LensComposition, status_code=201)
async def create_composition(composition: LensComposition = Body(...)) -> LensComposition:
    """
    Create a new composition.

    Creates a new Lens Composition with the provided data.
    """
    try:
        return composition_service.create_composition(composition)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create composition: {str(e)}")


@router.get("/{composition_id}", response_model=LensComposition)
async def get_composition(composition_id: str) -> LensComposition:
    """
    Get composition by ID.

    Returns a specific Lens Composition.
    """
    composition = composition_service.get_composition(composition_id)
    if not composition:
        raise HTTPException(status_code=404, detail=f"Composition {composition_id} not found")
    return composition


@router.put("/{composition_id}", response_model=LensComposition)
async def update_composition(
    composition_id: str,
    updates: Dict[str, Any] = Body(...)
) -> LensComposition:
    """
    Update composition.

    Updates an existing Lens Composition with the provided data.
    """
    composition = composition_service.update_composition(composition_id, updates)
    if not composition:
        raise HTTPException(status_code=404, detail=f"Composition {composition_id} not found")
    return composition


@router.delete("/{composition_id}", status_code=204)
async def delete_composition(composition_id: str):
    """
    Delete composition.

    Deletes a Lens Composition.
    """
    if not composition_service.delete_composition(composition_id):
        raise HTTPException(status_code=404, detail=f"Composition {composition_id} not found")


@router.get("", response_model=List[LensComposition])
async def list_compositions(
    workspace_id: Optional[str] = Query(None, description="Filter by workspace ID"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of results")
) -> List[LensComposition]:
    """
    List compositions.

    Returns a list of Lens Compositions, optionally filtered by workspace.
    """
    return composition_service.list_compositions(workspace_id=workspace_id, limit=limit)


@router.post("/{composition_id}/fuse", response_model=FusedLensContext)
async def fuse_composition(
    composition_id: str,
    request: FuseRequest = Body(...)
) -> FusedLensContext:
    """
    Fuse composition into a single lens context.

    Fuses the composition's lens stack into a single FusedLensContext.
    """
    composition = composition_service.get_composition(composition_id)
    if not composition:
        raise HTTPException(status_code=404, detail=f"Composition {composition_id} not found")

    try:
        from ...models.mind_lens import MindLensInstance

        lens_instances = {}
        for lens_id, lens_data in request.lens_instances.items():
            lens_instances[lens_id] = MindLensInstance(**lens_data)

        return fusion_service.fuse_composition(composition, lens_instances)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fuse composition: {str(e)}")

