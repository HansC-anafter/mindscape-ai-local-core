"""
System Settings API Routes

Endpoints for managing system-level settings.
"""

from fastapi import APIRouter, HTTPException, Query, Body, Request
import json
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

router = APIRouter(prefix="/api/v1/system-settings", tags=["system-settings"])

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
        # Note: These are default models, will be migrated to database
        DEFAULT_CHAT_MODELS = [
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

        DEFAULT_EMBEDDING_MODELS = [
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

        # Use default models for now (will be replaced with database models later)
        available_chat_models = DEFAULT_CHAT_MODELS
        available_embedding_models = DEFAULT_EMBEDDING_MODELS

        return LLMModelSettingsResponse(
            chat_model=chat_model,
            embedding_model=embedding_model,
            available_chat_models=available_chat_models,
            available_embedding_models=available_embedding_models
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get LLM model settings: {str(e)}")


@router.get("/models", response_model=List[Dict[str, Any]])
async def get_models(
    model_type: Optional[str] = Query(None, description="Filter by model type ('chat' or 'embedding')"),
    enabled: Optional[bool] = Query(None, description="Filter by enabled status"),
    provider: Optional[str] = Query(None, description="Filter by provider name")
):
    """
    Get all models with optional filters

    Returns:
        List of model configurations
    """
    try:
        from backend.app.services.model_config_store import ModelConfigStore
        from backend.app.models.model_provider import ModelType

        store = ModelConfigStore()

        models = store.get_all_models()
        if not models:
            store.initialize_default_models()
            models = store.get_all_models()

        model_type_enum = None
        if model_type:
            model_type_enum = ModelType(model_type)

        filtered_models = store.get_all_models(
            model_type=model_type_enum,
            enabled=enabled,
            provider=provider
        )

        return [
            {
                "id": m.id,
                "model_name": m.model_name,
                "provider": m.provider_name,
                "model_type": m.model_type.value,
                "display_name": m.display_name,
                "description": m.description,
                "enabled": m.enabled,
                "is_latest": m.is_latest,
                "is_recommended": m.is_recommended,
                "is_deprecated": m.is_deprecated,
                "deprecation_date": m.deprecation_date,
                "dimensions": m.dimensions,
                "context_window": m.context_window,
                "icon": m.icon,
            }
            for m in filtered_models
        ]
    except Exception as e:
        logger.error(f"Failed to get models: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get models: {str(e)}")


@router.put("/models/{model_id}/enable", response_model=Dict[str, Any])
async def toggle_model_enabled(
    model_id: int,
    request: Dict[str, bool] = Body(...)
):
    """
    Enable or disable a model

    Args:
        model_id: Model ID
        request: Request body with 'enabled' boolean

    Returns:
        Updated model configuration
    """
    try:
        from backend.app.services.model_config_store import ModelConfigStore

        store = ModelConfigStore()
        enabled = request.get("enabled", False)

        model = store.toggle_model_enabled(model_id, enabled)

        if not model:
            raise HTTPException(status_code=404, detail=f"Model with id {model_id} not found")

        return {
            "id": model.id,
            "model_name": model.model_name,
            "provider": model.provider_name,
            "model_type": model.model_type.value,
            "display_name": model.display_name,
            "description": model.description,
            "enabled": model.enabled,
            "is_latest": model.is_latest,
            "is_recommended": model.is_recommended,
            "is_deprecated": model.is_deprecated,
            "deprecation_date": model.deprecation_date,
            "dimensions": model.dimensions,
            "context_window": model.context_window,
            "icon": model.icon,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to toggle model enabled: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to toggle model enabled: {str(e)}")


@router.get("/models/{model_id}/config", response_model=Dict[str, Any])
async def get_model_config(model_id: int):
    """
    Get model configuration card data

    Args:
        model_id: Model ID

    Returns:
        Model configuration card data
    """
    try:
        from backend.app.services.model_config_store import ModelConfigStore
        from backend.app.services.system_settings_store import SystemSettingsStore

        model_store = ModelConfigStore()
        settings_store = SystemSettingsStore()

        model = model_store.get_model_by_id(model_id)
        if not model:
            raise HTTPException(status_code=404, detail=f"Model with id {model_id} not found")

        api_key_setting_key = f"{model.provider_name}_api_key"
        api_key_setting = settings_store.get_setting(api_key_setting_key)
        api_key_configured = api_key_setting is not None and bool(api_key_setting.value)

        base_url = None
        if model.provider_name == "ollama":
            base_url = "http://localhost:11434"

        return {
            "model": {
                "id": model.id,
                "model_name": model.model_name,
                "provider": model.provider_name,
                "model_type": model.model_type.value,
                "display_name": model.display_name,
                "description": model.description,
                "enabled": model.enabled,
                "is_latest": model.is_latest,
                "is_recommended": model.is_recommended,
                "is_deprecated": model.is_deprecated,
                "deprecation_date": model.deprecation_date,
                "dimensions": model.dimensions,
                "context_window": model.context_window,
                "icon": model.icon,
            },
            "api_key_configured": api_key_configured,
            "base_url": base_url,
            "quota_info": None,
        }
    except Exception as e:
        logger.error(f"Failed to get model config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get model config: {str(e)}")


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

        request_dict = request.dict(exclude_none=True)
        logger.info(f"Received Google OAuth update request with {len(request_dict)} fields: {list(request_dict.keys())}")
        for key, value in request_dict.items():
            if key == "client_secret":
                logger.info(f"  {key}: {'*** (masked, length: ' + str(len(value)) + ')' if value else 'empty'}")
            else:
                logger.info(f"  {key}: {str(value)[:50] + '...' if value and len(str(value)) > 50 else (value or 'empty')}")

        updated_settings = {}

        if request.client_id is not None:
            client_id_value = request.client_id.strip() if isinstance(request.client_id, str) else str(request.client_id)
            if client_id_value:
                setting = SystemSetting(
                    key="google_oauth_client_id",
                    value=client_id_value,
                    value_type=SettingType.STRING,
                    category="oauth",
                    description="Google OAuth 2.0 Client ID for Google Drive integration",
                    is_sensitive=False,
                    is_user_editable=True
                )
                logger.info(f"Attempting to save google_oauth_client_id: {client_id_value[:30]}... (length: {len(client_id_value)})")
                settings_store.save_setting(setting)
                updated_settings["client_id"] = client_id_value
                logger.info(f"Save operation completed for google_oauth_client_id")

                # Verify save immediately after commit
                verify = settings_store.get_setting("google_oauth_client_id")
                if verify:
                    verify_value_str = str(verify.value) if verify.value else ""
                    verify_length = len(verify_value_str)
                    logger.info(f"Verification read - key exists: True, value length: {verify_length}, value preview: {verify_value_str[:30] if verify_value_str else '(empty)'}...")
                    if verify_value_str and verify_length > 0:
                        if verify_value_str == client_id_value:
                            logger.info(f"✓ Verified google_oauth_client_id saved successfully (length: {verify_length})")
                        else:
                            logger.error(f"✗ Verification failed - value mismatch! Expected: {client_id_value[:30]}..., Got: {verify_value_str[:30]}...")
                    else:
                        logger.error(f"✗ WARNING: google_oauth_client_id verification failed - value is empty after save! (length: {verify_length})")
                else:
                    logger.error("✗ WARNING: google_oauth_client_id verification failed - setting not found after save!")

        if request.client_secret is not None:
            client_secret_value = request.client_secret.strip() if isinstance(request.client_secret, str) else str(request.client_secret)
            if client_secret_value:
                setting = SystemSetting(
                    key="google_oauth_client_secret",
                    value=client_secret_value,
                    value_type=SettingType.STRING,
                    category="oauth",
                    description="Google OAuth 2.0 Client Secret for Google Drive integration",
                    is_sensitive=True,
                    is_user_editable=True
                )
                logger.info(f"Attempting to save google_oauth_client_secret (length: {len(client_secret_value)})")
                settings_store.save_setting(setting)
                updated_settings["client_secret"] = "***"
                logger.info(f"Save operation completed for google_oauth_client_secret")

                # Verify save
                verify = settings_store.get_setting("google_oauth_client_secret")
                if verify:
                    verify_value_str = str(verify.value) if verify.value else ""
                    verify_length = len(verify_value_str)
                    logger.info(f"Verification read - key exists: True, value length: {verify_length}")
                    if verify_value_str and verify_length > 0:
                        if verify_value_str == client_secret_value:
                            logger.info(f"✓ Verified google_oauth_client_secret saved successfully (length: {verify_length})")
                        else:
                            logger.error(f"✗ Verification failed - value mismatch for client_secret!")
                    else:
                        logger.error(f"✗ WARNING: google_oauth_client_secret verification failed - value is empty after save! (length: {verify_length})")
                else:
                    logger.error("✗ WARNING: google_oauth_client_secret verification failed - setting not found after save!")
            else:
                logger.warning("Received empty client_secret, skipping save")

        if request.redirect_uri is not None:
            redirect_uri_value = request.redirect_uri.strip() if isinstance(request.redirect_uri, str) and request.redirect_uri.strip() else None
            if redirect_uri_value:
                logger.info(f"Attempting to save google_oauth_redirect_uri: {redirect_uri_value}")
                setting = SystemSetting(
                    key="google_oauth_redirect_uri",
                    value=redirect_uri_value,
                    value_type=SettingType.STRING,
                    category="oauth",
                    description="Google OAuth Redirect URI",
                    is_sensitive=False,
                    is_user_editable=True
                )
                settings_store.save_setting(setting)
                updated_settings["redirect_uri"] = redirect_uri_value
                logger.info(f"Save operation completed for google_oauth_redirect_uri")

                # Verify save
                verify = settings_store.get_setting("google_oauth_redirect_uri")
                if verify:
                    verify_value_str = str(verify.value) if verify.value else ""
                    verify_length = len(verify_value_str)
                    if verify_value_str and verify_length > 0:
                        logger.info(f"✓ Verified google_oauth_redirect_uri saved successfully (length: {verify_length})")
                    else:
                        logger.error(f"✗ WARNING: google_oauth_redirect_uri verification failed - value is empty after save!")
                else:
                    logger.error("✗ WARNING: google_oauth_redirect_uri verification failed - setting not found after save!")
            else:
                logger.warning("Received empty redirect_uri, skipping save")

        if request.backend_url is not None:
            backend_url_value = request.backend_url.strip() if isinstance(request.backend_url, str) else str(request.backend_url)
            if backend_url_value:
                setting = SystemSetting(
                    key="backend_url",
                    value=backend_url_value,
                    value_type=SettingType.STRING,
                    category="oauth",
                    description="Backend URL for OAuth callback construction",
                    is_sensitive=False,
                    is_user_editable=True
                )
                logger.info(f"Attempting to save backend_url: {backend_url_value} (length: {len(backend_url_value)})")
                settings_store.save_setting(setting)
                updated_settings["backend_url"] = backend_url_value
                logger.info(f"Save operation completed for backend_url")

                # Verify save
                verify = settings_store.get_setting("backend_url")
                if verify:
                    verify_value_str = str(verify.value) if verify.value else ""
                    verify_length = len(verify_value_str)
                    logger.info(f"Verification read - key exists: True, value length: {verify_length}, value: {verify_value_str}")
                    if verify_value_str and verify_length > 0:
                        if verify_value_str == backend_url_value:
                            logger.info(f"✓ Verified backend_url saved successfully (length: {verify_length})")
                        else:
                            logger.error(f"✗ Verification failed - value mismatch! Expected: {backend_url_value}, Got: {verify_value_str}")
                    else:
                        logger.error(f"✗ WARNING: backend_url verification failed - value is empty after save! (length: {verify_length})")
                else:
                    logger.error("✗ WARNING: backend_url verification failed - setting not found after save!")

        logger.info(f"Google OAuth configuration update completed. Updated fields: {list(updated_settings.keys())}")

        if not updated_settings:
            logger.warning("No fields were updated - all values may be empty or None")

        return {
            "success": True,
            "message": "Google OAuth configuration updated",
            "updated_settings": updated_settings
        }
    except Exception as e:
        logger.error(f"Failed to update Google OAuth config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update Google OAuth config: {str(e)}")


class GoogleOAuthTestRequest(BaseModel):
    """Google OAuth test request body"""
    client_id: Optional[str] = Field(default=None, description="Client ID to test")
    client_secret: Optional[str] = Field(default=None, description="Client Secret to test")


@router.post("/google-oauth/test", response_model=Dict[str, Any])
async def test_google_oauth_config(
    request: Request,
):
    """Test Google OAuth configuration by validating credentials format"""
    try:
        # Read JSON body directly from request
        try:
            request_body = await request.json()
        except Exception as json_error:
            logger.error(f"Failed to parse JSON body: {json_error}")
            logger.info(f"Request Content-Type: {request.headers.get('content-type', 'not set')}")
            raise HTTPException(status_code=400, detail=f"Invalid JSON in request body: {str(json_error)}")

        # Log request headers and body
        content_type = request.headers.get('content-type', 'not set')
        logger.info(f"Received test request - Content-Type: {content_type}")
        logger.info(f"Raw request body type: {type(request_body)}")
        logger.info(f"Raw request body keys: {list(request_body.keys()) if isinstance(request_body, dict) else 'not a dict'}")

        # Extract values from request body
        test_client_id = None
        test_client_secret = None

        # Get client_id from request body
        if isinstance(request_body, dict) and "client_id" in request_body:
            client_id_value = request_body.get("client_id")
            logger.info(f"Raw client_id from request: type={type(client_id_value)}, value={'None' if client_id_value is None else ('empty' if client_id_value == '' else client_id_value[:30] + '...')}")
            if client_id_value is not None:
                if isinstance(client_id_value, str):
                    client_id_trimmed = client_id_value.strip()
                    if client_id_trimmed:
                        test_client_id = client_id_trimmed
                        logger.info(f"Extracted client_id from request body: {test_client_id[:30]}... (length: {len(test_client_id)})")
                else:
                    test_client_id = str(client_id_value).strip()
                    logger.info(f"Extracted client_id from request body (converted to string): {test_client_id[:30]}...")

        # Get client_secret from request body
        if isinstance(request_body, dict) and "client_secret" in request_body:
            client_secret_value = request_body.get("client_secret")
            logger.info(f"Raw client_secret from request: type={type(client_secret_value)}, present={client_secret_value is not None and client_secret_value != ''}")
            if client_secret_value is not None:
                if isinstance(client_secret_value, str):
                    client_secret_trimmed = client_secret_value.strip()
                    if client_secret_trimmed:
                        test_client_secret = client_secret_trimmed
                        logger.info(f"Extracted client_secret from request body (masked, length: {len(test_client_secret)})")
                else:
                    test_client_secret = str(client_secret_value).strip()
                    logger.info(f"Extracted client_secret from request body (converted to string, masked)")

        logger.info(f"After processing - client_id: {'present (length: ' + str(len(test_client_id)) + ')' if test_client_id else 'missing'}, client_secret: {'present' if test_client_secret else 'missing'}")

        # Fall back to database if not provided
        if not test_client_id:
            client_id_setting = settings_store.get_setting("google_oauth_client_id")
            test_client_id = str(client_id_setting.value) if client_id_setting and client_id_setting.value else None
            logger.info(f"Loaded client_id from database: {'present' if test_client_id else 'missing'}")

        if not test_client_secret:
            client_secret_setting = settings_store.get_setting("google_oauth_client_secret")
            test_client_secret = str(client_secret_setting.value) if client_secret_setting and client_secret_setting.value else None
            logger.info(f"Loaded client_secret from database: {'present' if test_client_secret else 'missing'}")

        errors = []
        warnings = []

        logger.info(f"Validating - test_client_id: {'present' if test_client_id else 'None'}, test_client_secret: {'present' if test_client_secret else 'None'}")

        if not test_client_id:
            errors.append("Client ID is required")
        else:
            test_client_id = test_client_id.strip()
            if not test_client_id:
                errors.append("Client ID cannot be empty")
            elif not test_client_id.endswith(".apps.googleusercontent.com"):
                warnings.append("Client ID should end with .apps.googleusercontent.com")

        if not test_client_secret:
            errors.append("Client Secret is required")
        else:
            test_client_secret = test_client_secret.strip()
            if not test_client_secret:
                errors.append("Client Secret cannot be empty")
            elif len(test_client_secret) < 10:
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
        logger.error(f"Failed to test Google OAuth config: {e}", exc_info=True)
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


# ============================================
# Embedding Migration Endpoints
# ============================================

@router.post("/embedding-migrations", response_model=Dict[str, Any])
async def create_embedding_migration(
    request: Dict[str, Any]
):
    """Create a new embedding migration task"""
    try:
        from ...services.embedding_migration_service import EmbeddingMigrationService
        from ...models.embedding_migration import EmbeddingMigrationCreate, MigrationStrategy

        service = EmbeddingMigrationService()
        user_id = request.get("user_id", "default-user")

        create_request = EmbeddingMigrationCreate(
            source_model=request["source_model"],
            target_model=request["target_model"],
            source_provider=request.get("source_provider", "openai"),
            target_provider=request.get("target_provider", "openai"),
            workspace_id=request.get("workspace_id"),
            intent_id=request.get("intent_id"),
            scope=request.get("scope"),
            strategy=MigrationStrategy(request.get("strategy", "replace")),
            metadata=request.get("metadata", {})
        )

        migration = await service.create_migration_task(create_request, user_id)

        return {
            "success": True,
            "migration": {
                "id": str(migration.id),
                "source_model": migration.source_model,
                "target_model": migration.target_model,
                "total_count": migration.total_count,
                "status": migration.status,
                "created_at": migration.created_at.isoformat()
            },
            "message": f"Migration task created with {migration.total_count} embeddings to migrate"
        }
    except Exception as e:
        logger.error(f"Failed to create migration task: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create migration task: {str(e)}")


@router.get("/embedding-migrations", response_model=Dict[str, Any])
async def list_embedding_migrations(
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(100, description="Maximum number of results"),
    offset: int = Query(0, description="Offset for pagination")
):
    """List all embedding migration tasks"""
    try:
        from ...services.embedding_migration_service import EmbeddingMigrationService
        from ...models.embedding_migration import MigrationStatus

        service = EmbeddingMigrationService()
        migration_status = MigrationStatus(status) if status else None

        migrations = await service.list_migrations(
            user_id=user_id,
            status=migration_status,
            limit=limit,
            offset=offset
        )

        return {
            "success": True,
            "migrations": [
                {
                    "id": str(m.id),
                    "source_model": m.source_model,
                    "target_model": m.target_model,
                    "total_count": m.total_count,
                    "processed_count": m.processed_count,
                    "failed_count": m.failed_count,
                    "status": m.status,
                    "progress_percentage": (m.processed_count / m.total_count * 100) if m.total_count > 0 else 0,
                    "created_at": m.created_at.isoformat(),
                    "started_at": m.started_at.isoformat() if m.started_at else None,
                    "completed_at": m.completed_at.isoformat() if m.completed_at else None
                }
                for m in migrations
            ],
            "total": len(migrations)
        }
    except Exception as e:
        logger.error(f"Failed to list migration tasks: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list migration tasks: {str(e)}")


@router.get("/embedding-migrations/{migration_id}", response_model=Dict[str, Any])
async def get_embedding_migration(migration_id: str):
    """Get migration task status"""
    try:
        from ...services.embedding_migration_service import EmbeddingMigrationService
        from uuid import UUID

        service = EmbeddingMigrationService()
        migration = await service.get_migration_status(UUID(migration_id))

        if not migration:
            raise HTTPException(status_code=404, detail=f"Migration {migration_id} not found")

        progress_percentage = (migration.processed_count / migration.total_count * 100) if migration.total_count > 0 else 0

        return {
            "success": True,
            "migration": {
                "id": str(migration.id),
                "source_model": migration.source_model,
                "target_model": migration.target_model,
                "source_provider": migration.source_provider,
                "target_provider": migration.target_provider,
                "strategy": migration.strategy,
                "total_count": migration.total_count,
                "processed_count": migration.processed_count,
                "failed_count": migration.failed_count,
                "status": migration.status,
                "progress_percentage": progress_percentage,
                "error_message": migration.error_message,
                "created_at": migration.created_at.isoformat(),
                "started_at": migration.started_at.isoformat() if migration.started_at else None,
                "completed_at": migration.completed_at.isoformat() if migration.completed_at else None
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get migration status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get migration status: {str(e)}")


@router.post("/embedding-migrations/{migration_id}/start", response_model=Dict[str, Any])
async def start_embedding_migration(migration_id: str):
    """Start executing a migration task"""
    try:
        from ...services.embedding_migration_service import EmbeddingMigrationService
        from uuid import UUID

        service = EmbeddingMigrationService()
        await service.execute_migration(UUID(migration_id))

        return {
            "success": True,
            "message": f"Migration task {migration_id} started"
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to start migration: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to start migration: {str(e)}")


@router.post("/embedding-migrations/{migration_id}/cancel", response_model=Dict[str, Any])
async def cancel_embedding_migration(migration_id: str):
    """Cancel an in-progress migration task"""
    try:
        from ...services.embedding_migration_service import EmbeddingMigrationService
        from uuid import UUID

        service = EmbeddingMigrationService()
        cancelled = await service.cancel_migration(UUID(migration_id))

        if not cancelled:
            raise HTTPException(status_code=404, detail=f"Migration {migration_id} not found or cannot be cancelled")

        return {
            "success": True,
            "message": f"Migration task {migration_id} cancelled"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel migration: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to cancel migration: {str(e)}")


@router.delete("/embedding-migrations/{migration_id}", response_model=Dict[str, Any])
async def delete_embedding_migration(migration_id: str):
    """Delete a migration task"""
    try:
        from ...services.embedding_migration_service import EmbeddingMigrationService
        from uuid import UUID

        service = EmbeddingMigrationService()
        deleted = await service.delete_migration(UUID(migration_id))

        if not deleted:
            raise HTTPException(status_code=404, detail=f"Migration {migration_id} not found")

        return {
            "success": True,
            "message": f"Migration task {migration_id} deleted"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete migration: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete migration: {str(e)}")


# Google OAuth endpoints moved above to fix route conflict
