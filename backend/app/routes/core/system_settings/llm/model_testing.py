"""
LLM Model Connection Testing Endpoints

Provider-specific connection test logic, extracted from models.py.
Each provider has its own test function dispatched via _TESTERS dict.
"""

import asyncio
import logging
import os
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Body

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Per-provider test functions ──


async def _test_openai(
    model_name: str, model_type: str, settings_store, config
) -> Dict[str, Any]:
    api_key = config.agent_backend.openai_api_key or os.getenv("OPENAI_API_KEY")
    
    # Fallback: read from SystemSettingsStore (where the UI saves it)
    if not api_key:
        api_key_setting = await asyncio.to_thread(
            settings_store.get_setting, "openai_api_key"
        )
        if api_key_setting and api_key_setting.value:
            api_key = api_key_setting.value
    
    # Check for custom base URL
    base_url_setting = await asyncio.to_thread(
        settings_store.get_setting, "openai_api_base"
    )
    base_url = base_url_setting.value if base_url_setting else os.getenv("OPENAI_API_BASE")
    
    # If a custom base URL is used (like LM Studio or local proxy), an API key might not be required
    # But the official openai SDK requires *some* string.
    if base_url and not api_key:
        api_key = "dummy-key-for-local-endpoint"
        
    if not api_key:
        return {"success": False, "message": "OpenAI API key not configured"}

    if model_type == "chat":
        try:
            import openai
            
            client_kwargs = {"api_key": api_key}
            if base_url:
                client_kwargs["base_url"] = base_url

            client = openai.OpenAI(**client_kwargs)
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
            
            client_kwargs = {"api_key": api_key}
            if base_url:
                client_kwargs["base_url"] = base_url

            client = openai.OpenAI(**client_kwargs)
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

    return {"success": False, "message": f"Unknown model type: {model_type}"}


async def _test_anthropic(
    model_name: str, model_type: str, settings_store, config
) -> Dict[str, Any]:
    api_key = config.agent_backend.anthropic_api_key or os.getenv("ANTHROPIC_API_KEY")
    
    # Fallback: read from SystemSettingsStore (where the UI saves it)
    if not api_key:
        api_key_setting = await asyncio.to_thread(
            settings_store.get_setting, "anthropic_api_key"
        )
        if api_key_setting and api_key_setting.value:
            api_key = api_key_setting.value
    
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

    return {"success": False, "message": f"Unknown model type: {model_type}"}


async def _test_vertex_ai(
    model_name: str, model_type: str, settings_store, config
) -> Dict[str, Any]:
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

    return {"success": False, "message": f"Unknown model type: {model_type}"}


async def _test_ollama(
    model_name: str, model_type: str, settings_store, config
) -> Dict[str, Any]:
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


async def _test_gemini_api(
    model_name: str, model_type: str, settings_store, config
) -> Dict[str, Any]:
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


async def _test_huggingface(
    model_name: str, model_type: str, settings_store, config
) -> Dict[str, Any]:
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


# ── Provider dispatch table ──

_TESTERS = {
    "openai": _test_openai,
    "anthropic": _test_anthropic,
    "vertex-ai": _test_vertex_ai,
    "ollama": _test_ollama,
    "gemini-api": _test_gemini_api,
    "huggingface": _test_huggingface,
}


# ── Endpoint ──


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
        from backend.app.services.config_store import ConfigStore

        model_store = ModelConfigStore()
        settings_store = SystemSettingsStore()

        model = await asyncio.to_thread(model_store.get_model_by_id, model_id)
        if not model:
            raise HTTPException(
                status_code=404, detail=f"Model with id {model_id} not found"
            )

        provider = model.provider_name
        tester = _TESTERS.get(provider)
        if not tester:
            return {
                "success": False,
                "message": f"Test not implemented for provider: {provider}",
            }

        config_store = ConfigStore()
        config = await asyncio.to_thread(
            config_store.get_or_create_config, "default-user"
        )

        return await tester(
            model_name=model.model_name,
            model_type=model.model_type,
            settings_store=settings_store,
            config=config,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to test model connection: {e}", exc_info=True)
        return {"success": False, "message": f"Test failed: {str(e)}"}
