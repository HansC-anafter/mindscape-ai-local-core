"""
LLM Provider Helper
Utility functions for getting LLM provider based on user settings
"""

import logging
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

        raise ValueError(
            f"Selected provider '{provider_name}' (from chat_model '{model_name}') is not available. "
            f"Available providers: {', '.join(available_providers) if available_providers else 'none'}. "
            f"Please configure the API key for '{provider_name}' in Settings."
        )

    from backend.app.services.system_settings_store import SystemSettingsStore
    settings_store = SystemSettingsStore()
    chat_setting = settings_store.get_setting("chat_model")
    model_name = str(chat_setting.value) if chat_setting else "unknown"
    logger.info(f"Using LLM provider '{provider_name}' (from chat_model '{model_name}')")
    return provider

