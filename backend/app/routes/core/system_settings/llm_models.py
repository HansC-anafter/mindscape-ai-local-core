"""
Llm Models endpoints
"""
from fastapi import APIRouter, HTTPException, Query, Body
from typing import Dict, Any, List, Optional
import logging

from .shared import settings_store
from .constants import DEFAULT_CHAT_MODELS, DEFAULT_EMBEDDING_MODELS
from backend.app.models.system_settings import (
    SystemSetting,
    SystemSettingsUpdate,
    SystemSettingsResponse,
    LLMModelConfig,
    LLMModelSettingsResponse,
    ModelType,
    SettingType
)

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/llm-models", response_model=Dict[str, Any])
async def get_llm_model_settings(
    include_embedding_status: bool = Query(False, description="Include embedding migration status")
):
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

        # Use module-level default models
        available_chat_models = DEFAULT_CHAT_MODELS
        available_embedding_models = DEFAULT_EMBEDDING_MODELS

        response = {
            "chat_model": chat_model,
            "embedding_model": embedding_model,
            "available_chat_models": available_chat_models,
            "available_embedding_models": available_embedding_models
        }

        # Include embedding migration status if requested
        if include_embedding_status and embedding_setting:
            current_model = {
                "model_name": str(embedding_setting.value),
                "provider": embedding_setting.metadata.get("provider", "openai")
            }
            try:
                migration_info = await _analyze_embedding_migration_needs(
                    previous_model=current_model,
                    new_model=current_model
                )
                if migration_info:
                    migration_info["needs_migration"] = False
                    migration_info["migration_recommendation"] = "Current model is active. Embedding status is healthy."
                else:
                    # Create basic migration_info if analysis returned None
                    migration_info = {
                        "needs_migration": False,
                        "has_active_migration": False,
                        "previous_model": {
                            "model_name": current_model["model_name"],
                            "provider": current_model["provider"],
                            "total_embeddings": None,
                        },
                        "new_model": {
                            "model_name": current_model["model_name"],
                            "provider": current_model["provider"],
                            "existing_embeddings": 0,
                        },
                        "historical_models": [],
                        "missing_periods": [],
                        "migration_recommendation": "Current model is active. Embedding status is healthy."
                    }
                response["migration_info"] = migration_info
            except Exception as e:
                logger.warning(f"Failed to get embedding migration status: {e}", exc_info=True)
                # Return basic migration_info even if analysis fails
                response["migration_info"] = {
                    "needs_migration": False,
                    "has_active_migration": False,
                    "previous_model": {
                        "model_name": current_model["model_name"],
                        "provider": current_model["provider"],
                        "total_embeddings": None,
                    },
                    "new_model": {
                        "model_name": current_model["model_name"],
                        "provider": current_model["provider"],
                        "existing_embeddings": 0,
                    },
                    "historical_models": [],
                    "missing_periods": [],
                    "migration_recommendation": f"Unable to query embedding status: {str(e)}. Please check database connection.",
                    "error": str(e)
                }

        return response
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
        provider_api_key = api_key_setting.value if api_key_setting else None

        if model.provider_name == "vertex-ai":
            service_account_setting = settings_store.get_setting("vertex_ai_service_account_json")
            if service_account_setting and service_account_setting.value:
                api_key_configured = True
                provider_api_key = service_account_setting.value

        base_url = None
        provider_base_url = None
        if model.provider_name == "ollama":
            base_url = "http://localhost:11434"
            ollama_base_url_setting = settings_store.get_setting("ollama_base_url")
            provider_base_url = ollama_base_url_setting.value if ollama_base_url_setting else base_url

        project_id = None
        location = None
        provider_project_id = None
        provider_location = None
        if model.provider_name == "vertex-ai":
            project_id_setting = settings_store.get_setting("vertex_ai_project_id")
            location_setting = settings_store.get_setting("vertex_ai_location")
            provider_project_id = project_id_setting.value if project_id_setting else None
            provider_location = location_setting.value if location_setting else "us-central1"
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
        raise HTTPException(status_code=500, detail=f"Failed to get model config: {str(e)}")


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

        model = model_store.get_model_by_id(model_id)
        if not model:
            raise HTTPException(status_code=404, detail=f"Model with id {model_id} not found")

        is_provider_level = config.get("provider_level", False)

        if "api_key" in config and config["api_key"]:
            api_key_setting_key = f"{model.provider_name}_api_key"
            setting = SystemSetting(
                key=api_key_setting_key,
                value=config["api_key"],
                value_type=SettingType.STRING,
                category="models",
                description=f"API key for {model.provider_name}",
                is_sensitive=True
            )
            settings_store.save_setting(setting)

        if model.provider_name == "ollama" and "base_url" in config:
            setting = SystemSetting(
                key="ollama_base_url",
                value=config.get("base_url", "http://localhost:11434"),
                value_type=SettingType.STRING,
                category="models",
                description="Ollama base URL"
            )
            settings_store.save_setting(setting)

        if model.provider_name == "vertex-ai":
            if "project_id" in config and config["project_id"]:
                setting = SystemSetting(
                    key="vertex_ai_project_id",
                    value=config["project_id"],
                    value_type=SettingType.STRING,
                    category="models",
                    description="GCP Project ID for Vertex AI"
                )
                settings_store.save_setting(setting)
            if "location" in config and config["location"]:
                setting = SystemSetting(
                    key="vertex_ai_location",
                    value=config["location"],
                    value_type=SettingType.STRING,
                    category="models",
                    description="GCP Location/Region for Vertex AI"
                )
                settings_store.save_setting(setting)
            if "api_key" in config and config["api_key"]:
                import json
                try:
                    service_account_data = json.loads(config["api_key"]) if isinstance(config["api_key"], str) else config["api_key"]
                    if isinstance(service_account_data, dict) and service_account_data.get("type") == "service_account":
                        setting = SystemSetting(
                            key="vertex_ai_service_account_json",
                            value=json.dumps(service_account_data),
                            value_type=SettingType.JSON,
                            category="models",
                            description="GCP Service Account JSON for Vertex AI",
                            is_sensitive=True
                        )
                        settings_store.save_setting(setting)
                except (json.JSONDecodeError, TypeError):
                    logger.warning("Invalid service account JSON format for Vertex AI")

        return {"success": True, "message": "Model configuration updated successfully"}
    except Exception as e:
        logger.error(f"Failed to update model config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update model config: {str(e)}")


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

        model = model_store.get_model_by_id(model_id)
        if not model:
            raise HTTPException(status_code=404, detail=f"Model with id {model_id} not found")

        model_name = model.model_name
        provider = model.provider_name
        model_type = model.model_type

        # Get API key or configuration
        config_store = ConfigStore()
        config = config_store.get_or_create_config("default-user")

        # Test based on provider and model type
        if provider == "openai":
            api_key = config.get("openai_api_key") or os.getenv("OPENAI_API_KEY")
            if not api_key:
                return {"success": False, "message": "OpenAI API key not configured"}

            if model_type == "chat":
                # Simple test: try to list models
                try:
                    import openai
                    client = openai.OpenAI(api_key=api_key)
                    client.models.list(limit=1)
                    return {"success": True, "message": "OpenAI chat model connection successful"}
                except Exception as e:
                    return {"success": False, "message": f"OpenAI connection failed: {str(e)}"}
            elif model_type == "embedding":
                try:
                    import openai
                    client = openai.OpenAI(api_key=api_key)
                    # Test embedding with a small text
                    client.embeddings.create(
                        model=model_name,
                        input="test"
                    )
                    return {"success": True, "message": "OpenAI embedding model connection successful"}
                except Exception as e:
                    return {"success": False, "message": f"OpenAI embedding connection failed: {str(e)}"}

        elif provider == "anthropic":
            api_key = config.get("anthropic_api_key") or os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                return {"success": False, "message": "Anthropic API key not configured"}

            if model_type == "chat":
                try:
                    import anthropic
                    client = anthropic.Anthropic(api_key=api_key)
                    client.messages.create(
                        model=model_name,
                        max_tokens=10,
                        messages=[{"role": "user", "content": "test"}]
                    )
                    return {"success": True, "message": "Anthropic chat model connection successful"}
                except Exception as e:
                    return {"success": False, "message": f"Anthropic connection failed: {str(e)}"}

        elif provider == "vertex-ai":
            # Check for service account JSON
            service_account_setting = settings_store.get_setting("vertex_ai_service_account_json")
            project_id_setting = settings_store.get_setting("vertex_ai_project_id")
            location_setting = settings_store.get_setting("vertex_ai_location")

            if not service_account_setting:
                return {"success": False, "message": "Vertex AI service account JSON not configured"}
            if not project_id_setting:
                return {"success": False, "message": "Vertex AI project ID not configured"}
            if not location_setting:
                return {"success": False, "message": "Vertex AI location not configured"}

            try:
                import json
                import google.auth
                from google.oauth2 import service_account
                from google.cloud import aiplatform

                service_account_data = json.loads(service_account_setting.value)
                credentials = service_account.Credentials.from_service_account_info(service_account_data)
                project_id = project_id_setting.value
                location = location_setting.value

                # Initialize Vertex AI
                aiplatform.init(project=project_id, location=location, credentials=credentials)

                if model_type == "chat":
                    from vertexai.generative_models import GenerativeModel
                    model_instance = GenerativeModel(model_name)
                    response = model_instance.generate_content("test")
                    return {"success": True, "message": "Vertex AI chat model connection successful"}
                elif model_type == "embedding":
                    from vertexai.language_models import TextEmbeddingModel
                    model_instance = TextEmbeddingModel.from_pretrained(model_name)
                    embeddings = model_instance.get_embeddings(["test"])
                    return {"success": True, "message": "Vertex AI embedding model connection successful"}
            except Exception as e:
                return {"success": False, "message": f"Vertex AI connection failed: {str(e)}"}

        elif provider == "ollama":
            base_url_setting = settings_store.get_setting("ollama_base_url")
            base_url = base_url_setting.value if base_url_setting else "http://localhost:11434"

            try:
                import requests
                response = requests.get(f"{base_url}/api/tags", timeout=5)
                if response.status_code == 200:
                    return {"success": True, "message": "Ollama connection successful"}
                else:
                    return {"success": False, "message": f"Ollama connection failed: {response.status_code}"}
            except Exception as e:
                return {"success": False, "message": f"Ollama connection failed: {str(e)}"}

        return {"success": False, "message": f"Test not implemented for provider: {provider}"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to test model connection: {e}", exc_info=True)
        return {"success": False, "message": f"Test failed: {str(e)}"}


@router.get("/category/{category}", response_model=List[SystemSetting])

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


async def _analyze_embedding_migration_needs(
    previous_model: Dict[str, str],
    new_model: Dict[str, str]
) -> Optional[Dict[str, Any]]:
    """
    Analyze embedding migration needs by querying historical embedding usage

    Returns detailed information about:
    - Historical models used
    - Last update time for each model
    - Missing time periods in new model
    - Total embeddings count per model
    """
    try:
        import os
        import psycopg2
        from psycopg2.extras import RealDictCursor
        from collections import defaultdict
        from datetime import datetime, timezone

        # Get PostgreSQL config
        pg_config = {
            "host": os.getenv("POSTGRES_HOST", "postgres"),
            "port": int(os.getenv("POSTGRES_PORT", "5432")),
            "database": os.getenv("POSTGRES_DB", "mindscape_vectors"),
            "user": os.getenv("POSTGRES_USER", "mindscape"),
            "password": os.getenv("POSTGRES_PASSWORD", "mindscape_password"),
        }

        # Set connection timeout (5 seconds)
        pg_config["connect_timeout"] = 5
        conn = psycopg2.connect(**pg_config)
        try:
            # Set statement timeout (10 seconds)
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("SET statement_timeout = 10000")  # 10 seconds

            # Query all historical embedding models and their usage
            cursor.execute("""
                SELECT
                    metadata->>'embedding_model' as model_name,
                    metadata->>'embedding_provider' as provider,
                    COUNT(*) as count,
                    MIN(created_at) as first_used,
                    MAX(created_at) as last_used,
                    MAX(updated_at) as last_updated
                FROM mindscape_personal
                WHERE metadata->>'embedding_model' IS NOT NULL
                GROUP BY metadata->>'embedding_model', metadata->>'embedding_provider'
                ORDER BY last_used DESC
            """)

            historical_models = cursor.fetchall()

            # Query embeddings for previous model
            cursor.execute("""
                SELECT
                    COUNT(*) as count,
                    MIN(created_at) as first_used,
                    MAX(created_at) as last_used,
                    MAX(updated_at) as last_updated
                FROM mindscape_personal
                WHERE metadata->>'embedding_model' = %s
                  AND metadata->>'embedding_provider' = %s
            """, (previous_model["model_name"], previous_model["provider"]))

            previous_model_stats = cursor.fetchone()

            # Query embeddings for new model (if any exist)
            cursor.execute("""
                SELECT
                    COUNT(*) as count,
                    MIN(created_at) as first_used,
                    MAX(created_at) as last_used,
                    MAX(updated_at) as last_updated
                FROM mindscape_personal
                WHERE metadata->>'embedding_model' = %s
                  AND metadata->>'embedding_provider' = %s
            """, (new_model["model_name"], new_model["provider"]))

            new_model_stats = cursor.fetchone()

            # Check for active migrations
            from backend.app.services.embedding_migration_store import EmbeddingMigrationStore
            from backend.app.models.embedding_migration import MigrationStatus
            migration_store = EmbeddingMigrationStore()
            running_migrations = migration_store.list_migrations(status=MigrationStatus.IN_PROGRESS)
            pending_migrations = migration_store.list_migrations(status=MigrationStatus.PENDING)
            active_migrations = running_migrations + pending_migrations

            has_active_migration = any(
                m.source_model == previous_model["model_name"] and
                m.target_model == new_model["model_name"]
                for m in active_migrations
            )

            # Determine if migration is needed
            # Migration is needed if:
            # 1. Previous model has embeddings
            # 2. New model doesn't have all the embeddings (or has fewer)
            # 3. No active migration for this model pair
            previous_count = previous_model_stats["count"] if previous_model_stats else 0
            new_count = new_model_stats["count"] if new_model_stats else 0
            needs_migration = (
                previous_count > 0 and
                (new_count < previous_count or new_count == 0) and
                not has_active_migration
            )

            # Build response
            migration_info = {
                "needs_migration": needs_migration,
                "has_active_migration": has_active_migration,
                "previous_model": {
                    "model_name": previous_model["model_name"],
                    "provider": previous_model["provider"],
                    "total_embeddings": previous_count,
                    "first_used": previous_model_stats["first_used"].isoformat() if previous_model_stats and previous_model_stats["first_used"] else None,
                    "last_used": previous_model_stats["last_used"].isoformat() if previous_model_stats and previous_model_stats["last_used"] else None,
                    "last_updated": previous_model_stats["last_updated"].isoformat() if previous_model_stats and previous_model_stats["last_updated"] else None,
                },
                "new_model": {
                    "model_name": new_model["model_name"],
                    "provider": new_model["provider"],
                    "existing_embeddings": new_count,
                    "first_used": new_model_stats["first_used"].isoformat() if new_model_stats and new_model_stats["first_used"] else None,
                    "last_used": new_model_stats["last_used"].isoformat() if new_model_stats and new_model_stats["last_used"] else None,
                },
                "historical_models": [
                    {
                        "model_name": row["model_name"],
                        "provider": row["provider"],
                        "count": row["count"],
                        "first_used": row["first_used"].isoformat() if row["first_used"] else None,
                        "last_used": row["last_used"].isoformat() if row["last_used"] else None,
                        "last_updated": row["last_updated"].isoformat() if row["last_updated"] else None,
                    }
                    for row in historical_models
                ],
                "missing_periods": [],
                "migration_recommendation": None
            }

            # Calculate missing time periods
            if previous_model_stats and previous_model_stats["count"] > 0:
                if previous_model_stats["first_used"] and previous_model_stats["last_used"]:
                    migration_info["missing_periods"].append({
                        "from": previous_model_stats["first_used"].isoformat(),
                        "to": previous_model_stats["last_used"].isoformat(),
                        "model": previous_model["model_name"],
                        "count": previous_model_stats["count"]
                    })

            # Generate migration recommendation
            if needs_migration:
                if new_count == 0:
                    migration_info["migration_recommendation"] = "New model has no embeddings. Strongly recommend re-embedding all documents to ensure search accuracy."
                elif new_count < previous_count:
                    missing_count = previous_count - new_count
                    migration_info["migration_recommendation"] = f"New model is missing {missing_count:,} embeddings. Recommend re-embedding to fill the gap."
                else:
                    migration_info["migration_recommendation"] = "Recommend re-embedding to ensure all vectors are generated with the new model."
            elif has_active_migration:
                migration_info["migration_recommendation"] = "Active migration task in progress. Please wait for completion before checking again."
            elif new_count >= previous_count and new_count > 0:
                migration_info["migration_recommendation"] = "New model has sufficient embeddings. Migration may not be necessary."

            return migration_info

        finally:
            conn.close()

    except Exception as e:
        logger.warning(f"Failed to analyze embedding migration needs: {e}", exc_info=True)
        # Return basic info even if database query fails
        return {
            "needs_migration": False,  # Don't assume migration needed if we can't check
            "has_active_migration": False,
            "previous_model": {
                "model_name": previous_model["model_name"],
                "provider": previous_model["provider"],
                "total_embeddings": None,  # Unknown
            },
            "new_model": {
                "model_name": new_model["model_name"],
                "provider": new_model["provider"],
                "existing_embeddings": 0,  # Unknown
            },
            "historical_models": [],
            "missing_periods": [],
            "migration_recommendation": f"Unable to query embedding status: {str(e)}. Please check database connection.",
            "error": f"Could not query historical data: {str(e)}"
        }


@router.put("/llm-models/embedding", response_model=Dict[str, Any])
async def update_embedding_model(
    model_name: str,
    provider: str = Query("openai", description="Model provider"),
    api_key_setting_key: Optional[str] = Query(None, description="API key setting key")
):
    """Update embedding model configuration and check if migration is needed"""
    try:
        # Get previous model before updating
        previous_setting = settings_store.get_setting("embedding_model")
        previous_model = None
        if previous_setting:
            previous_model = {
                "model_name": str(previous_setting.value),
                "provider": previous_setting.metadata.get("provider", "openai")
            }

        # Update the setting
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

        # Always analyze embedding status (even if model didn't change, show current status)
        migration_info = None
        if previous_model and (previous_model["model_name"] != model_name or previous_model["provider"] != provider):
            # Model changed, analyze migration needs
            migration_info = await _analyze_embedding_migration_needs(
                previous_model=previous_model,
                new_model={"model_name": model_name, "provider": provider}
            )
        else:
            # Model didn't change or no previous model, but still show current embedding status
            # Use current model as both previous and new to get status
            current_model = {"model_name": model_name, "provider": provider}
            migration_info = await _analyze_embedding_migration_needs(
                previous_model=current_model,
                new_model=current_model
            )
            # Since model didn't change, migration is not needed
            if migration_info:
                migration_info["needs_migration"] = False
                migration_info["migration_recommendation"] = "Current model is active. Embedding status is healthy."

        response = {
            "model": LLMModelConfig(
                model_name=str(updated.value),
                provider=updated.metadata.get("provider", "openai"),
                model_type=ModelType.EMBEDDING,
                api_key_setting_key=updated.metadata.get("api_key_setting_key"),
                metadata=updated.metadata
            )
        }

        # Always include migration_info if available (shows embedding status)
        # If migration_info is None (e.g., database error), create a basic one
        if not migration_info:
            migration_info = {
                "needs_migration": False,
                "has_active_migration": False,
                "previous_model": {
                    "model_name": model_name,
                    "provider": provider,
                    "total_embeddings": None,
                },
                "new_model": {
                    "model_name": model_name,
                    "provider": provider,
                    "existing_embeddings": 0,
                },
                "historical_models": [],
                "missing_periods": [],
                "migration_recommendation": "Unable to query embedding status. Please check database connection."
            }

        response["migration_info"] = migration_info

        return response
    except Exception as e:
        logger.error(f"Failed to update embedding model: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update embedding model: {str(e)}")


@router.post("/llm-models/test-chat", response_model=Dict[str, Any])
async def test_chat_model_connection(
    model_name: Optional[str] = Query(None, description="Model name to test (uses current setting if not provided)")
):
    """Test chat model connection"""
    try:
        import os
        from backend.app.services.config_store import ConfigStore

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
async def _analyze_embedding_migration_needs(
    previous_model: Dict[str, str],
    new_model: Dict[str, str]
) -> Optional[Dict[str, Any]]:
    """
    Analyze embedding migration needs by querying historical embedding usage

    Returns detailed information about:
    - Historical models used
    - Last update time for each model
    - Missing time periods in new model
    - Total embeddings count per model
    """
    try:
        import os
        import psycopg2
        from psycopg2.extras import RealDictCursor
        from collections import defaultdict
        from datetime import datetime, timezone

        # Get PostgreSQL config
        pg_config = {
            "host": os.getenv("POSTGRES_HOST", "postgres"),
            "port": int(os.getenv("POSTGRES_PORT", "5432")),
            "database": os.getenv("POSTGRES_DB", "mindscape_vectors"),
            "user": os.getenv("POSTGRES_USER", "mindscape"),
            "password": os.getenv("POSTGRES_PASSWORD", "mindscape_password"),
        }

        # Set connection timeout (5 seconds)
        pg_config["connect_timeout"] = 5
        conn = psycopg2.connect(**pg_config)
        try:
            # Set statement timeout (10 seconds)
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("SET statement_timeout = 10000")  # 10 seconds

            # Query all historical embedding models and their usage
            cursor.execute("""
                SELECT
                    metadata->>'embedding_model' as model_name,
                    metadata->>'embedding_provider' as provider,
                    COUNT(*) as count,
                    MIN(created_at) as first_used,
                    MAX(created_at) as last_used,
                    MAX(updated_at) as last_updated
                FROM mindscape_personal
                WHERE metadata->>'embedding_model' IS NOT NULL
                GROUP BY metadata->>'embedding_model', metadata->>'embedding_provider'
                ORDER BY last_used DESC
            """)

            historical_models = cursor.fetchall()

            # Query embeddings for previous model
            cursor.execute("""
                SELECT
                    COUNT(*) as count,
                    MIN(created_at) as first_used,
                    MAX(created_at) as last_used,
                    MAX(updated_at) as last_updated
                FROM mindscape_personal
                WHERE metadata->>'embedding_model' = %s
                  AND metadata->>'embedding_provider' = %s
            """, (previous_model["model_name"], previous_model["provider"]))

            previous_model_stats = cursor.fetchone()

            # Query embeddings for new model (if any exist)
            cursor.execute("""
                SELECT
                    COUNT(*) as count,
                    MIN(created_at) as first_used,
                    MAX(created_at) as last_used,
                    MAX(updated_at) as last_updated
                FROM mindscape_personal
                WHERE metadata->>'embedding_model' = %s
                  AND metadata->>'embedding_provider' = %s
            """, (new_model["model_name"], new_model["provider"]))

            new_model_stats = cursor.fetchone()

            # Check for active migrations
            from backend.app.services.embedding_migration_store import EmbeddingMigrationStore
            from backend.app.models.embedding_migration import MigrationStatus
            migration_store = EmbeddingMigrationStore()
            running_migrations = migration_store.list_migrations(status=MigrationStatus.IN_PROGRESS)
            pending_migrations = migration_store.list_migrations(status=MigrationStatus.PENDING)
            active_migrations = running_migrations + pending_migrations

            has_active_migration = any(
                m.source_model == previous_model["model_name"] and
                m.target_model == new_model["model_name"]
                for m in active_migrations
            )

            # Determine if migration is needed
            # Migration is needed if:
            # 1. Previous model has embeddings
            # 2. New model doesn't have all the embeddings (or has fewer)
            # 3. No active migration for this model pair
            previous_count = previous_model_stats["count"] if previous_model_stats else 0
            new_count = new_model_stats["count"] if new_model_stats else 0
            needs_migration = (
                previous_count > 0 and
                (new_count < previous_count or new_count == 0) and
                not has_active_migration
            )

            # Build response
            migration_info = {
                "needs_migration": needs_migration,
                "has_active_migration": has_active_migration,
                "previous_model": {
                    "model_name": previous_model["model_name"],
                    "provider": previous_model["provider"],
                    "total_embeddings": previous_count,
                    "first_used": previous_model_stats["first_used"].isoformat() if previous_model_stats and previous_model_stats["first_used"] else None,
                    "last_used": previous_model_stats["last_used"].isoformat() if previous_model_stats and previous_model_stats["last_used"] else None,
                    "last_updated": previous_model_stats["last_updated"].isoformat() if previous_model_stats and previous_model_stats["last_updated"] else None,
                },
                "new_model": {
                    "model_name": new_model["model_name"],
                    "provider": new_model["provider"],
                    "existing_embeddings": new_count,
                    "first_used": new_model_stats["first_used"].isoformat() if new_model_stats and new_model_stats["first_used"] else None,
                    "last_used": new_model_stats["last_used"].isoformat() if new_model_stats and new_model_stats["last_used"] else None,
                },
                "historical_models": [
                    {
                        "model_name": row["model_name"],
                        "provider": row["provider"],
                        "count": row["count"],
                        "first_used": row["first_used"].isoformat() if row["first_used"] else None,
                        "last_used": row["last_used"].isoformat() if row["last_used"] else None,
                        "last_updated": row["last_updated"].isoformat() if row["last_updated"] else None,
                    }
                    for row in historical_models
                ],
                "missing_periods": [],
                "migration_recommendation": None
            }

            # Calculate missing time periods
            if previous_model_stats and previous_model_stats["count"] > 0:
                if previous_model_stats["first_used"] and previous_model_stats["last_used"]:
                    migration_info["missing_periods"].append({
                        "from": previous_model_stats["first_used"].isoformat(),
                        "to": previous_model_stats["last_used"].isoformat(),
                        "model": previous_model["model_name"],
                        "count": previous_model_stats["count"]
                    })

            # Generate migration recommendation
            if needs_migration:
                if new_count == 0:
                    migration_info["migration_recommendation"] = "New model has no embeddings. Strongly recommend re-embedding all documents to ensure search accuracy."
                elif new_count < previous_count:
                    missing_count = previous_count - new_count
                    migration_info["migration_recommendation"] = f"New model is missing {missing_count:,} embeddings. Recommend re-embedding to fill the gap."
                else:
                    migration_info["migration_recommendation"] = "Recommend re-embedding to ensure all vectors are generated with the new model."
            elif has_active_migration:
                migration_info["migration_recommendation"] = "Active migration task in progress. Please wait for completion before checking again."
            elif new_count >= previous_count and new_count > 0:
                migration_info["migration_recommendation"] = "New model has sufficient embeddings. Migration may not be necessary."

            return migration_info

        finally:
            conn.close()

    except Exception as e:
        logger.warning(f"Failed to analyze embedding migration needs: {e}", exc_info=True)
        # Return basic info even if database query fails
        return {
            "needs_migration": False,  # Don't assume migration needed if we can't check
            "has_active_migration": False,
            "previous_model": {
                "model_name": previous_model["model_name"],
                "provider": previous_model["provider"],
                "total_embeddings": None,  # Unknown
            },
            "new_model": {
                "model_name": new_model["model_name"],
                "provider": new_model["provider"],
                "existing_embeddings": 0,  # Unknown
            },
            "historical_models": [],
            "missing_periods": [],
            "migration_recommendation": f"Unable to query embedding status: {str(e)}. Please check database connection.",
            "error": f"Could not query historical data: {str(e)}"
        }


