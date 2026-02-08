"""
Model Utility Configuration Endpoints

Handles model utility configurations (cost, success rate, latency, etc.).
"""

from fastapi import APIRouter, HTTPException, Query, Body
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/model-utility-configs", response_model=Dict[str, Any])
async def get_model_utility_configs(
    auto_assign: bool = Query(
        False, description="Auto-assign configs for enabled models if not exist"
    )
):
    """
    Get all model utility configurations

    Args:
        auto_assign: Whether to auto-assign configs for enabled models

    Returns:
        Dictionary mapping model_name to utility config
    """
    try:
        from backend.app.services.model_utility_config_store import (
            ModelUtilityConfigStore,
        )

        store = ModelUtilityConfigStore()

        if auto_assign:
            store.auto_assign_configs_for_enabled_models()

        all_configs = store.get_all_configs()

        return {
            "configs": {
                model_name: config.to_dict()
                for model_name, config in all_configs.items()
            },
            "total_count": len(all_configs),
        }
    except Exception as e:
        logger.error(f"Failed to get model utility configs: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to get model utility configs: {str(e)}"
        )


@router.get("/model-utility-configs/{model_name}", response_model=Dict[str, Any])
async def get_model_utility_config(model_name: str):
    """
    Get utility configuration for a specific model

    Args:
        model_name: Model name

    Returns:
        Model utility configuration
    """
    try:
        from backend.app.services.model_utility_config_store import (
            ModelUtilityConfigStore,
        )

        store = ModelUtilityConfigStore()
        config = store.get_model_config(model_name)

        if not config:
            raise HTTPException(
                status_code=404,
                detail=f"Utility config not found for model: {model_name}",
            )

        return config.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get model utility config: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to get model utility config: {str(e)}"
        )


@router.put("/model-utility-configs/{model_name}", response_model=Dict[str, Any])
async def update_model_utility_config(
    model_name: str, config: Dict[str, Any] = Body(...)
):
    """
    Update utility configuration for a model

    Args:
        model_name: Model name
        config: Configuration data (cost_per_1m_tokens, success_rate, latency_ms, etc.)

    Returns:
        Updated configuration
    """
    try:
        from backend.app.services.model_utility_config_store import (
            ModelUtilityConfigStore,
            ModelUtilityConfig,
        )

        store = ModelUtilityConfigStore()

        existing_config = store.get_model_config(model_name)
        if existing_config:
            updated_config = ModelUtilityConfig(
                model_name=model_name,
                provider=config.get("provider", existing_config.provider),
                cost_per_1m_tokens=config.get(
                    "cost_per_1m_tokens", existing_config.cost_per_1m_tokens
                ),
                success_rate=config.get("success_rate", existing_config.success_rate),
                latency_ms=config.get("latency_ms", existing_config.latency_ms),
                enabled=config.get("enabled", existing_config.enabled),
                metadata=config.get("metadata", existing_config.metadata),
            )
        else:
            updated_config = ModelUtilityConfig.from_dict(
                {
                    "model_name": model_name,
                    "provider": config.get("provider", "unknown"),
                    "cost_per_1m_tokens": config.get("cost_per_1m_tokens", 1.0),
                    "success_rate": config.get("success_rate", 0.85),
                    "latency_ms": config.get("latency_ms"),
                    "enabled": config.get("enabled", True),
                    "metadata": config.get("metadata"),
                }
            )

        store.save_model_config(updated_config)

        return {"status": "success", "config": updated_config.to_dict()}
    except Exception as e:
        logger.error(f"Failed to update model utility config: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to update model utility config: {str(e)}"
        )


@router.post("/model-utility-configs/auto-assign", response_model=Dict[str, Any])
async def auto_assign_model_utility_configs():
    """
    Automatically assign utility configurations for all enabled models

    Returns:
        Dictionary of assigned configurations
    """
    try:
        from backend.app.services.model_utility_config_store import (
            ModelUtilityConfigStore,
        )

        store = ModelUtilityConfigStore()
        assigned_configs = store.auto_assign_configs_for_enabled_models()

        return {
            "status": "success",
            "assigned_count": len(assigned_configs),
            "configs": {
                model_name: config.to_dict()
                for model_name, config in assigned_configs.items()
            },
        }
    except Exception as e:
        logger.error(f"Failed to auto-assign model utility configs: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to auto-assign model utility configs: {str(e)}",
        )
