"""
System Settings API Routes

Endpoints for managing system-level settings.
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

from ...models.system_settings import (
    SystemSetting,
    SystemSettingsUpdate,
    SystemSettingsResponse,
    LLMModelConfig,
    LLMModelSettingsResponse,
    ModelType,
    SettingType
)
from ...services.system_settings_store import SystemSettingsStore

router = APIRouter(prefix="/api/system-settings", tags=["system-settings"])

# Initialize store
settings_store = SystemSettingsStore()

# Obsidian configuration endpoints
@router.get("/obsidian")
async def get_obsidian_config():
    """Get Obsidian configuration"""
    try:
        setting = settings_store.get_setting("obsidian_config")
        if setting:
            import json
            config = json.loads(setting.value) if isinstance(setting.value, str) else setting.value
            return config
        return {
            "vault_paths": [],
            "include_folders": ["Research", "Projects"],
            "exclude_folders": [".obsidian", "Templates"],
            "include_tags": ["research", "paper", "project"],
            "enabled": False
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get Obsidian config: {str(e)}")


@router.put("/obsidian")
async def update_obsidian_config(config: Dict[str, Any]):
    """Update Obsidian configuration"""
    try:
        import json
        settings_store.set_setting(
            key="obsidian_config",
            value=json.dumps(config),
            value_type=SettingType.JSON,
            category="tools",
            description="Obsidian vault configuration"
        )
        return {"success": True, "message": "Obsidian configuration saved"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save Obsidian config: {str(e)}")


@router.post("/obsidian/test")
async def test_obsidian_config(config: Dict[str, Any]):
    """Test Obsidian vault configuration"""
    try:
        from pathlib import Path
        vault_paths = config.get("vault_paths", [])
        valid_vaults = []

        for vault_path in vault_paths:
            vault = Path(vault_path).expanduser().resolve()
            is_valid = vault.exists() and vault.is_dir()
            valid_vaults.append({
                "path": str(vault),
                "valid": is_valid,
                "has_obsidian": (vault / ".obsidian").exists() if is_valid else False
            })

        all_valid = all(v["valid"] for v in valid_vaults)
        message = f"Found {len(valid_vaults)} vault(s), {sum(1 for v in valid_vaults if v['valid'])} valid"

        return {
            "valid": all_valid,
            "message": message,
            "vaults": valid_vaults
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to test Obsidian config: {str(e)}")


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


@router.get("/llm-models", response_model=LLMModelSettingsResponse)
async def get_llm_model_settings():
    """Get LLM model configurations (chat and embedding models)"""
    try:
        chat_setting = settings_store.get_setting("chat_model")
        embedding_setting = settings_store.get_setting("embedding_model")

        chat_model = None
        if chat_setting:
            chat_model = LLMModelConfig(
                model_name=str(chat_setting.value),
                provider=chat_setting.metadata.get("provider", "openai"),
                model_type=ModelType.CHAT,
                api_key_setting_key=chat_setting.metadata.get("api_key_setting_key"),
                metadata=chat_setting.metadata
            )

        embedding_model = None
        if embedding_setting:
            embedding_model = LLMModelConfig(
                model_name=str(embedding_setting.value),
                provider=embedding_setting.metadata.get("provider", "openai"),
                model_type=ModelType.EMBEDDING,
                api_key_setting_key=embedding_setting.metadata.get("api_key_setting_key"),
                metadata=embedding_setting.metadata
            )

        # Available models (2025 latest, with older models for downgrade)
        available_chat_models = [
            {
                "model_name": "gpt-5.1-pro",
                "provider": "openai",
                "description": "OpenAI GPT-5.1 Pro (latest, Nov 2025) - Enhanced for writing, data science, business",
                "is_latest": True,
                "is_recommended": True
            },
            {
                "model_name": "gpt-5.1",
                "provider": "openai",
                "description": "OpenAI GPT-5.1 (latest, Nov 2025) - Latest general-purpose model",
                "is_latest": True
            },
            {
                "model_name": "gpt-4o",
                "provider": "openai",
                "description": "OpenAI GPT-4o (updated Mar 2025) - High quality, deprecated Feb 2026",
                "is_deprecated": True,
                "deprecation_date": "2026-02-16"
            },
            {
                "model_name": "gpt-4o-mini",
                "provider": "openai",
                "description": "OpenAI GPT-4o Mini - Cost-effective, 128K context"
            },
            {
                "model_name": "claude-opus-4.5",
                "provider": "anthropic",
                "description": "Anthropic Claude Opus 4.5 (latest) - Most powerful, enhanced coding & automation",
                "is_latest": True
            },
            {
                "model_name": "claude-haiku-4.5",
                "provider": "anthropic",
                "description": "Anthropic Claude Haiku 4.5 (latest, Oct 2025) - Fastest, most cost-efficient",
                "is_latest": True
            },
            {
                "model_name": "claude-sonnet-4.5",
                "provider": "anthropic",
                "description": "Anthropic Claude Sonnet 4.5 (latest) - Balanced performance"
            },
            {
                "model_name": "claude-3.5-sonnet",
                "provider": "anthropic",
                "description": "Anthropic Claude 3.5 Sonnet (deprecated Oct 2025)",
                "is_deprecated": True
            },
            {
                "model_name": "claude-3-haiku",
                "provider": "anthropic",
                "description": "Anthropic Claude 3 Haiku (legacy)"
            }
        ]

        available_embedding_models = [
            {
                "model_name": "text-embedding-3-large",
                "provider": "openai",
                "description": "OpenAI text-embedding-3-large (latest) - 3072 dimensions, best performance",
                "is_latest": True,
                "is_recommended": True,
                "dimensions": 3072
            },
            {
                "model_name": "text-embedding-3-small",
                "provider": "openai",
                "description": "OpenAI text-embedding-3-small - 1536 dimensions, cost-effective",
                "dimensions": 1536
            },
            {
                "model_name": "text-embedding-ada-002",
                "provider": "openai",
                "description": "OpenAI text-embedding-ada-002 (legacy) - 1536 dimensions",
                "is_legacy": True,
                "dimensions": 1536
            }
        ]

        return LLMModelSettingsResponse(
            chat_model=chat_model,
            embedding_model=embedding_model,
            available_chat_models=available_chat_models,
            available_embedding_models=available_embedding_models
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get LLM model settings: {str(e)}")


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


# ============================================
# Google OAuth Configuration Endpoints
# IMPORTANT: These must be defined BEFORE /{key} route to avoid route conflicts
# ============================================

@router.get("/google-oauth", response_model=Dict[str, Any])
async def get_google_oauth_config():
    """Get Google OAuth configuration"""
    try:
        client_id_setting = settings_store.get_setting("google_oauth_client_id")
        client_secret_setting = settings_store.get_setting("google_oauth_client_secret")
        redirect_uri_setting = settings_store.get_setting("google_oauth_redirect_uri")
        backend_url_setting = settings_store.get_setting("backend_url")

        # Mask sensitive values
        client_secret_value = "***" if client_secret_setting and client_secret_setting.value else ""

        return {
            "client_id": str(client_id_setting.value) if client_id_setting and client_id_setting.value else "",
            "client_secret": client_secret_value,
            "redirect_uri": str(redirect_uri_setting.value) if redirect_uri_setting and redirect_uri_setting.value else "",
            "backend_url": str(backend_url_setting.value) if backend_url_setting and backend_url_setting.value else "",
            "is_configured": bool(
                client_id_setting and client_id_setting.value and
                client_secret_setting and client_secret_setting.value
            )
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get Google OAuth config: {str(e)}")


class GoogleOAuthConfigUpdate(BaseModel):
    """Google OAuth configuration update request"""
    client_id: Optional[str] = Field(None, description="Google OAuth Client ID")
    client_secret: Optional[str] = Field(None, description="Google OAuth Client Secret")
    redirect_uri: Optional[str] = Field(None, description="OAuth Redirect URI (optional, auto-generated if not provided)")
    backend_url: Optional[str] = Field(None, description="Backend URL for OAuth callback construction")


@router.put("/google-oauth", response_model=Dict[str, Any])
async def update_google_oauth_config(request: GoogleOAuthConfigUpdate):
    """Update Google OAuth configuration"""
    try:
        from ...models.system_settings import SystemSetting, SettingType

        updated_settings = {}

        if request.client_id is not None:
            setting = SystemSetting(
                key="google_oauth_client_id",
                value=request.client_id,
                value_type=SettingType.STRING,
                category="oauth",
                description="Google OAuth 2.0 Client ID for Google Drive integration",
                is_sensitive=False,
                is_user_editable=True
            )
            settings_store.save_setting(setting)
            updated_settings["client_id"] = request.client_id

        if request.client_secret is not None:
            setting = SystemSetting(
                key="google_oauth_client_secret",
                value=request.client_secret,
                value_type=SettingType.STRING,
                category="oauth",
                description="Google OAuth 2.0 Client Secret for Google Drive integration",
                is_sensitive=True,
                is_user_editable=True
            )
            settings_store.save_setting(setting)
            updated_settings["client_secret"] = "***"

        if request.redirect_uri is not None:
            setting = SystemSetting(
                key="google_oauth_redirect_uri",
                value=request.redirect_uri,
                value_type=SettingType.STRING,
                category="oauth",
                description="Google OAuth Redirect URI",
                is_sensitive=False,
                is_user_editable=True
            )
            settings_store.save_setting(setting)
            updated_settings["redirect_uri"] = request.redirect_uri

        if request.backend_url is not None:
            setting = SystemSetting(
                key="backend_url",
                value=request.backend_url,
                value_type=SettingType.STRING,
                category="oauth",
                description="Backend URL for OAuth callback construction",
                is_sensitive=False,
                is_user_editable=True
            )
            settings_store.save_setting(setting)
            updated_settings["backend_url"] = request.backend_url

        logger.info("Google OAuth configuration updated, will reload on next OAuth request")

        return {
            "success": True,
            "message": "Google OAuth configuration updated",
            "updated_settings": updated_settings
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update Google OAuth config: {str(e)}")


@router.post("/google-oauth/test", response_model=Dict[str, Any])
async def test_google_oauth_config(
    client_id: Optional[str] = Query(None, description="Client ID to test (uses current setting if not provided)"),
    client_secret: Optional[str] = Query(None, description="Client Secret to test (uses current setting if not provided)"),
):
    """Test Google OAuth configuration by validating credentials format"""
    try:
        if not client_id:
            client_id_setting = settings_store.get_setting("google_oauth_client_id")
            client_id = str(client_id_setting.value) if client_id_setting and client_id_setting.value else None

        if not client_secret:
            client_secret_setting = settings_store.get_setting("google_oauth_client_secret")
            client_secret = str(client_secret_setting.value) if client_secret_setting and client_secret_setting.value else None

        errors = []
        warnings = []

        if not client_id:
            errors.append("Client ID is required")
        elif not client_id.endswith(".apps.googleusercontent.com"):
            warnings.append("Client ID should end with .apps.googleusercontent.com")

        if not client_secret:
            errors.append("Client Secret is required")
        elif len(client_secret) < 10:
            warnings.append("Client Secret seems too short")

        if errors:
            return {
                "success": False,
                "valid": False,
                "errors": errors,
                "warnings": warnings,
                "message": "Configuration validation failed"
            }

        return {
            "success": True,
            "valid": True,
            "warnings": warnings,
            "message": "Configuration format is valid. Note: This only validates format, not actual credentials.",
            "tested_at": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to test Google OAuth config: {str(e)}")


# ============================================
# Generic Setting Endpoints (catch-all routes - must be LAST)
# ============================================

@router.get("/{key}", response_model=SystemSetting)
async def get_setting(key: str):
    """
    Get a specific setting by key

    Note: This is a catch-all route. Specific routes like /google-oauth
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
            from ..models.system_settings import SettingType

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


@router.put("/llm-models/chat", response_model=LLMModelConfig)
async def update_chat_model(
    model_name: str,
    provider: str = Query("openai", description="Model provider"),
    api_key_setting_key: Optional[str] = Query(None, description="API key setting key")
):
    """Update chat/conversation model configuration"""
    try:
        metadata = {
            "provider": provider,
            "model_type": "chat"
        }
        if api_key_setting_key:
            metadata["api_key_setting_key"] = api_key_setting_key

        setting = SystemSetting(
            key="chat_model",
            value=model_name,
            value_type=SettingType.STRING,
            category="llm",
            description="Model for chat/conversation inference",
            is_sensitive=False,
            is_user_editable=True,
            metadata=metadata
        )

        updated = settings_store.save_setting(setting)

        return LLMModelConfig(
            model_name=str(updated.value),
            provider=updated.metadata.get("provider", "openai"),
            model_type=ModelType.CHAT,
            api_key_setting_key=updated.metadata.get("api_key_setting_key"),
            metadata=updated.metadata
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update chat model: {str(e)}")


@router.put("/llm-models/embedding", response_model=LLMModelConfig)
async def update_embedding_model(
    model_name: str,
    provider: str = Query("openai", description="Model provider"),
    api_key_setting_key: Optional[str] = Query(None, description="API key setting key")
):
    """Update embedding model configuration"""
    try:
        metadata = {
            "provider": provider,
            "model_type": "embedding"
        }
        if api_key_setting_key:
            metadata["api_key_setting_key"] = api_key_setting_key

        setting = SystemSetting(
            key="embedding_model",
            value=model_name,
            value_type=SettingType.STRING,
            category="llm",
            description="Model for embeddings/vectorization",
            is_sensitive=False,
            is_user_editable=True,
            metadata=metadata
        )

        updated = settings_store.save_setting(setting)

        return LLMModelConfig(
            model_name=str(updated.value),
            provider=updated.metadata.get("provider", "openai"),
            model_type=ModelType.EMBEDDING,
            api_key_setting_key=updated.metadata.get("api_key_setting_key"),
            metadata=updated.metadata
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update embedding model: {str(e)}")


@router.post("/llm-models/test-chat", response_model=Dict[str, Any])
async def test_chat_model_connection(
    model_name: Optional[str] = Query(None, description="Model name to test (uses current setting if not provided)")
):
    """Test chat model connection"""
    try:
        import os
        from ...services.config_store import ConfigStore

        # Get model configuration
        if not model_name:
            chat_setting = settings_store.get_setting("chat_model")
            if not chat_setting:
                raise HTTPException(status_code=400, detail="No chat model configured")
            model_name = str(chat_setting.value)
            provider = chat_setting.metadata.get("provider", "openai")
        else:
            # Determine provider from model name
            if model_name.startswith("gpt") or model_name.startswith("text-"):
                provider = "openai"
            elif model_name.startswith("claude"):
                provider = "anthropic"
            else:
                provider = "openai"

        # Get API key
        config_store = ConfigStore()
        config = config_store.get_or_create_config("default-user")

        if provider == "openai":
            api_key = config.agent_backend.openai_api_key or os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise HTTPException(status_code=400, detail="OpenAI API key not configured")
        elif provider == "anthropic":
            api_key = config.agent_backend.anthropic_api_key or os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise HTTPException(status_code=400, detail="Anthropic API key not configured")
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")

        # Test connection with a simple API call
        try:
            if provider == "openai":
                import openai
                client = openai.OpenAI(api_key=api_key)
                # For newer models (gpt-5.1+), don't use max_tokens/max_completion_tokens
                # as the SDK version may not support max_completion_tokens yet
                # Just use a minimal test call
                create_params = {
                    "model": model_name,
                    "messages": [{"role": "user", "content": "Hi"}]
                }
                # Only add max_tokens for older models that require it
                # For gpt-5.x, skip the parameter to avoid SDK compatibility issues
                if not (model_name.startswith("gpt-5") or "gpt-5" in model_name):
                    create_params["max_tokens"] = 10

                response = client.chat.completions.create(**create_params)
                success = bool(response.choices and len(response.choices) > 0)
                message = "Connection successful" if success else "Connection failed"
            elif provider == "anthropic":
                import anthropic
                client = anthropic.Anthropic(api_key=api_key)
                response = client.messages.create(
                    model=model_name,
                    max_tokens=10,
                    messages=[{"role": "user", "content": "Hello"}]
                )
                success = bool(response.content)
                message = "Connection successful" if success else "Connection failed"
            else:
                raise ValueError(f"Unsupported provider: {provider}")

            return {
                "success": success,
                "model_name": model_name,
                "provider": provider,
                "message": message,
                "tested_at": datetime.utcnow().isoformat()
            }
        except Exception as api_error:
            return {
                "success": False,
                "model_name": model_name,
                "provider": provider,
                "message": f"Connection failed: {str(api_error)}",
                "error": str(api_error),
                "tested_at": datetime.utcnow().isoformat()
            }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to test chat model: {str(e)}")


@router.post("/llm-models/test-embedding", response_model=Dict[str, Any])
async def test_embedding_model_connection(
    model_name: Optional[str] = Query(None, description="Model name to test (uses current setting if not provided)")
):
    """Test embedding model connection"""
    try:
        import os
        from ...services.config_store import ConfigStore

        # Get model configuration
        if not model_name:
            embedding_setting = settings_store.get_setting("embedding_model")
            if not embedding_setting:
                raise HTTPException(status_code=400, detail="No embedding model configured")
            model_name = str(embedding_setting.value)
            provider = embedding_setting.metadata.get("provider", "openai")
        else:
            # Determine provider from model name
            if model_name.startswith("text-embedding"):
                provider = "openai"
            else:
                provider = "openai"

        # Get API key
        config_store = ConfigStore()
        config = config_store.get_or_create_config("default-user")

        api_key = config.agent_backend.openai_api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise HTTPException(status_code=400, detail="OpenAI API key not configured")

        # Test connection with a simple embedding call
        try:
            import openai
            client = openai.OpenAI(api_key=api_key)
            response = client.embeddings.create(
                model=model_name,
                input="test"
            )
            success = bool(response.data and len(response.data) > 0 and response.data[0].embedding)
            message = f"Connection successful (dimensions: {len(response.data[0].embedding)})" if success else "Connection failed"

            return {
                "success": success,
                "model_name": model_name,
                "provider": provider,
                "message": message,
                "dimensions": len(response.data[0].embedding) if success else None,
                "tested_at": datetime.utcnow().isoformat()
            }
        except Exception as api_error:
            return {
                "success": False,
                "model_name": model_name,
                "provider": provider,
                "message": f"Connection failed: {str(api_error)}",
                "error": str(api_error),
                "tested_at": datetime.utcnow().isoformat()
            }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to test embedding model: {str(e)}")


# Google OAuth endpoints moved above to fix route conflict
