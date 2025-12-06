"""
LLM Provider Helper
Utility functions for getting LLM provider based on user settings
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def get_provider_name_from_chat_model() -> Optional[str]:
    """
    Get provider name from system chat_model setting

    Returns:
        Provider name (openai, anthropic, vertex-ai) or None if not configured

    Raises:
        ValueError: If chat_model is not configured or cannot determine provider
    """
    from backend.app.services.system_settings_store import SystemSettingsStore
    settings_store = SystemSettingsStore()
    chat_setting = settings_store.get_setting("chat_model")

    if not chat_setting:
        raise ValueError(
            "chat_model not configured in system settings. "
            "Please configure chat_model in Settings."
        )

    # Get provider from model metadata or infer from model name
    provider_name = chat_setting.metadata.get("provider")
    if not provider_name:
        model_name = str(chat_setting.value)
        # Infer provider from model name
        if "gemini" in model_name.lower():
            provider_name = "vertex-ai"
        elif "gpt" in model_name.lower() or "text-" in model_name.lower():
            provider_name = "openai"
        elif "claude" in model_name.lower():
            provider_name = "anthropic"
        else:
            raise ValueError(
                f"Cannot determine LLM provider from model name '{model_name}'. "
                "Please configure provider in chat_model metadata."
            )

    return provider_name


def get_llm_provider_from_settings(llm_manager) -> Optional[object]:
    """
    Get LLM provider from user's chat_model setting

    Args:
        llm_manager: LLMProviderManager instance

    Returns:
        LLMProvider instance

    Raises:
        ValueError: If chat_model is not configured or provider is not available
    """
    provider_name = get_provider_name_from_chat_model()
    provider = llm_manager.get_provider(provider_name)

    if not provider:
        available_providers = llm_manager.get_available_providers()
        from backend.app.services.system_settings_store import SystemSettingsStore
        settings_store = SystemSettingsStore()
        chat_setting = settings_store.get_setting("chat_model")
        model_name = str(chat_setting.value) if chat_setting else "unknown"

        # Provide specific error message based on provider type
        if provider_name == "vertex-ai":
            error_msg = (
                f"Selected provider 'vertex-ai' (from chat_model '{model_name}') is not available. "
                f"Available providers: {', '.join(available_providers) if available_providers else 'none'}. "
                f"Please configure the Service Account JSON and Project ID for 'vertex-ai' in Settings."
            )
        elif provider_name in ["openai", "anthropic"]:
            error_msg = (
                f"Selected provider '{provider_name}' (from chat_model '{model_name}') is not available. "
                f"Available providers: {', '.join(available_providers) if available_providers else 'none'}. "
                f"Please configure the API key for '{provider_name}' in Settings."
            )
        else:
            error_msg = (
                f"Selected provider '{provider_name}' (from chat_model '{model_name}') is not available. "
                f"Available providers: {', '.join(available_providers) if available_providers else 'none'}. "
                f"Please configure the credentials for '{provider_name}' in Settings."
            )
        raise ValueError(error_msg)

    from backend.app.services.system_settings_store import SystemSettingsStore
    settings_store = SystemSettingsStore()
    chat_setting = settings_store.get_setting("chat_model")
    model_name = str(chat_setting.value) if chat_setting else "unknown"
    logger.info(f"Using LLM provider '{provider_name}' (from chat_model '{model_name}')")
    return provider


def get_model_name_from_chat_model() -> Optional[str]:
    """
    Get model name from system chat_model setting

    Returns:
        Model name (e.g., 'gemini-2.5-pro', 'gpt-4o-mini') or None if not configured
    """
    from backend.app.services.system_settings_store import SystemSettingsStore
    settings_store = SystemSettingsStore()
    chat_setting = settings_store.get_setting("chat_model")

    if not chat_setting:
        return None

    return str(chat_setting.value)


def create_llm_provider_manager(
    openai_key: Optional[str] = None,
    anthropic_key: Optional[str] = None,
    vertex_api_key: Optional[str] = None,
    vertex_project_id: Optional[str] = None,
    vertex_location: Optional[str] = None
):
    """
    Create LLMProviderManager with unified configuration from system settings

    This function provides a unified way to create LLMProviderManager across the codebase.
    It reads configuration from system settings first, then falls back to environment variables,
    and finally uses provided parameters.

    Args:
        openai_key: OpenAI API key (optional, will be read from system settings or env if not provided)
        anthropic_key: Anthropic API key (optional, will be read from system settings or env if not provided)
        vertex_api_key: Vertex AI service account JSON or file path (optional)
        vertex_project_id: Vertex AI project ID (optional)
        vertex_location: Vertex AI location (optional, defaults to us-central1)

    Returns:
        LLMProviderManager instance with all available providers configured
    """
    from backend.app.services.agent_runner import LLMProviderManager
    from backend.app.services.system_settings_store import SystemSettingsStore

    settings_store = SystemSettingsStore()

    # Get OpenAI key: parameter > system settings > environment variable
    if not openai_key:
        openai_setting = settings_store.get_setting("openai_api_key")
        openai_key = openai_setting.value if openai_setting else None
    if not openai_key:
        openai_key = os.getenv("OPENAI_API_KEY")

    # Get Anthropic key: parameter > system settings > environment variable
    if not anthropic_key:
        anthropic_setting = settings_store.get_setting("anthropic_api_key")
        anthropic_key = anthropic_setting.value if anthropic_setting else None
    if not anthropic_key:
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")

    # Get Vertex AI config: parameter > system settings > environment variable
    if not vertex_api_key:
        vertex_service_account = settings_store.get_setting("vertex_ai_service_account")
        vertex_api_key = vertex_service_account.value if vertex_service_account else None
    if not vertex_api_key:
        vertex_api_key = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

    if not vertex_project_id:
        vertex_project_setting = settings_store.get_setting("vertex_ai_project_id")
        vertex_project_id = vertex_project_setting.value if vertex_project_setting else None
    if not vertex_project_id:
        vertex_project_id = os.getenv("GOOGLE_CLOUD_PROJECT")

    if not vertex_location:
        vertex_location_setting = settings_store.get_setting("vertex_ai_location")
        vertex_location = vertex_location_setting.value if vertex_location_setting else None
    if not vertex_location:
        vertex_location = os.getenv("VERTEX_LOCATION", "us-central1")

    return LLMProviderManager(
        openai_key=openai_key,
        anthropic_key=anthropic_key,
        vertex_api_key=vertex_api_key,
        vertex_project_id=vertex_project_id,
        vertex_location=vertex_location
    )

