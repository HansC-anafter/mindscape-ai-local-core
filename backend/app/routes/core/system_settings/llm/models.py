"""
LLM Model CRUD Endpoints

Handles model listing, enabling/disabling, configuration, testing, and pulling.
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

        model_type_enum = None
        if model_type:
            model_type_enum = ModelType(model_type)

        filtered_models = await asyncio.to_thread(
            store.get_all_models,
            model_type=model_type_enum,
            enabled=enabled,
            provider=provider,
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


@router.post("/models/{model_id}/test", response_model=Dict[str, Any])
async def test_model_connection(model_id: int):
    """
    Test model connection by model ID

    Args:
        model_id: Model ID

    Returns:
        Success message with test results
    """
    try:
        from backend.app.services.model_config_store import ModelConfigStore
        from backend.app.services.system_settings_store import SystemSettingsStore
        import os
        from backend.app.services.config_store import ConfigStore

        model_store = ModelConfigStore()
        settings_store = SystemSettingsStore()

        model = await asyncio.to_thread(model_store.get_model_by_id, model_id)
        if not model:
            raise HTTPException(
                status_code=404, detail=f"Model with id {model_id} not found"
            )

        model_name = model.model_name
        provider = model.provider_name
        model_type = model.model_type

        # Get API key or configuration
        config_store = ConfigStore()
        config = await asyncio.to_thread(
            config_store.get_or_create_config, "default-user"
        )

        # Test based on provider and model type
        if provider == "openai":
            api_key = config.agent_backend.openai_api_key or os.getenv("OPENAI_API_KEY")
            if not api_key:
                return {"success": False, "message": "OpenAI API key not configured"}

            if model_type == "chat":
                try:
                    import openai

                    client = openai.OpenAI(api_key=api_key)
                    models = client.models.list()
                    next(iter(models), None)
                    return {
                        "success": True,
                        "message": "OpenAI chat model connection successful",
                    }
                except Exception as e:
                    return {
                        "success": False,
                        "message": f"OpenAI connection failed: {str(e)}",
                    }
            elif model_type == "embedding":
                try:
                    import openai

                    client = openai.OpenAI(api_key=api_key)
                    client.embeddings.create(model=model_name, input="test")
                    return {
                        "success": True,
                        "message": "OpenAI embedding model connection successful",
                    }
                except Exception as e:
                    return {
                        "success": False,
                        "message": f"OpenAI embedding connection failed: {str(e)}",
                    }

        elif provider == "anthropic":
            api_key = config.agent_backend.anthropic_api_key or os.getenv(
                "ANTHROPIC_API_KEY"
            )
            if not api_key:
                return {"success": False, "message": "Anthropic API key not configured"}

            if model_type == "chat":
                try:
                    import anthropic

                    client = anthropic.Anthropic(api_key=api_key)
                    client.messages.create(
                        model=model_name,
                        max_tokens=10,
                        messages=[{"role": "user", "content": "test"}],
                    )
                    return {
                        "success": True,
                        "message": "Anthropic chat model connection successful",
                    }
                except Exception as e:
                    return {
                        "success": False,
                        "message": f"Anthropic connection failed: {str(e)}",
                    }

        elif provider == "vertex-ai":
            service_account_setting = await asyncio.to_thread(
                settings_store.get_setting, "vertex_ai_service_account_json"
            )
            project_id_setting = await asyncio.to_thread(
                settings_store.get_setting, "vertex_ai_project_id"
            )
            location_setting = await asyncio.to_thread(
                settings_store.get_setting, "vertex_ai_location"
            )

            if not service_account_setting:
                return {
                    "success": False,
                    "message": "Vertex AI service account JSON not configured",
                }
            if not project_id_setting:
                return {
                    "success": False,
                    "message": "Vertex AI project ID not configured",
                }
            if not location_setting:
                return {
                    "success": False,
                    "message": "Vertex AI location not configured",
                }

            try:
                import json
                import google.auth
                from google.oauth2 import service_account
                from google.cloud import aiplatform

                service_account_data = json.loads(service_account_setting.value)
                credentials = service_account.Credentials.from_service_account_info(
                    service_account_data
                )
                project_id = project_id_setting.value
                location = location_setting.value

                aiplatform.init(
                    project=project_id, location=location, credentials=credentials
                )

                if model_type == "chat":
                    from vertexai.generative_models import GenerativeModel

                    model_instance = GenerativeModel(model_name)
                    response = model_instance.generate_content("test")
                    return {
                        "success": True,
                        "message": "Vertex AI chat model connection successful",
                    }
                elif model_type == "embedding":
                    from vertexai.language_models import TextEmbeddingModel

                    model_instance = TextEmbeddingModel.from_pretrained(model_name)
                    embeddings = model_instance.get_embeddings(["test"])
                    return {
                        "success": True,
                        "message": "Vertex AI embedding model connection successful",
                    }
            except Exception as e:
                return {
                    "success": False,
                    "message": f"Vertex AI connection failed: {str(e)}",
                }

        elif provider == "ollama":
            base_url_setting = await asyncio.to_thread(
                settings_store.get_setting, "ollama_base_url"
            )
            base_url = (
                base_url_setting.value if base_url_setting else "http://localhost:11434"
            )

            try:
                import requests

                response = requests.get(f"{base_url}/api/tags", timeout=5)
                if response.status_code == 200:
                    return {"success": True, "message": "Ollama connection successful"}
                else:
                    return {
                        "success": False,
                        "message": f"Ollama connection failed: {response.status_code}",
                    }
            except Exception as e:
                return {
                    "success": False,
                    "message": f"Ollama connection failed: {str(e)}",
                }

        return {
            "success": False,
            "message": f"Test not implemented for provider: {provider}",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to test model connection: {e}", exc_info=True)
        return {"success": False, "message": f"Test failed: {str(e)}"}


@router.post("/llm-models/pull", response_model=Dict[str, Any])
async def pull_model(
    payload: Dict[str, Any] = Body(..., description="Model pull payload")
):
    """
    Trigger model pull (specifically for Ollama)
    """
    try:
        from backend.app.services.system_settings_store import SystemSettingsStore
        import requests

        model_name = payload.get("model_name")
        provider = payload.get("provider")

        if not model_name:
            raise HTTPException(status_code=400, detail="model_name is required")

        if provider != "ollama":
            return {
                "success": False,
                "message": "Pull only supported for Ollama provider",
            }

        settings_store = SystemSettingsStore()
        base_url_setting = await asyncio.to_thread(
            settings_store.get_setting, "ollama_base_url"
        )
        base_url = (
            base_url_setting.value if base_url_setting else "http://localhost:11434"
        )

        try:
            requests.post(
                f"{base_url}/api/pull",
                json={"name": model_name, "stream": True},
                timeout=0.1,
            )
        except requests.exceptions.ReadTimeout:
            return {
                "success": True,
                "message": f"Model download started for {model_name}. It may take a while.",
            }
        except Exception as e:
            return {"success": False, "message": f"Failed to start download: {str(e)}"}

        return {"success": True, "message": f"Model download started for {model_name}"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to pull model: {e}", exc_info=True)
        return {"success": False, "message": f"Pull failed: {str(e)}"}
