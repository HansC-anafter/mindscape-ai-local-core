"""
Hugging Face credential settings endpoints.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Any, Dict, Optional
import logging

from .shared import settings_store
from backend.app.models.system_settings import SystemSetting, SettingType

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/huggingface-auth", response_model=Dict[str, Any])
async def get_huggingface_auth_config():
    """Get Hugging Face access token configuration."""
    try:
        token_setting = settings_store.get_setting("huggingface_api_key")
        token_value = (
            str(token_setting.value).strip()
            if token_setting and token_setting.value is not None
            else ""
        )
        return {
            "api_key_configured": bool(token_value),
            "api_key": "***" if token_value else "",
            "source": "system_settings:huggingface_api_key" if token_value else "none",
            "credential_kind": "access_token",
        }
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get Hugging Face credential config: {exc}",
        )


class HuggingFaceAuthConfigUpdate(BaseModel):
    api_key: Optional[str] = Field(
        default=None,
        description="Hugging Face access token",
    )
    clear: bool = Field(
        default=False,
        description="Clear stored Hugging Face credential",
    )


@router.put("/huggingface-auth", response_model=Dict[str, Any])
async def update_huggingface_auth_config(request: HuggingFaceAuthConfigUpdate):
    """Create, update, or clear Hugging Face access token configuration."""
    try:
        token_value = ""
        if not request.clear and request.api_key is not None:
            token_value = request.api_key.strip()

        setting = SystemSetting(
            key="huggingface_api_key",
            value=token_value,
            value_type=SettingType.STRING,
            category="models",
            description="Hugging Face access token for model pull and pack-owned weight sync",
            is_sensitive=True,
            is_user_editable=True,
        )
        settings_store.save_setting(setting)

        return {
            "success": True,
            "message": (
                "Hugging Face 存取憑證已清除"
                if request.clear or not token_value
                else "Hugging Face 存取憑證已儲存"
            ),
            "api_key_configured": bool(token_value),
        }
    except Exception as exc:
        logger.error("Failed to update Hugging Face auth config: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update Hugging Face credential config: {exc}",
        )
