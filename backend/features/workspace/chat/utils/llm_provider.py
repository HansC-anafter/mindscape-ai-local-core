"""
LLM Provider configuration and management utilities
"""

import logging
import os
from typing import Optional, Tuple

from backend.app.services.agent_runner import LLMProviderManager
from backend.app.services.config_store import ConfigStore
from backend.app.services.model_config_store import ModelConfigStore
from backend.app.services.system_settings_store import SystemSettingsStore

logger = logging.getLogger(__name__)


def determine_provider_from_model(model_name: str) -> Optional[str]:
    """
    Determine provider name from model name

    Args:
        model_name: Model name (e.g., "gpt-4", "gemini-pro", "claude-3")

    Returns:
        Provider name or None if cannot determine
    """
    if not model_name:
        return None

    model_lower = model_name.lower()
    if "gemini" in model_lower:
        return "vertex-ai"
    elif "gpt" in model_lower or "o1" in model_lower or "o3" in model_lower:
        return "openai"
    elif "claude" in model_lower:
        return "anthropic"
    return None


def get_provider_name_from_model_config(model_name: str) -> Tuple[Optional[str], Optional[object]]:
    """
    Get provider name from model configuration store

    Args:
        model_name: Model name to look up

    Returns:
        Tuple of (provider_name, model_config)
    """
    if not model_name:
        return None, None

    try:
        model_store = ModelConfigStore()
        from backend.app.models.model_provider import ModelType
        all_models = model_store.get_all_models(model_type=ModelType.CHAT, enabled=True)

        for model in all_models:
            if model.model_name == model_name:
                return model.provider_name, model

        # If not found, try to determine from model name
        if "gemini" in model_name.lower():
            logger.info(f"Model {model_name} not found in config, but detected as Gemini model, using vertex-ai provider")
            return "vertex-ai", None
    except Exception as e:
        logger.warning(f"Failed to get model config for {model_name}: {e}")

    # Fallback: determine from model name
    provider_name = determine_provider_from_model(model_name)
    return provider_name, None


def get_vertex_ai_config(
    settings_store: SystemSettingsStore,
    config_store: ConfigStore,
    profile_id: Optional[str] = None
) -> Tuple[Optional[str], Optional[str], str]:
    """
    Get Vertex AI configuration from system settings and config store

    Args:
        settings_store: System settings store
        config_store: Config store
        profile_id: Optional profile ID for config lookup

    Returns:
        Tuple of (service_account_json, project_id, location)
    """
    # Get from system settings first
    service_account_setting = settings_store.get_setting("vertex_ai_service_account_json")
    vertex_project_setting = settings_store.get_setting("vertex_ai_project_id")
    vertex_location_setting = settings_store.get_setting("vertex_ai_location")

    # Get service account JSON
    vertex_api_key = None
    if service_account_setting and service_account_setting.value:
        val = str(service_account_setting.value).strip()
        vertex_api_key = val if val else None

    if not vertex_api_key:
        config = config_store.get_or_create_config(profile_id or "default-user")
        vertex_api_key = config.agent_backend.vertex_api_key if config.agent_backend.vertex_api_key else None

    if not vertex_api_key:
        vertex_api_key = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

    # Get project ID
    vertex_project_id = None
    if vertex_project_setting and vertex_project_setting.value:
        val = str(vertex_project_setting.value).strip()
        vertex_project_id = val if val else None

    if not vertex_project_id:
        config = config_store.get_or_create_config(profile_id or "default-user")
        vertex_project_id = config.agent_backend.vertex_project_id if config.agent_backend.vertex_project_id else None

    if not vertex_project_id:
        vertex_project_id = os.getenv("GOOGLE_CLOUD_PROJECT")

    # Get location
    vertex_location = None
    if vertex_location_setting and vertex_location_setting.value:
        val = str(vertex_location_setting.value).strip()
        vertex_location = val if val else None

    if not vertex_location:
        config = config_store.get_or_create_config(profile_id or "default-user")
        vertex_location = config.agent_backend.vertex_location if config.agent_backend.vertex_location else None

    if not vertex_location:
        vertex_location = os.getenv("VERTEX_LOCATION", "us-central1")

    return vertex_api_key, vertex_project_id, vertex_location


def get_llm_provider_manager(
    profile_id: Optional[str] = None,
    db_path: Optional[str] = None,
    use_default_user: bool = False
) -> LLMProviderManager:
    """
    Get LLM provider manager with configured API keys

    Args:
        profile_id: Profile ID for config lookup (if None and use_default_user=False, uses "default-user")
        db_path: Optional database path for ConfigStore
        use_default_user: If True, always use "default-user" for config

    Returns:
        Configured LLMProviderManager instance
    """
    config_store = ConfigStore(db_path) if db_path else ConfigStore()
    config_id = "default-user" if use_default_user else (profile_id or "default-user")
    config = config_store.get_or_create_config(config_id)

    settings_store = SystemSettingsStore()

    # Get API keys
    openai_key = config.agent_backend.openai_api_key or os.getenv("OPENAI_API_KEY")
    anthropic_key = config.agent_backend.anthropic_api_key or os.getenv("ANTHROPIC_API_KEY")

    # Get Vertex AI config
    vertex_api_key, vertex_project_id, vertex_location = get_vertex_ai_config(
        settings_store, config_store, config_id
    )

    logger.info(f"Vertex AI config: service_account={'set' if vertex_api_key else 'not set'}, project_id={vertex_project_id}, location={vertex_location}")

    return LLMProviderManager(
        openai_key=openai_key,
        anthropic_key=anthropic_key,
        vertex_api_key=vertex_api_key,
        vertex_project_id=vertex_project_id,
        vertex_location=vertex_location
    )


def get_llm_provider(
    model_name: str,
    llm_provider_manager: Optional[LLMProviderManager] = None,
    profile_id: Optional[str] = None,
    db_path: Optional[str] = None
) -> Tuple[object, str]:
    """
    Get LLM provider instance for given model

    Args:
        model_name: Model name
        llm_provider_manager: Optional pre-configured manager (if None, creates new one)
        profile_id: Profile ID for config lookup
        db_path: Optional database path for ConfigStore

    Returns:
        Tuple of (provider_instance, provider_type_name)

    Raises:
        ValueError: If provider cannot be determined or is not available
    """
    if not model_name:
        raise ValueError("Cannot generate response: chat_model not configured in system settings")

    # Get provider name
    provider_name, model_config = get_provider_name_from_model_config(model_name)

    if not provider_name:
        raise ValueError(
            f"Cannot determine provider for model '{model_name}'. "
            f"Supported models: gemini-*, gpt-*, o1-*, o3-*, claude-*"
        )

    # Get or create provider manager
    if llm_provider_manager is None:
        llm_provider_manager = get_llm_provider_manager(profile_id=profile_id, db_path=db_path)

    # Get provider
    provider = llm_provider_manager.get_provider(provider_name)
    if not provider:
        available = llm_provider_manager.get_available_providers()
        raise ValueError(
            f"Provider '{provider_name}' not available for model '{model_name}'. "
            f"Please check your API configuration. Available providers: {available}"
        )

    provider_type = type(provider).__name__
    logger.info(f"Selected provider type: {provider_type} for model {model_name}")

    return provider, provider_type

