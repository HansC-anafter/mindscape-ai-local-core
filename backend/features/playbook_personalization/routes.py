"""
Playbook Personalization API routes
Handles personalized Playbook variants and optimization
"""

import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel

from backend.app.services.playbook_service import PlaybookService
from backend.app.models.personalized_playbook import (
    CreateVariantRequest,
    UpdateVariantRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["playbook-personalization"])

# Initialize services
from backend.app.services.mindscape_store import MindscapeStore
store = MindscapeStore()
playbook_service = PlaybookService(store=store)


def _get_optimization_service():
    from backend.app.services.playbook_optimization_service import (
        PlaybookOptimizationService,
    )

    return PlaybookOptimizationService()


def _personalized_variants_not_available() -> HTTPException:
    return HTTPException(
        status_code=501,
        detail=(
            "Personalized playbook variant persistence is not available in the "
            "current PlaybookService/PlaybookRegistry backend."
        ),
    )


class OptimizeRequest(BaseModel):
    """Request to analyze and generate optimization suggestions"""
    include_usage_analysis: bool = True


class CreateVariantFromSuggestionsRequest(BaseModel):
    """Request to create variant from selected suggestions"""
    variant_name: str
    selected_suggestions: List[Dict[str, Any]]


@router.post("/{playbook_code}/optimize", response_model=Dict[str, Any])
async def optimize_playbook(
    playbook_code: str,
    profile_id: str = Query("default-user"),
    request: Optional[OptimizeRequest] = Body(None)
):
    """
    Analyze Playbook usage and generate optimization suggestions

    Returns usage analysis and LLM-generated suggestions
    """
    try:
        optimization_service = _get_optimization_service()

        # Analyze usage
        usage_analysis = await optimization_service.analyze_usage(profile_id, playbook_code)

        # Generate suggestions
        suggestions = await optimization_service.generate_suggestions(
            profile_id,
            playbook_code,
            usage_analysis
        )

        return {
            "usage_analysis": usage_analysis.dict(),
            "suggestions": [s.dict() for s in suggestions]
        }
    except Exception as e:
        logger.error(f"Failed to optimize playbook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{playbook_code}/variants", response_model=List[Dict[str, Any]])
async def list_variants(
    playbook_code: str,
    profile_id: str = Query("default-user"),
    active_only: bool = Query(False)
):
    """List all personalized variants for a Playbook"""
    try:
        variants = playbook_service.registry.list_variants(playbook_code)
        if active_only:
            variants = [variant for variant in variants if variant.get("is_active", True)]
        return variants
    except Exception as e:
        logger.error(f"Failed to list variants: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{playbook_code}/variants/{variant_id}", response_model=Dict[str, Any])
async def get_variant(
    playbook_code: str,
    variant_id: str,
    profile_id: str = Query("default-user")
):
    """Get a specific variant"""
    try:
        variant = playbook_service.registry.get_variant(playbook_code, variant_id)
        if not variant:
            raise HTTPException(status_code=404, detail="Variant not found")

        return variant
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get variant: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{playbook_code}/variants/copy", response_model=Dict[str, Any])
async def copy_system_version(
    playbook_code: str,
    profile_id: str = Query("default-user"),
    variant_name: str = Query(..., description="Name for the copied variant"),
    variant_description: Optional[str] = Query(None, description="Description for the variant")
):
    """Copy system Playbook as a personal variant (Flow A: manual copy)"""
    raise _personalized_variants_not_available()


@router.post("/{playbook_code}/variants", response_model=Dict[str, Any])
async def create_variant(
    playbook_code: str,
    profile_id: str = Query("default-user"),
    request: CreateVariantRequest = Body(...)
):
    """Create a new personalized variant"""
    raise _personalized_variants_not_available()


@router.post("/{playbook_code}/variants/from-suggestions", response_model=Dict[str, Any])
async def create_variant_from_suggestions(
    playbook_code: str,
    profile_id: str = Query("default-user"),
    request: CreateVariantFromSuggestionsRequest = Body(...)
):
    """Create a variant based on selected optimization suggestions"""
    raise _personalized_variants_not_available()


@router.patch("/{playbook_code}/variants/{variant_id}", response_model=Dict[str, Any])
async def update_variant(
    playbook_code: str,
    variant_id: str,
    profile_id: str = Query("default-user"),
    request: UpdateVariantRequest = Body(...)
):
    """Update a personalized variant"""
    raise _personalized_variants_not_available()


@router.delete("/{playbook_code}/variants/{variant_id}")
async def delete_variant(
    playbook_code: str,
    variant_id: str,
    profile_id: str = Query("default-user")
):
    """Delete a personalized variant"""
    raise _personalized_variants_not_available()
