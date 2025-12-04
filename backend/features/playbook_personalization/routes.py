"""
Playbook Personalization API routes
Handles personalized Playbook variants and optimization
"""

import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel

from backend.app.services.playbook_service import PlaybookService
from backend.app.services.playbook_optimization_service import PlaybookOptimizationService
from backend.app.models.personalized_playbook import (
    CreateVariantRequest,
    UpdateVariantRequest,
    OptimizationSuggestion,
    UsageAnalysis
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["playbook-personalization"])

# Initialize services
from backend.app.services.mindscape_store import MindscapeStore
store = MindscapeStore()
playbook_service = PlaybookService(store=store)
optimization_service = PlaybookOptimizationService()


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
        variants = playbook_store.list_personalized_variants(
            profile_id,
            base_playbook_code=playbook_code,
            active_only=active_only
        )
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
        variant = playbook_service.playbook_store.get_personalized_variant(variant_id)
        if not variant:
            raise HTTPException(status_code=404, detail="Variant not found")

        # Verify ownership
        if variant["profile_id"] != profile_id or variant["base_playbook_code"] != playbook_code:
            raise HTTPException(status_code=403, detail="Access denied")

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
    try:
        # Get base Playbook
        from backend.app.services.playbook_loader import PlaybookLoader
        loader = PlaybookLoader()
        playbook = loader.get_playbook_by_code(playbook_code)

        if not playbook:
            raise HTTPException(status_code=404, detail="Playbook not found")

        # Check if user already has a default variant
        existing_default = playbook_store.get_default_variant(profile_id, playbook_code)
        is_default = existing_default is None  # Set as default if no existing default

        variant_data = {
            "profile_id": profile_id,
            "base_playbook_code": playbook_code,
            "base_version": playbook.metadata.version,
            "variant_name": variant_name,
            "variant_description": variant_description or f"複製自系統版本 {playbook.metadata.version}",
            "personalized_sop_content": playbook.sop_content,  # Copy SOP as-is
            "skip_steps": None,
            "custom_checklist": None,
            "execution_params": None,
            "is_default": is_default
        }

        variant = playbook_store.create_personalized_variant(variant_data)
        return variant
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to copy system version: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{playbook_code}/variants", response_model=Dict[str, Any])
async def create_variant(
    playbook_code: str,
    profile_id: str = Query("default-user"),
    request: CreateVariantRequest = Body(...)
):
    """Create a new personalized variant"""
    try:
        # Get base Playbook to get version
        playbook = await playbook_service.get_playbook(
            playbook_code=playbook_code,
            locale="zh-TW"  # Default locale, can be made configurable
        )

        if not playbook:
            raise HTTPException(status_code=404, detail="Playbook not found")

        variant_data = {
            "profile_id": profile_id,
            "base_playbook_code": playbook_code,
            "base_version": playbook.metadata.version,
            "variant_name": request.variant_name,
            "variant_description": request.variant_description,
            "personalized_sop_content": request.personalized_sop_content,
            "skip_steps": request.skip_steps,
            "custom_checklist": request.custom_checklist,
            "execution_params": request.execution_params,
            "is_default": request.is_default
        }

        variant = playbook_store.create_personalized_variant(variant_data)
        return variant
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create variant: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{playbook_code}/variants/from-suggestions", response_model=Dict[str, Any])
async def create_variant_from_suggestions(
    playbook_code: str,
    profile_id: str = Query("default-user"),
    request: CreateVariantFromSuggestionsRequest = Body(...)
):
    """Create a variant based on selected optimization suggestions"""
    try:
        variant = await optimization_service.create_variant_from_suggestions(
            profile_id,
            playbook_code,
            request.variant_name,
            request.selected_suggestions
        )
        return variant
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create variant from suggestions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{playbook_code}/variants/{variant_id}", response_model=Dict[str, Any])
async def update_variant(
    playbook_code: str,
    variant_id: str,
    profile_id: str = Query("default-user"),
    request: UpdateVariantRequest = Body(...)
):
    """Update a personalized variant"""
    try:
        # Verify ownership
        variant = playbook_store.get_personalized_variant(variant_id)
        if not variant:
            raise HTTPException(status_code=404, detail="Variant not found")

        if variant["profile_id"] != profile_id or variant["base_playbook_code"] != playbook_code:
            raise HTTPException(status_code=403, detail="Access denied")

        # Build updates dict
        updates = {}
        if request.variant_name is not None:
            updates["variant_name"] = request.variant_name
        if request.variant_description is not None:
            updates["variant_description"] = request.variant_description
        if request.personalized_sop_content is not None:
            updates["personalized_sop_content"] = request.personalized_sop_content
        if request.skip_steps is not None:
            updates["skip_steps"] = request.skip_steps
        if request.custom_checklist is not None:
            updates["custom_checklist"] = request.custom_checklist
        if request.execution_params is not None:
            updates["execution_params"] = request.execution_params
        if request.is_active is not None:
            updates["is_active"] = request.is_active
        if request.is_default is not None:
            updates["is_default"] = request.is_default

        updated_variant = playbook_store.update_personalized_variant(variant_id, updates)
        return updated_variant
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update variant: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{playbook_code}/variants/{variant_id}")
async def delete_variant(
    playbook_code: str,
    variant_id: str,
    profile_id: str = Query("default-user")
):
    """Delete a personalized variant"""
    try:
        # Verify ownership
        variant = playbook_store.get_personalized_variant(variant_id)
        if not variant:
            raise HTTPException(status_code=404, detail="Variant not found")

        if variant["profile_id"] != profile_id or variant["base_playbook_code"] != playbook_code:
            raise HTTPException(status_code=403, detail="Access denied")

        success = playbook_store.delete_personalized_variant(variant_id)
        if not success:
            raise HTTPException(status_code=404, detail="Variant not found")

        return {"status": "deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete variant: {e}")
        raise HTTPException(status_code=500, detail=str(e))
