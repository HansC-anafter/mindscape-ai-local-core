"""Embedding model connection test routes."""

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

from backend.app.routes.core.system_settings.shared import settings_store

from .state import _utc_now

router = APIRouter()

@router.post("/llm-models/test-embedding", response_model=Dict[str, Any])
async def test_embedding_model_connection(
    model_name: Optional[str] = Query(
        None,
        description="Model name to test (uses current setting if not provided)",
    )
):
    """Test embedding model connection"""
    try:
        import os
        from backend.app.services.config_store import ConfigStore

        if not model_name:
            embedding_setting = settings_store.get_setting("embedding_model")
            if not embedding_setting:
                raise HTTPException(
                    status_code=400, detail="No embedding model configured"
                )
            model_name = str(embedding_setting.value)
            provider = embedding_setting.metadata.get("provider", "openai")
        else:
            embedding_setting = settings_store.get_setting("embedding_model")
            if embedding_setting and str(embedding_setting.value) == model_name:
                provider = embedding_setting.metadata.get("provider", "openai")
            elif "text-embedding" in model_name.lower():
                provider = "openai"
            elif "gemini-embedding" in model_name.lower():
                provider = "gemini-api"
            elif "textembedding" in model_name.lower():
                provider = "vertex-ai"
            else:
                provider = "openai"

        if provider == "vertex-ai":
            service_account_setting = settings_store.get_setting(
                "vertex_ai_service_account_json"
            )
            project_id_setting = settings_store.get_setting("vertex_ai_project_id")
            location_setting = settings_store.get_setting("vertex_ai_location")

            vertex_service_account_json = (
                service_account_setting.value
                if service_account_setting and service_account_setting.value
                else os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            )
            vertex_project_id = (
                project_id_setting.value
                if project_id_setting and project_id_setting.value
                else os.getenv("GOOGLE_CLOUD_PROJECT")
            )
            vertex_location = (
                location_setting.value
                if location_setting and location_setting.value
                else os.getenv("VERTEX_LOCATION", "us-central1")
            )

            if not vertex_service_account_json or not vertex_project_id:
                raise HTTPException(
                    status_code=400,
                    detail="Vertex AI credentials not configured (service_account and project_id required)",
                )

            try:
                from google.cloud import aiplatform
                from google.oauth2 import service_account
                from vertexai.language_models import TextEmbeddingModel
                import vertexai
                import json

                credentials = None
                if vertex_service_account_json:
                    try:
                        sa_info = json.loads(vertex_service_account_json)
                        credentials = (
                            service_account.Credentials.from_service_account_info(
                                sa_info
                            )
                        )
                        if not vertex_project_id and "project_id" in sa_info:
                            vertex_project_id = sa_info["project_id"]
                    except (json.JSONDecodeError, ValueError):
                        credentials = (
                            service_account.Credentials.from_service_account_file(
                                vertex_service_account_json
                            )
                        )
                        if not vertex_project_id:
                            with open(vertex_service_account_json, "r") as f:
                                sa_info = json.load(f)
                                if "project_id" in sa_info:
                                    vertex_project_id = sa_info["project_id"]

                if credentials:
                    aiplatform.init(
                        project=vertex_project_id,
                        location=vertex_location,
                        credentials=credentials,
                    )
                    vertexai.init(
                        project=vertex_project_id,
                        location=vertex_location,
                        credentials=credentials,
                    )
                else:
                    aiplatform.init(project=vertex_project_id, location=vertex_location)
                    vertexai.init(project=vertex_project_id, location=vertex_location)

                model = TextEmbeddingModel.from_pretrained(model_name)
                embeddings = model.get_embeddings(["test"])

                success = bool(
                    embeddings and len(embeddings) > 0 and embeddings[0].values
                )
                dimensions = len(embeddings[0].values) if success else None
                message = (
                    f"Connection successful (dimensions: {dimensions})"
                    if success
                    else "Connection failed"
                )

                return {
                    "success": success,
                    "model_name": model_name,
                    "provider": provider,
                    "message": message,
                    "dimensions": dimensions,
                    "tested_at": _utc_now().isoformat(),
                }
            except Exception as api_error:
                return {
                    "success": False,
                    "model_name": model_name,
                    "provider": provider,
                    "message": f"Connection failed: {str(api_error)}",
                    "error": str(api_error),
                    "tested_at": _utc_now().isoformat(),
                }
        elif provider == "gemini-api":
            api_key = os.getenv("GOOGLE_AI_API_KEY") or os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise HTTPException(
                    status_code=400,
                    detail="Google AI API key not configured (set GOOGLE_AI_API_KEY or GEMINI_API_KEY)",
                )

            try:
                import google.generativeai as genai

                genai.configure(api_key=api_key)
                result = genai.embed_content(
                    model=f"models/{model_name}",
                    content="test",
                )
                embedding = result.get("embedding", [])
                success = bool(embedding and len(embedding) > 0)
                dimensions = len(embedding) if success else None
                message = (
                    f"Connection successful (dimensions: {dimensions})"
                    if success
                    else "Connection failed"
                )

                return {
                    "success": success,
                    "model_name": model_name,
                    "provider": provider,
                    "message": message,
                    "dimensions": dimensions,
                    "tested_at": _utc_now().isoformat(),
                }
            except Exception as api_error:
                return {
                    "success": False,
                    "model_name": model_name,
                    "provider": provider,
                    "message": f"Connection failed: {str(api_error)}",
                    "error": str(api_error),
                    "tested_at": _utc_now().isoformat(),
                }
        else:
            config_store = ConfigStore()
            config = config_store.get_or_create_config("default-user")
            api_key = config.agent_backend.openai_api_key or os.getenv("OPENAI_API_KEY")
            
            # Fallback: read from SystemSettingsStore (where the UI saves it)
            if not api_key:
                import asyncio as _asyncio
                _key_setting = await _asyncio.to_thread(
                    settings_store.get_setting, "openai_api_key"
                )
                if _key_setting and _key_setting.value:
                    api_key = _key_setting.value
            
            # Check for custom base URL
            import asyncio
            base_url_setting = await asyncio.to_thread(
                settings_store.get_setting, "openai_api_base"
            )
            base_url = base_url_setting.value if base_url_setting else os.getenv("OPENAI_API_BASE")
            
            if base_url and not api_key:
                api_key = "dummy-key-for-local-endpoint"
                
            if not api_key:
                raise HTTPException(
                    status_code=400, detail="OpenAI API key not configured"
                )

            try:
                import openai

                client_kwargs = {"api_key": api_key}
                if base_url:
                    client_kwargs["base_url"] = base_url

                client = openai.OpenAI(**client_kwargs)
                response = client.embeddings.create(model=model_name, input="test")
                success = bool(
                    response.data
                    and len(response.data) > 0
                    and response.data[0].embedding
                )
                message = (
                    f"Connection successful (dimensions: {len(response.data[0].embedding)})"
                    if success
                    else "Connection failed"
                )

                return {
                    "success": success,
                    "model_name": model_name,
                    "provider": provider,
                    "message": message,
                    "dimensions": (
                        len(response.data[0].embedding) if success else None
                    ),
                    "tested_at": _utc_now().isoformat(),
                }
            except Exception as api_error:
                return {
                    "success": False,
                    "model_name": model_name,
                    "provider": provider,
                    "message": f"Connection failed: {str(api_error)}",
                    "error": str(api_error),
                    "tested_at": _utc_now().isoformat(),
                }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to test embedding model: {str(e)}",
        )
