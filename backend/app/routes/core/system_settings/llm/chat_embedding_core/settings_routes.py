"""Chat and embedding model setting routes."""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

from backend.app.models.system_settings import (
    LLMModelConfig,
    ModelType,
    SettingType,
    SystemSetting,
)
from backend.app.routes.core.system_settings.constants import (
    DEFAULT_CHAT_MODELS,
    DEFAULT_EMBEDDING_MODELS,
)
from backend.app.routes.core.system_settings.shared import settings_store
from backend.app.services.model_routing_policy_service import ModelRoutingPolicyService

from .migration_analysis import _analyze_embedding_migration_needs

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/llm-models", response_model=Dict[str, Any])
async def get_llm_model_settings(
    include_embedding_status: bool = Query(
        False, description="Include embedding migration status"
    )
):
    """Get LLM model configurations (chat and embedding models)"""
    try:
        routing_service = ModelRoutingPolicyService(settings_store=settings_store)
        chat_payload = routing_service.build_workspace_chat_payload()
        embedding_setting = settings_store.get_setting("embedding_model")

        chat_model = chat_payload.get("chat_model")

        embedding_model = None
        if embedding_setting:
            embedding_model = LLMModelConfig(
                model_name=str(embedding_setting.value),
                provider=embedding_setting.metadata.get("provider", "openai"),
                model_type=ModelType.EMBEDDING,
                api_key_setting_key=embedding_setting.metadata.get(
                    "api_key_setting_key"
                ),
                metadata=embedding_setting.metadata,
            )

        # Return only enabled models (respects user's toggle settings)
        from backend.app.services.model_config_store import ModelConfigStore
        from backend.app.models.model_provider import ModelType as MT

        _store = ModelConfigStore()
        _enabled_chat = _store.get_all_models(model_type=MT.CHAT, enabled=True)
        available_chat_models = (
            chat_payload.get("available_chat_models")
            if _enabled_chat or chat_payload.get("available_chat_models")
            else DEFAULT_CHAT_MODELS
        )
        available_embedding_models = DEFAULT_EMBEDDING_MODELS

        response = {
            "chat_model": chat_model,
            "embedding_model": embedding_model,
            "available_chat_models": available_chat_models,
            "available_embedding_models": available_embedding_models,
        }

        if include_embedding_status and embedding_setting:
            current_model = {
                "model_name": str(embedding_setting.value),
                "provider": embedding_setting.metadata.get("provider", "openai"),
            }
            try:
                migration_info = await _analyze_embedding_migration_needs(
                    previous_model=current_model, new_model=current_model
                )
                if migration_info:
                    migration_info["needs_migration"] = False
                    migration_info["migration_recommendation"] = (
                        "Current model is active. Embedding status is healthy."
                    )
                else:
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
                        "migration_recommendation": "Current model is active. Embedding status is healthy.",
                    }
                response["migration_info"] = migration_info
            except Exception as e:
                logger.warning(
                    f"Failed to get embedding migration status: {e}", exc_info=True
                )
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
                    "error": str(e),
                }

        return response
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get LLM model settings: {str(e)}"
        )

@router.put("/llm-models/chat", response_model=LLMModelConfig)
async def update_chat_model(
    model_name: str,
    provider: str = Query("openai", description="Model provider"),
    api_key_setting_key: Optional[str] = Query(None, description="API key setting key"),
):
    """Update chat/conversation model configuration"""
    try:
        payload = ModelRoutingPolicyService(settings_store=settings_store).update_chat_default(
            model_name=model_name,
            provider=provider,
            api_key_setting_key=api_key_setting_key,
        )
        return payload["chat_model"]
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to update chat model: {str(e)}"
        )

@router.put("/llm-models/embedding", response_model=Dict[str, Any])
async def update_embedding_model(
    model_name: str,
    provider: str = Query("openai", description="Model provider"),
    api_key_setting_key: Optional[str] = Query(None, description="API key setting key"),
):
    """Update embedding model configuration and check if migration is needed"""
    try:
        previous_setting = settings_store.get_setting("embedding_model")
        previous_model = None
        if previous_setting:
            previous_model = {
                "model_name": str(previous_setting.value),
                "provider": previous_setting.metadata.get("provider", "openai"),
            }

        metadata = {"provider": provider, "model_type": "embedding"}
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
            metadata=metadata,
        )

        updated = settings_store.save_setting(setting)

        migration_info = None
        if previous_model and (
            previous_model["model_name"] != model_name
            or previous_model["provider"] != provider
        ):
            migration_info = await _analyze_embedding_migration_needs(
                previous_model=previous_model,
                new_model={"model_name": model_name, "provider": provider},
            )
        else:
            current_model = {"model_name": model_name, "provider": provider}
            migration_info = await _analyze_embedding_migration_needs(
                previous_model=current_model, new_model=current_model
            )
            if migration_info:
                migration_info["needs_migration"] = False
                migration_info["migration_recommendation"] = (
                    "Current model is active. Embedding status is healthy."
                )

        response = {
            "model": LLMModelConfig(
                model_name=str(updated.value),
                provider=updated.metadata.get("provider", "openai"),
                model_type=ModelType.EMBEDDING,
                api_key_setting_key=updated.metadata.get("api_key_setting_key"),
                metadata=updated.metadata,
            )
        }

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
                "migration_recommendation": "Unable to query embedding status. Please check database connection.",
            }

        response["migration_info"] = migration_info

        return response
    except Exception as e:
        logger.error(f"Failed to update embedding model: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to update embedding model: {str(e)}"
        )
