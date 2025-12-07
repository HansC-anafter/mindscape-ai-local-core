"""
LLM Provider Manager
Handles LLM provider initialization and management
"""

import logging
from typing import Optional, Any

from backend.app.services.agent_runner import LLMProviderManager, LLMProvider

logger = logging.getLogger(__name__)


class PlaybookLLMProviderManager:
    """Manages LLM providers for Playbook execution"""

    def __init__(self, config_store: Any):
        self.config_store = config_store

    def get_llm_manager(self, profile_id: str) -> LLMProviderManager:
        """Get LLM manager with profile-specific API keys"""
        from backend.app.shared.llm_provider_helper import create_llm_provider_manager

        # Get user config (for profile-specific overrides)
        config = self.config_store.get_or_create_config(profile_id)

        # Use user-configured keys if available, otherwise use unified function
        openai_key = config.agent_backend.openai_api_key
        anthropic_key = config.agent_backend.anthropic_api_key
        vertex_api_key = config.agent_backend.vertex_api_key
        vertex_project_id = config.agent_backend.vertex_project_id
        vertex_location = config.agent_backend.vertex_location

        # Use unified function with user config as overrides
        return create_llm_provider_manager(
            openai_key=openai_key,
            anthropic_key=anthropic_key,
            vertex_api_key=vertex_api_key,
            vertex_project_id=vertex_project_id,
            vertex_location=vertex_location
        )

    def get_llm_provider(self, llm_manager: LLMProviderManager) -> LLMProvider:
        """
        Get LLM provider based on user's chat_model setting

        Args:
            llm_manager: LLMProviderManager instance

        Returns:
            LLMProvider instance

        Raises:
            ValueError: If chat_model is not configured or specified provider is not available
        """
        from backend.app.shared.llm_provider_helper import get_llm_provider_from_settings
        return get_llm_provider_from_settings(llm_manager)

    def get_model_name(self) -> Optional[str]:
        """Get model name from system settings"""
        from backend.app.shared.llm_provider_helper import get_model_name_from_chat_model
        return get_model_name_from_chat_model()

