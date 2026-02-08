"""
Chat and Embedding Model Endpoints

Handles chat/embedding model configuration and testing.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any, Optional
from datetime import datetime
import logging

from ..shared import settings_store
from ..constants import DEFAULT_CHAT_MODELS, DEFAULT_EMBEDDING_MODELS
from backend.app.models.system_settings import (
    SystemSetting,
    LLMModelConfig,
    ModelType,
    SettingType,
)

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
        chat_setting = settings_store.get_setting("chat_model")
        embedding_setting = settings_store.get_setting("embedding_model")

        chat_model = None
        if chat_setting:
            chat_model = LLMModelConfig(
                model_name=str(chat_setting.value),
                provider=chat_setting.metadata.get("provider", "openai"),
                model_type=ModelType.CHAT,
                api_key_setting_key=chat_setting.metadata.get("api_key_setting_key"),
                metadata=chat_setting.metadata,
            )

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

        available_chat_models = DEFAULT_CHAT_MODELS
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
        metadata = {"provider": provider, "model_type": "chat"}
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
            metadata=metadata,
        )

        updated = settings_store.save_setting(setting)

        return LLMModelConfig(
            model_name=str(updated.value),
            provider=updated.metadata.get("provider", "openai"),
            model_type=ModelType.CHAT,
            api_key_setting_key=updated.metadata.get("api_key_setting_key"),
            metadata=updated.metadata,
        )
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


@router.post("/llm-models/test-chat", response_model=Dict[str, Any])
async def test_chat_model_connection(
    model_name: Optional[str] = Query(
        None, description="Model name to test (uses current setting if not provided)"
    )
):
    """Test chat model connection"""
    try:
        import os
        from backend.app.services.config_store import ConfigStore

        if not model_name:
            chat_setting = settings_store.get_setting("chat_model")
            if not chat_setting:
                raise HTTPException(status_code=400, detail="No chat model configured")
            model_name = str(chat_setting.value)
            provider = chat_setting.metadata.get("provider", "openai")
        else:
            if model_name.startswith("gpt") or model_name.startswith("text-"):
                provider = "openai"
            elif model_name.startswith("claude"):
                provider = "anthropic"
            else:
                provider = "openai"

        config_store = ConfigStore()
        config = config_store.get_or_create_config("default-user")

        if provider == "openai":
            api_key = config.agent_backend.openai_api_key or os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise HTTPException(
                    status_code=400, detail="OpenAI API key not configured"
                )
        elif provider == "anthropic":
            api_key = config.agent_backend.anthropic_api_key or os.getenv(
                "ANTHROPIC_API_KEY"
            )
            if not api_key:
                raise HTTPException(
                    status_code=400, detail="Anthropic API key not configured"
                )
        else:
            raise HTTPException(
                status_code=400, detail=f"Unsupported provider: {provider}"
            )

        try:
            if provider == "openai":
                import openai

                client = openai.OpenAI(api_key=api_key)
                create_params = {
                    "model": model_name,
                    "messages": [{"role": "user", "content": "Hi"}],
                }
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
                    messages=[{"role": "user", "content": "Hello"}],
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
                "tested_at": datetime.utcnow().isoformat(),
            }
        except Exception as api_error:
            return {
                "success": False,
                "model_name": model_name,
                "provider": provider,
                "message": f"Connection failed: {str(api_error)}",
                "error": str(api_error),
                "tested_at": datetime.utcnow().isoformat(),
            }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to test chat model: {str(e)}"
        )


async def _analyze_embedding_migration_needs(
    previous_model: Dict[str, str], new_model: Dict[str, str]
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
        import psycopg2
        from psycopg2.extras import RealDictCursor
        from app.database.config import get_vector_postgres_config

        pg_config = get_vector_postgres_config()
        pg_config["connect_timeout"] = 5
        conn = psycopg2.connect(**pg_config)
        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("SET statement_timeout = 10000")

            cursor.execute(
                """
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
            """
            )

            historical_models = cursor.fetchall()

            cursor.execute(
                """
                SELECT
                    COUNT(*) as count,
                    MIN(created_at) as first_used,
                    MAX(created_at) as last_used,
                    MAX(updated_at) as last_updated
                FROM mindscape_personal
                WHERE metadata->>'embedding_model' = %s
                  AND metadata->>'embedding_provider' = %s
            """,
                (previous_model["model_name"], previous_model["provider"]),
            )

            previous_model_stats = cursor.fetchone()

            cursor.execute(
                """
                SELECT
                    COUNT(*) as count,
                    MIN(created_at) as first_used,
                    MAX(created_at) as last_used,
                    MAX(updated_at) as last_updated
                FROM mindscape_personal
                WHERE metadata->>'embedding_model' = %s
                  AND metadata->>'embedding_provider' = %s
            """,
                (new_model["model_name"], new_model["provider"]),
            )

            new_model_stats = cursor.fetchone()

            from backend.app.services.embedding_migration_store import (
                EmbeddingMigrationStore,
            )
            from backend.app.models.embedding_migration import MigrationStatus

            migration_store = EmbeddingMigrationStore()
            running_migrations = migration_store.list_migrations(
                status=MigrationStatus.IN_PROGRESS
            )
            pending_migrations = migration_store.list_migrations(
                status=MigrationStatus.PENDING
            )
            active_migrations = running_migrations + pending_migrations

            has_active_migration = any(
                m.source_model == previous_model["model_name"]
                and m.target_model == new_model["model_name"]
                for m in active_migrations
            )

            previous_count = (
                previous_model_stats["count"] if previous_model_stats else 0
            )
            new_count = new_model_stats["count"] if new_model_stats else 0
            needs_migration = (
                previous_count > 0
                and (new_count < previous_count or new_count == 0)
                and not has_active_migration
            )

            migration_info = {
                "needs_migration": needs_migration,
                "has_active_migration": has_active_migration,
                "previous_model": {
                    "model_name": previous_model["model_name"],
                    "provider": previous_model["provider"],
                    "total_embeddings": previous_count,
                    "first_used": (
                        previous_model_stats["first_used"].isoformat()
                        if previous_model_stats and previous_model_stats["first_used"]
                        else None
                    ),
                    "last_used": (
                        previous_model_stats["last_used"].isoformat()
                        if previous_model_stats and previous_model_stats["last_used"]
                        else None
                    ),
                    "last_updated": (
                        previous_model_stats["last_updated"].isoformat()
                        if previous_model_stats and previous_model_stats["last_updated"]
                        else None
                    ),
                },
                "new_model": {
                    "model_name": new_model["model_name"],
                    "provider": new_model["provider"],
                    "existing_embeddings": new_count,
                    "first_used": (
                        new_model_stats["first_used"].isoformat()
                        if new_model_stats and new_model_stats["first_used"]
                        else None
                    ),
                    "last_used": (
                        new_model_stats["last_used"].isoformat()
                        if new_model_stats and new_model_stats["last_used"]
                        else None
                    ),
                },
                "historical_models": [
                    {
                        "model_name": row["model_name"],
                        "provider": row["provider"],
                        "count": row["count"],
                        "first_used": (
                            row["first_used"].isoformat() if row["first_used"] else None
                        ),
                        "last_used": (
                            row["last_used"].isoformat() if row["last_used"] else None
                        ),
                        "last_updated": (
                            row["last_updated"].isoformat()
                            if row["last_updated"]
                            else None
                        ),
                    }
                    for row in historical_models
                ],
                "missing_periods": [],
                "migration_recommendation": None,
            }

            if previous_model_stats and previous_model_stats["count"] > 0:
                if (
                    previous_model_stats["first_used"]
                    and previous_model_stats["last_used"]
                ):
                    migration_info["missing_periods"].append(
                        {
                            "from": previous_model_stats["first_used"].isoformat(),
                            "to": previous_model_stats["last_used"].isoformat(),
                            "model": previous_model["model_name"],
                            "count": previous_model_stats["count"],
                        }
                    )

            if needs_migration:
                if new_count == 0:
                    migration_info["migration_recommendation"] = (
                        "New model has no embeddings. Strongly recommend re-embedding all documents to ensure search accuracy."
                    )
                elif new_count < previous_count:
                    missing_count = previous_count - new_count
                    migration_info["migration_recommendation"] = (
                        f"New model is missing {missing_count:,} embeddings. Recommend re-embedding to fill the gap."
                    )
                else:
                    migration_info["migration_recommendation"] = (
                        "Recommend re-embedding to ensure all vectors are generated with the new model."
                    )
            elif has_active_migration:
                migration_info["migration_recommendation"] = (
                    "Active migration task in progress. Please wait for completion before checking again."
                )
            elif new_count >= previous_count and new_count > 0:
                migration_info["migration_recommendation"] = (
                    "New model has sufficient embeddings. Migration may not be necessary."
                )

            return migration_info

        finally:
            conn.close()

    except Exception as e:
        logger.warning(
            f"Failed to analyze embedding migration needs: {e}", exc_info=True
        )
        return {
            "needs_migration": False,
            "has_active_migration": False,
            "previous_model": {
                "model_name": previous_model["model_name"],
                "provider": previous_model["provider"],
                "total_embeddings": None,
            },
            "new_model": {
                "model_name": new_model["model_name"],
                "provider": new_model["provider"],
                "existing_embeddings": 0,
            },
            "historical_models": [],
            "missing_periods": [],
            "migration_recommendation": f"Unable to query embedding status: {str(e)}. Please check database connection.",
            "error": f"Could not query historical data: {str(e)}",
        }
