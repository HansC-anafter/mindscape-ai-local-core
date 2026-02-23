"""
LLM Provider Factory

Centralized LLM provider construction from system settings and environment
variables. Eliminates duplication across orchestrator __init__ and
generate_readonly_feedback.
"""

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def build_llm_provider() -> Any:
    """
    Build an LLM provider from system settings with env-var fallbacks.

    Resolution order for each credential:
    1. SystemSettingsStore value (if non-empty)
    2. Environment variable fallback

    Returns:
        LLM provider instance ready for text generation.
    """
    from backend.app.services.system_settings_store import SystemSettingsStore
    from backend.app.shared.llm_provider_helper import (
        create_llm_provider_manager,
        get_llm_provider_from_settings,
    )

    openai_key = os.getenv("OPENAI_API_KEY")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")

    settings_store = SystemSettingsStore()

    vertex_service_account_json = _resolve_setting(
        settings_store,
        "vertex_ai_service_account_json",
        env_fallback="GOOGLE_APPLICATION_CREDENTIALS",
    )
    vertex_project_id = _resolve_setting(
        settings_store,
        "vertex_ai_project_id",
        env_fallback="GOOGLE_CLOUD_PROJECT",
    )
    vertex_location = _resolve_setting(
        settings_store,
        "vertex_ai_location",
        env_fallback="VERTEX_LOCATION",
        default="us-central1",
    )

    logger.info(
        "LLM provider factory: vertex_ai service_account=%s, project_id=%s, location=%s",
        "set" if vertex_service_account_json else "not set",
        vertex_project_id,
        vertex_location,
    )

    llm_manager = create_llm_provider_manager(
        openai_key=openai_key,
        anthropic_key=anthropic_key,
        vertex_api_key=vertex_service_account_json,
        vertex_project_id=vertex_project_id,
        vertex_location=vertex_location,
    )
    return get_llm_provider_from_settings(llm_manager)


def _resolve_setting(
    settings_store,
    setting_key: str,
    env_fallback: str = "",
    default: str = "",
) -> str | None:
    """
    Resolve a system setting with optional env-var fallback.

    Args:
        settings_store: SystemSettingsStore instance.
        setting_key: Setting key to look up.
        env_fallback: Environment variable name to check if setting is empty.
        default: Default value if both setting and env var are empty.

    Returns:
        Resolved value or None.
    """
    setting = settings_store.get_setting(setting_key)
    if setting and setting.value:
        val = str(setting.value).strip()
        if val:
            return val
    if env_fallback:
        env_val = os.getenv(env_fallback, default or "")
        return env_val if env_val else None
    return default or None
