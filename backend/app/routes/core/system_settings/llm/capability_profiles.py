"""
Capability Profile Endpoints

Handles capability profile configuration and workspace overrides.
"""

from fastapi import APIRouter, HTTPException, Body
from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/capability-profiles", response_model=Dict[str, Any])
async def get_capability_profiles():
    """Get capability profile configuration"""
    try:
        from backend.app.services.system_settings_store import SystemSettingsStore

        settings_store = SystemSettingsStore()

        return {
            "capability_profile_mapping": settings_store.get_capability_profile_mapping(),
            "profile_model_mapping": settings_store.get_profile_model_mapping(),
            "custom_model_provider_mapping": settings_store.get_custom_model_provider_mapping(),
        }
    except Exception as e:
        logger.error(f"Failed to get capability profiles: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to get capability profiles: {str(e)}"
        )


@router.put("/capability-profiles", response_model=Dict[str, Any])
async def update_capability_profiles(
    capability_profile_mapping: Optional[Dict[str, str]] = Body(
        None, description="Stage to capability profile mapping"
    ),
    profile_model_mapping: Optional[Dict[str, List[str]]] = Body(
        None, description="Profile to model list mapping"
    ),
    custom_model_provider_mapping: Optional[Dict[str, str]] = Body(
        None, description="Custom model to provider mapping"
    ),
):
    """Update capability profile configuration"""
    try:
        from backend.app.services.system_settings_store import SystemSettingsStore

        settings_store = SystemSettingsStore()

        if capability_profile_mapping is not None:
            settings_store.set_capability_profile_mapping(capability_profile_mapping)
        if profile_model_mapping is not None:
            settings_store.set_profile_model_mapping(profile_model_mapping)
        if custom_model_provider_mapping is not None:
            settings_store.set_custom_model_provider_mapping(
                custom_model_provider_mapping
            )

        return {
            "status": "success",
            "capability_profile_mapping": settings_store.get_capability_profile_mapping(),
            "profile_model_mapping": settings_store.get_profile_model_mapping(),
            "custom_model_provider_mapping": settings_store.get_custom_model_provider_mapping(),
        }
    except Exception as e:
        logger.error(f"Failed to update capability profiles: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to update capability profiles: {str(e)}"
        )


@router.get(
    "/workspaces/{workspace_id}/capability-profile", response_model=Dict[str, Any]
)
async def get_workspace_capability_profile(workspace_id: str):
    """Get workspace capability profile override"""
    try:
        from backend.app.services.mindscape_store import MindscapeStore

        store = MindscapeStore()
        workspace = await store.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")
        return {"capability_profile": workspace.capability_profile}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get workspace capability profile: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get workspace capability profile: {str(e)}",
        )


@router.put(
    "/workspaces/{workspace_id}/capability-profile", response_model=Dict[str, Any]
)
async def update_workspace_capability_profile(
    workspace_id: str,
    capability_profile: Optional[str] = Body(
        None,
        description="Capability profile override (fast/standard/precise/tool_strict/safe_write)",
    ),
):
    """Update workspace capability profile override"""
    try:
        from backend.app.services.mindscape_store import MindscapeStore

        store = MindscapeStore()
        workspace = await store.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

        workspace.capability_profile = capability_profile
        updated = await store.update_workspace(workspace)

        return {"status": "success", "capability_profile": updated.capability_profile}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to update workspace capability profile: {e}", exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update workspace capability profile: {str(e)}",
        )
