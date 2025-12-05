"""
General system settings endpoints
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any, List, Optional

from .shared import settings_store
from backend.app.models.system_settings import (
    SystemSetting,
    SystemSettingsUpdate,
    SystemSettingsResponse,
    SettingType
)

router = APIRouter()


@router.get("/", response_model=SystemSettingsResponse)
async def get_all_settings(
    include_sensitive: bool = Query(False, description="Include sensitive settings (masked)")
):
    """Get all system settings"""
    try:
        settings = settings_store.get_all_settings(include_sensitive=include_sensitive)
        categories = settings_store.get_categories()

        return SystemSettingsResponse(
            settings=settings,
            categories=categories
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get settings: {str(e)}")


@router.get("/categories/list", response_model=List[str])
async def list_categories():
    """Get list of all setting categories"""
    try:
        return settings_store.get_categories()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list categories: {str(e)}")


@router.get("/category/{category}", response_model=List[SystemSetting])
async def get_settings_by_category(category: str):
    """Get all settings in a category"""
    try:
        settings = settings_store.get_settings_by_category(category)

        # Mask sensitive values
        for setting in settings:
            if setting.is_sensitive:
                setting.value = "***"

        return settings
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get settings: {str(e)}")


@router.get("/{key}", response_model=SystemSetting)
async def get_setting(key: str):
    """
    Get a specific setting by key

    This is a catch-all route. Specific routes like /google-oauth
    should be defined BEFORE this route to avoid conflicts.
    """
    try:
        setting = settings_store.get_setting(key)
        if not setting:
            raise HTTPException(status_code=404, detail=f"Setting not found: {key}")

        # Mask sensitive values
        if setting.is_sensitive:
            setting.value = "***"

        return setting
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get setting: {str(e)}")


@router.put("/", response_model=Dict[str, Any])
async def update_settings(request: SystemSettingsUpdate):
    """Update multiple settings at once"""
    try:
        updated = settings_store.update_settings(request.settings)

        return {
            "success": True,
            "updated_count": len(updated),
            "updated_keys": list(updated.keys()),
            "message": f"Updated {len(updated)} settings"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update settings: {str(e)}")


@router.put("/{key}", response_model=SystemSetting)
async def update_setting(
    key: str,
    value: Any,
    category: Optional[str] = Query(None, description="Setting category"),
    description: Optional[str] = Query(None, description="Setting description")
):
    """Update a single setting"""
    try:
        existing = settings_store.get_setting(key)

        if not existing:
            # Create new setting
            # Infer type from value
            if isinstance(value, bool):
                value_type = SettingType.BOOLEAN
            elif isinstance(value, int):
                value_type = SettingType.INTEGER
            elif isinstance(value, float):
                value_type = SettingType.FLOAT
            elif isinstance(value, (dict, list)):
                value_type = SettingType.JSON
            else:
                value_type = SettingType.STRING

            setting = SystemSetting(
                key=key,
                value=value,
                value_type=value_type,
                category=category or "general",
                description=description
            )
        else:
            # Update existing setting
            setting = SystemSetting(
                key=existing.key,
                value=value,
                value_type=existing.value_type,
                category=category or existing.category,
                description=description or existing.description,
                is_sensitive=existing.is_sensitive,
                is_user_editable=existing.is_user_editable,
                default_value=existing.default_value,
                metadata=existing.metadata
            )

        updated = settings_store.save_setting(setting)

        # Mask sensitive values in response
        if updated.is_sensitive:
            updated.value = "***"

        return updated
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update setting: {str(e)}")


@router.delete("/{key}")
async def delete_setting(key: str):
    """Delete a setting"""
    try:
        deleted = settings_store.delete_setting(key)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Setting not found: {key}")

        return {
            "success": True,
            "message": f"Setting {key} deleted"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete setting: {str(e)}")

