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
                "metadata": m.metadata,
            }
            for m in filtered_models
        ]
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
                "metadata": model.metadata,
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

        config_store = ConfigStore()
        config = await asyncio.to_thread(
            config_store.get_or_create_config, "default-user"
        )

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

        elif provider == "gemini-api":
            api_key = os.getenv("GOOGLE_AI_API_KEY") or os.getenv("GEMINI_API_KEY")
            if not api_key:
                api_key_setting = await asyncio.to_thread(
                    settings_store.get_setting, "gemini-api_api_key"
                )
                api_key = api_key_setting.value if api_key_setting else None
            if not api_key:
                return {
                    "success": False,
                    "message": "Google AI API key not configured (set GOOGLE_AI_API_KEY or GEMINI_API_KEY)",
                }

            try:
                import google.generativeai as genai

                genai.configure(api_key=api_key)
                if model_type == "embedding":
                    result = genai.embed_content(
                        model=f"models/{model_name}",
                        content="test",
                    )
                    embedding = result.get("embedding", [])
                    if embedding:
                        return {
                            "success": True,
                            "message": f"Gemini embedding connection successful (dimensions: {len(embedding)})",
                        }
                    return {
                        "success": False,
                        "message": "Gemini embedding returned empty result",
                    }
                else:
                    model_instance = genai.GenerativeModel(model_name)
                    response = model_instance.generate_content("test")
                    return {
                        "success": True,
                        "message": "Gemini chat model connection successful",
                    }
            except Exception as e:
                return {
                    "success": False,
                    "message": f"Gemini connection failed: {str(e)}",
                }

        elif provider == "huggingface":
            import os
            from pathlib import Path
            import requests

            cache_dir = os.path.expanduser("~/.cache/huggingface/hub")
            model_dir_name = f"models--{model_name.replace('/', '--')}"
            model_dir = Path(cache_dir) / model_dir_name

            # Check if model exists locally in cache
            if model_dir.exists() and (model_dir / "snapshots").exists():
                snapshots = list((model_dir / "snapshots").glob("*"))
                if snapshots:
                    return {
                        "success": True,
                        "message": f"HuggingFace model '{model_name}' is downloaded and ready locally.",
                    }

            # If not found locally, check if it's a valid remote repo via HF API
            try:
                api_url = f"https://huggingface.co/api/models/{model_name}"
                resp = requests.get(api_url, timeout=5)
                if resp.status_code == 200:
                    return {
                        "success": True,
                        "message": f"HuggingFace model '{model_name}' is valid (not yet downloaded).",
                    }
                elif resp.status_code == 404:
                    return {
                        "success": False,
                        "message": f"HuggingFace model '{model_name}' not found on the hub.",
                    }
                else:
                    return {
                        "success": False,
                        "message": f"Failed to verify HuggingFace model. Status: {resp.status_code}",
                    }
            except Exception as e:
                return {
                    "success": False,
                    "message": f"HuggingFace connection failed: {str(e)}",
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


# ── Redis-backed pull progress tracking ──
# Uses Redis Hash per task so state is shared across uvicorn workers.
# Falls back to in-memory dict if Redis is unavailable.
import uuid as _uuid
import time as _time
import threading as _threading
import json as _json
import os as _os

_PULL_TASK_TTL = 300  # seconds
_PULL_KEY_PREFIX = "pull_task:"

# Fallback in-memory store (used only when Redis is unavailable)
_pull_tasks_fallback: Dict[str, Dict[str, Any]] = {}


def _sync_redis():
    """Get a synchronous Redis client for use in download threads."""
    try:
        import redis
        return redis.Redis(
            host=_os.getenv("REDIS_HOST", "redis"),
            port=int(_os.getenv("REDIS_PORT", "6379")),
            password=_os.getenv("REDIS_PASSWORD") or None,
            db=int(_os.getenv("REDIS_DB", "0")),
            socket_connect_timeout=2,
            decode_responses=True,
        )
    except Exception:
        return None


async def _async_redis():
    """Get async Redis client."""
    try:
        from backend.app.services.cache.async_redis import get_async_redis_client
        return await get_async_redis_client()
    except Exception:
        return None


def _task_key(task_id: str) -> str:
    return f"{_PULL_KEY_PREFIX}{task_id}"


def _set_task_sync(r, task_id: str, fields: Dict[str, Any]):
    """Write task fields to Redis (sync, for use in threads)."""
    key = _task_key(task_id)
    if r:
        try:
            # Convert all values to strings for Redis
            str_fields = {k: str(v) for k, v in fields.items()}
            r.hset(key, mapping=str_fields)
            r.expire(key, _PULL_TASK_TTL)
            return
        except Exception:
            pass
    # Fallback
    if task_id not in _pull_tasks_fallback:
        _pull_tasks_fallback[task_id] = {}
    _pull_tasks_fallback[task_id].update(fields)


async def _set_task_async(task_id: str, fields: Dict[str, Any]):
    """Write task fields to Redis (async, for use in endpoints)."""
    r = await _async_redis()
    key = _task_key(task_id)
    if r:
        try:
            str_fields = {k: str(v) for k, v in fields.items()}
            await r.hset(key, mapping=str_fields)
            await r.expire(key, _PULL_TASK_TTL)
            return
        except Exception:
            pass
    # Fallback
    if task_id not in _pull_tasks_fallback:
        _pull_tasks_fallback[task_id] = {}
    _pull_tasks_fallback[task_id].update(fields)


def _get_task_sync(r, task_id: str) -> Optional[Dict[str, Any]]:
    """Read task from Redis (sync)."""
    key = _task_key(task_id)
    if r:
        try:
            data = r.hgetall(key)
            if data:
                return _parse_task(data)
        except Exception:
            pass
    return _pull_tasks_fallback.get(task_id)


async def _get_task_async(task_id: str) -> Optional[Dict[str, Any]]:
    """Read task from Redis (async)."""
    r = await _async_redis()
    key = _task_key(task_id)
    if r:
        try:
            data = await r.hgetall(key)
            if data:
                return _parse_task(data)
        except Exception:
            pass
    return _pull_tasks_fallback.get(task_id)


def _parse_task(data: Dict[str, str]) -> Dict[str, Any]:
    """Parse Redis hash string values back to proper types."""
    return {
        "status": data.get("status", ""),
        "progress_pct": int(float(data.get("progress_pct", "0"))),
        "downloaded_bytes": int(float(data.get("downloaded_bytes", "0"))),
        "total_bytes": int(float(data.get("total_bytes", "0"))),
        "message": data.get("message", ""),
        "model_name": data.get("model_name", ""),
        "model_id": data.get("model_id", ""),
        "provider": data.get("provider", ""),
        "updated_at": float(data.get("updated_at", "0")),
    }


def _is_cancelled_sync(r, task_id: str) -> bool:
    """Check if task has been cancelled (sync, for download threads)."""
    if r:
        try:
            val = r.hget(_task_key(task_id), "status")
            return val == "cancelled"
        except Exception:
            pass
    fb = _pull_tasks_fallback.get(task_id, {})
    return fb.get("status") == "cancelled"


def _task_to_response(task_id: str, task: Dict[str, Any]) -> Dict[str, Any]:
    """Convert task dict to API response."""
    return {
        "task_id": task_id,
        "status": task.get("status", ""),
        "progress_pct": task.get("progress_pct", 0),
        "downloaded_bytes": task.get("downloaded_bytes", 0),
        "total_bytes": task.get("total_bytes", 0),
        "message": task.get("message", ""),
        "model_name": task.get("model_name", ""),
        "model_id": task.get("model_id", ""),
        "provider": task.get("provider", ""),
    }


@router.post("/llm-models/pull", response_model=Dict[str, Any])
async def pull_model(
    payload: Dict[str, Any] = Body(..., description="Model pull payload")
):
    """Trigger model pull with progress tracking."""
    try:
        model_name = payload.get("model_name")
        provider = payload.get("provider")

        if not model_name:
            raise HTTPException(status_code=400, detail="model_name is required")

        if provider not in ["ollama", "huggingface"]:
            return {
                "success": False,
                "message": f"Pull only supported for Ollama and HuggingFace providers (got {provider})",
            }

        task_id = _uuid.uuid4().hex[:8]
        model_id = payload.get("model_id", "")
        init_fields = {
            "status": "starting",
            "progress_pct": 0,
            "downloaded_bytes": 0,
            "total_bytes": 0,
            "message": f"Starting download for {model_name}...",
            "model_name": model_name,
            "model_id": model_id,
            "provider": provider,
            "updated_at": _time.time(),
        }
        await _set_task_async(task_id, init_fields)

        if provider == "huggingface":
            asyncio.create_task(_run_hf_download(task_id, model_name))
        else:
            asyncio.create_task(_run_ollama_pull(task_id, model_name))

        return {
            "success": True,
            "task_id": task_id,
            "message": f"Download started for {model_name}",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to pull model: {e}", exc_info=True)
        return {"success": False, "message": f"Pull failed: {str(e)}"}


async def _run_ollama_pull(task_id: str, model_name: str):
    """Background task: Ollama pull with streaming progress."""
    import requests
    try:
        from backend.app.services.system_settings_store import SystemSettingsStore
        settings_store = SystemSettingsStore()
        base_url_setting = await asyncio.to_thread(
            settings_store.get_setting, "ollama_base_url"
        )
        base_url = base_url_setting.value if base_url_setting else "http://localhost:11434"

        await _set_task_async(task_id, {
            "status": "downloading",
            "message": f"Pulling {model_name} from Ollama...",
            "updated_at": _time.time(),
        })

        def _stream_pull():
            r = _sync_redis()
            resp = requests.post(
                f"{base_url}/api/pull",
                json={"name": model_name, "stream": True},
                stream=True,
                timeout=3600,
            )
            for line in resp.iter_lines():
                if not line:
                    continue
                try:
                    data = _json.loads(line)
                    status = data.get("status", "")
                    total = data.get("total", 0)
                    completed = data.get("completed", 0)

                    if _is_cancelled_sync(r, task_id):
                        break

                    update: Dict[str, Any] = {
                        "message": status,
                        "updated_at": _time.time(),
                    }
                    if total > 0:
                        update["total_bytes"] = total
                        update["downloaded_bytes"] = completed
                        update["progress_pct"] = min(99, int(completed * 100 / total))

                    if status == "success":
                        update["status"] = "completed"
                        update["progress_pct"] = 100
                        update["message"] = f"Successfully pulled {model_name}"

                    _set_task_sync(r, task_id, update)

                    if status == "success":
                        break
                except Exception:
                    pass

        await asyncio.to_thread(_stream_pull)

        task = await _get_task_async(task_id)
        if task and task.get("status") != "completed":
            await _set_task_async(task_id, {
                "status": "completed",
                "progress_pct": 100,
                "message": f"Pull completed for {model_name}",
                "updated_at": _time.time(),
            })

    except Exception as e:
        logger.error(f"Ollama pull failed for {model_name}: {e}", exc_info=True)
        await _set_task_async(task_id, {
            "status": "failed",
            "message": f"Pull failed: {str(e)}",
            "updated_at": _time.time(),
        })


async def _run_hf_download(task_id: str, model_name: str):
    """Background task: HuggingFace download using Python huggingface_hub API."""
    try:
        await _set_task_async(task_id, {
            "status": "downloading",
            "message": f"Downloading {model_name}...",
            "updated_at": _time.time(),
        })

        def _do_download():
            from huggingface_hub import snapshot_download
            import os
            import threading

            r = _sync_redis()

            # Get repo info to estimate total size
            try:
                from huggingface_hub import HfApi
                api = HfApi()
                repo_info = api.repo_info(model_name, repo_type="model")
                siblings = repo_info.siblings or []
                total_size = 0
                for s in siblings:
                    sz = getattr(s, 'size', None) or getattr(s, 'lfs', {})
                    if isinstance(sz, dict):
                        sz = sz.get('size', 0)
                    total_size += sz or 0
                if total_size > 0:
                    _set_task_sync(r, task_id, {
                        "total_bytes": total_size,
                        "message": f"Downloading {model_name} ({total_size / 1e9:.1f} GB)...",
                        "updated_at": _time.time(),
                    })
                    logger.info(f"HF download {model_name}: total_bytes={total_size}")
                else:
                    logger.warning(f"HF download {model_name}: could not determine total size from {len(siblings)} siblings")
            except Exception as e:
                logger.warning(f"HF download {model_name}: repo_info failed: {e}")

            # Monitor progress via file system polling
            download_done = threading.Event()
            download_error = None

            def _monitor_progress():
                cache_dir = os.path.expanduser("~/.cache/huggingface/hub")
                model_dir_name = f"models--{model_name.replace('/', '--')}"
                model_cache = os.path.join(cache_dir, model_dir_name)

                while not download_done.is_set():
                    if _is_cancelled_sync(r, task_id):
                        break
                    try:
                        task = _get_task_sync(r, task_id)
                        if not task:
                            break

                        downloaded = 0
                        for scan_dir in [model_cache, os.path.join(model_cache, "blobs")]:
                            if not os.path.exists(scan_dir):
                                continue
                            for root, dirs, files in os.walk(scan_dir):
                                for f in files:
                                    try:
                                        downloaded += os.path.getsize(os.path.join(root, f))
                                    except OSError:
                                        pass
                        if downloaded > 0:
                            total = task.get("total_bytes", 0)
                            update: Dict[str, Any] = {
                                "downloaded_bytes": downloaded,
                                "updated_at": _time.time(),
                            }
                            if total > 0:
                                pct = min(99, int(downloaded * 100 / total))
                                update["progress_pct"] = pct
                                update["message"] = f"Downloading... {downloaded / 1e9:.1f}/{total / 1e9:.1f} GB"
                            else:
                                update["message"] = f"Downloading... {downloaded / 1e6:.0f} MB"
                            _set_task_sync(r, task_id, update)
                    except Exception:
                        pass
                    download_done.wait(1)

            monitor = threading.Thread(target=_monitor_progress, daemon=True)
            monitor.start()

            try:
                snapshot_download(model_name, repo_type="model")
            except Exception as e:
                download_error = e
            finally:
                download_done.set()
                monitor.join(timeout=5)

            if download_error:
                raise download_error

        await asyncio.to_thread(_do_download)

        await _set_task_async(task_id, {
            "status": "completed",
            "progress_pct": 100,
            "message": f"Successfully downloaded {model_name}",
            "updated_at": _time.time(),
        })

    except Exception as e:
        logger.error(f"HF download failed for {model_name}: {e}", exc_info=True)
        await _set_task_async(task_id, {
            "status": "failed",
            "message": f"Download failed: {str(e)}",
            "updated_at": _time.time(),
        })


@router.get("/llm-models/pull/active", response_model=List[Dict[str, Any]])
async def get_active_pulls():
    """Get all active pull tasks (for page reload recovery)."""
    results = []
    r = await _async_redis()
    if r:
        try:
            keys = await r.keys(f"{_PULL_KEY_PREFIX}*")
            for key in keys:
                data = await r.hgetall(key)
                if data and data.get("status") in ("starting", "downloading"):
                    task_id = key.replace(_PULL_KEY_PREFIX, "")
                    results.append(_task_to_response(task_id, _parse_task(data)))
        except Exception:
            pass
    # Also check fallback
    for tid, t in _pull_tasks_fallback.items():
        if t.get("status") in ("starting", "downloading"):
            results.append(_task_to_response(tid, t))
    return results


@router.get("/llm-models/pull/{task_id}/progress", response_model=Dict[str, Any])
async def get_pull_progress(task_id: str):
    """Get download progress for a pull task."""
    task = await _get_task_async(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found or expired")
    return _task_to_response(task_id, task)


@router.post("/llm-models/pull/{task_id}/cancel", response_model=Dict[str, Any])
async def cancel_pull(task_id: str):
    """Cancel an in-progress pull task."""
    task = await _get_task_async(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found or expired")
    if task.get("status") not in ("starting", "downloading"):
        return {"success": False, "message": f"Task already {task.get('status')}"}
    await _set_task_async(task_id, {
        "status": "cancelled",
        "message": "Download cancelled",
        "updated_at": _time.time(),
    })
    return {"success": True, "message": "Download cancelled"}


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




