"""
LLM Model CRUD Endpoints

Handles model listing, enabling/disabling, configuration updates, and deletion.
Connection testing is in model_testing.py, pull/download in pull_manager.py.
"""

import asyncio

from fastapi import APIRouter, HTTPException, Query, Body
from typing import Dict, Any, List, Optional
import logging

from backend.app.models.system_settings import (
    SystemSetting,
    SettingType,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Shared serialization helper ──


def _model_to_dict(m, include_metadata: bool = True) -> Dict[str, Any]:
    """Convert a model ORM/Pydantic object to a response dict.

    Args:
        m: Model instance with standard fields.
        include_metadata: Whether to include the metadata field.
    """
    d = {
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
    if include_metadata:
        d["metadata"] = m.metadata
    return d


@router.get("/models", response_model=List[Dict[str, Any]])
async def get_models(
    model_type: Optional[str] = Query(
        None, description="Filter by model type ('chat' or 'embedding')"
    ),
    enabled: Optional[bool] = Query(None, description="Filter by enabled status"),
    provider: Optional[str] = Query(None, description="Filter by provider name"),
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

        models = await asyncio.to_thread(store.get_all_models)
        if not models:
            await asyncio.to_thread(store.initialize_default_models)
            models = await asyncio.to_thread(store.get_all_models)
        else:
            await asyncio.to_thread(store.sync_default_models)

        model_type_enum = None
        if model_type:
            model_type_enum = ModelType(model_type)

        filtered_models = await asyncio.to_thread(
            store.get_all_models,
            model_type=model_type_enum,
            enabled=enabled,
            provider=provider,
        )

        return [_model_to_dict(m) for m in filtered_models]
    except Exception as e:
        logger.error(f"Failed to get models: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get models: {str(e)}")


@router.patch("/models/{model_id}/metadata", response_model=Dict[str, Any])
async def patch_model_metadata(model_id: int, payload: Dict[str, Any] = Body(...)):
    """
    Merge metadata into an existing model. Used by the frontend to push
    HuggingFace metadata (since the backend container cannot reach external APIs).
    """
    from backend.app.services.model_config_store import ModelConfigStore

    store = ModelConfigStore()
    model = await asyncio.to_thread(store.get_model_by_id, model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    model.metadata = {**(model.metadata or {}), **payload}
    if payload.get("hf_context_length") and not model.context_window:
        model.context_window = payload["hf_context_length"]

    updated = await asyncio.to_thread(store.create_or_update_model, model)
    return {"success": True, "id": updated.id, "metadata": updated.metadata}


@router.put("/models/{model_id}/enable", response_model=Dict[str, Any])
async def toggle_model_enabled(model_id: int, request: Dict[str, bool] = Body(...)):
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

        model = await asyncio.to_thread(store.toggle_model_enabled, model_id, enabled)

        if not model:
            raise HTTPException(
                status_code=404, detail=f"Model with id {model_id} not found"
            )

        return _model_to_dict(model, include_metadata=False)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to toggle model enabled: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to toggle model enabled: {str(e)}"
        )


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

        model = await asyncio.to_thread(model_store.get_model_by_id, model_id)
        if not model:
            raise HTTPException(
                status_code=404, detail=f"Model with id {model_id} not found"
            )

        api_key_setting_key = f"{model.provider_name}_api_key"
        if model.provider_name == "gemini-api":
            api_key_setting_key = "gemini-api_api_key"
        api_key_setting = await asyncio.to_thread(
            settings_store.get_setting, api_key_setting_key
        )
        api_key_configured = api_key_setting is not None and bool(api_key_setting.value)
        provider_api_key = api_key_setting.value if api_key_setting else None

        if model.provider_name == "vertex-ai":
            service_account_setting = await asyncio.to_thread(
                settings_store.get_setting, "vertex_ai_service_account_json"
            )
            if service_account_setting and service_account_setting.value:
                api_key_configured = True
                provider_api_key = service_account_setting.value

        base_url = None
        provider_base_url = None
        if model.provider_name == "ollama":
            base_url = "http://localhost:11434"
            ollama_base_url_setting = await asyncio.to_thread(
                settings_store.get_setting, "ollama_base_url"
            )
            provider_base_url = (
                ollama_base_url_setting.value if ollama_base_url_setting else base_url
            )

        project_id = None
        location = None
        provider_project_id = None
        provider_location = None
        if model.provider_name == "vertex-ai":
            project_id_setting = await asyncio.to_thread(
                settings_store.get_setting, "vertex_ai_project_id"
            )
            location_setting = await asyncio.to_thread(
                settings_store.get_setting, "vertex_ai_location"
            )
            provider_project_id = (
                project_id_setting.value if project_id_setting else None
            )
            provider_location = (
                location_setting.value if location_setting else "us-central1"
            )
            project_id = provider_project_id
            location = provider_location

        return {
            "model": _model_to_dict(model),
            "api_key_configured": api_key_configured,
            "base_url": base_url,
            "project_id": project_id,
            "location": location,
            "provider_config": {
                "api_key_configured": api_key_configured,
                "api_key": provider_api_key if api_key_configured else None,
                "base_url": provider_base_url,
                "project_id": provider_project_id,
                "location": provider_location,
            },
            "quota_info": None,
        }
    except Exception as e:
        logger.error(f"Failed to get model config: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to get model config: {str(e)}"
        )


@router.put("/models/{model_id}/config", response_model=Dict[str, Any])
async def update_model_config(model_id: int, config: Dict[str, Any] = Body(...)):
    """
    Update model configuration (API key, base URL, project ID, location, etc.)

    Args:
        model_id: Model ID
        config: Configuration data (api_key, base_url, project_id, location)

    Returns:
        Success message
    """
    try:
        from backend.app.services.model_config_store import ModelConfigStore
        from backend.app.services.system_settings_store import SystemSettingsStore

        model_store = ModelConfigStore()
        settings_store = SystemSettingsStore()

        model = await asyncio.to_thread(model_store.get_model_by_id, model_id)
        if not model:
            raise HTTPException(
                status_code=404, detail=f"Model with id {model_id} not found"
            )

        is_provider_level = config.get("provider_level", False)

        if "api_key" in config and config["api_key"]:
            api_key_setting_key = f"{model.provider_name}_api_key"
            setting = SystemSetting(
                key=api_key_setting_key,
                value=config["api_key"],
                value_type=SettingType.STRING,
                category="models",
                description=f"API key for {model.provider_name}",
                is_sensitive=True,
            )
            await asyncio.to_thread(settings_store.save_setting, setting)

        if model.provider_name == "ollama" and "base_url" in config:
            setting = SystemSetting(
                key="ollama_base_url",
                value=config.get("base_url", "http://localhost:11434"),
                value_type=SettingType.STRING,
                category="models",
                description="Ollama base URL",
            )
            await asyncio.to_thread(settings_store.save_setting, setting)

        if model.provider_name == "vertex-ai":
            if "project_id" in config and config["project_id"]:
                setting = SystemSetting(
                    key="vertex_ai_project_id",
                    value=config["project_id"],
                    value_type=SettingType.STRING,
                    category="models",
                    description="GCP Project ID for Vertex AI",
                )
                await asyncio.to_thread(settings_store.save_setting, setting)
            if "location" in config and config["location"]:
                setting = SystemSetting(
                    key="vertex_ai_location",
                    value=config["location"],
                    value_type=SettingType.STRING,
                    category="models",
                    description="GCP Location/Region for Vertex AI",
                )
                await asyncio.to_thread(settings_store.save_setting, setting)
            if "api_key" in config and config["api_key"]:
                import json

                try:
                    service_account_data = (
                        json.loads(config["api_key"])
                        if isinstance(config["api_key"], str)
                        else config["api_key"]
                    )
                    if (
                        isinstance(service_account_data, dict)
                        and service_account_data.get("type") == "service_account"
                    ):
                        setting = SystemSetting(
                            key="vertex_ai_service_account_json",
                            value=json.dumps(service_account_data),
                            value_type=SettingType.JSON,
                            category="models",
                            description="GCP Service Account JSON for Vertex AI",
                            is_sensitive=True,
                        )
                        await asyncio.to_thread(settings_store.save_setting, setting)
                except (json.JSONDecodeError, TypeError):
                    logger.warning("Invalid service account JSON format for Vertex AI")

        return {"success": True, "message": "Model configuration updated successfully"}
    except Exception as e:
        logger.error(f"Failed to update model config: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to update model config: {str(e)}"
        )


@router.delete("/models/{model_id}", response_model=Dict[str, Any])
async def delete_model(model_id: int):
    """Delete a model from the configuration."""
    try:
        from backend.app.services.model_config_store import ModelConfigStore
        store = ModelConfigStore()
        success = await asyncio.to_thread(store.delete_model, model_id)
        if success:
            return {"success": True, "message": "Model removed"}
        else:
            raise HTTPException(status_code=404, detail="Model not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete model {model_id}: {e}", exc_info=True)
        return {"success": False, "message": f"Delete failed: {str(e)}"}
