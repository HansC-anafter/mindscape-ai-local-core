"""
LLM Provider Manager - Manages multiple LLM providers with configuration
"""

import os
from typing import Dict, List, Optional
import logging

from .base import LLMProvider
from .openai import OpenAIProvider
from .anthropic import AnthropicProvider
from .vertex import VertexAIProvider
from .ollama import OllamaProvider
from .llama_cpp import LlamaCppProvider

logger = logging.getLogger(__name__)


class LLMProviderManager:
    """Manages multiple LLM providers with fallback"""

    def __init__(
        self,
        openai_key: Optional[str] = None,
        anthropic_key: Optional[str] = None,
        vertex_api_key: Optional[str] = None,
        vertex_project_id: Optional[str] = None,
        vertex_location: Optional[str] = None,
        llama_model_path: Optional[str] = None,
        ollama_base_url: Optional[str] = None,
    ):
        self.providers: Dict[str, LLMProvider] = {}
        self._init_providers(
            openai_key=openai_key,
            anthropic_key=anthropic_key,
            vertex_api_key=vertex_api_key,
            vertex_project_id=vertex_project_id,
            vertex_location=vertex_location,
            llama_model_path=llama_model_path,
            ollama_base_url=ollama_base_url,
        )

    def _init_providers(
        self,
        openai_key: Optional[str] = None,
        anthropic_key: Optional[str] = None,
        vertex_api_key: Optional[str] = None,
        vertex_project_id: Optional[str] = None,
        vertex_location: Optional[str] = None,
        llama_model_path: Optional[str] = None,
        ollama_base_url: Optional[str] = None,
    ):
        """Initialize available providers"""
        # Use provided keys or fallback to environment variables
        openai_key = openai_key or os.getenv("OPENAI_API_KEY")
        if openai_key:
            self.providers["openai"] = OpenAIProvider(openai_key)

        anthropic_key = anthropic_key or os.getenv("ANTHROPIC_API_KEY")
        if anthropic_key:
            self.providers["anthropic"] = AnthropicProvider(anthropic_key)

        # Vertex AI configuration (uses Service Account JSON, not API key)
        vertex_service_account = vertex_api_key or os.getenv(
            "GOOGLE_APPLICATION_CREDENTIALS"
        )
        vertex_project_id = vertex_project_id or os.getenv("GOOGLE_CLOUD_PROJECT")
        vertex_location = vertex_location or os.getenv("VERTEX_LOCATION", "us-central1")

        logger.info(
            f"Vertex AI config check: service_account={'set' if vertex_service_account else 'not set'}, project_id={'set' if vertex_project_id else 'not set'}, location={vertex_location}"
        )

        if vertex_service_account and vertex_project_id:
            try:
                self.providers["vertex-ai"] = VertexAIProvider(
                    api_key=vertex_service_account,
                    project_id=vertex_project_id,
                    location=vertex_location,
                )
                logger.info("Vertex AI provider initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize Vertex AI provider: {e}")
        else:
            logger.warning(
                f"Vertex AI provider not initialized: service_account={'set' if vertex_service_account else 'missing'}, project_id={'set' if vertex_project_id else 'missing'}"
            )

        # Ollama Provider (Recommended Local)
        ollama_base_url = ollama_base_url or os.getenv(
            "OLLAMA_BASE_URL", "http://localhost:11434"
        )
        # Always initialize Ollama as it is the default local strategy
        self.providers["ollama"] = OllamaProvider(base_url=ollama_base_url)
        logger.info(f"Ollama provider initialized with {ollama_base_url}")

        # Local Llama GGUF (Fallback for Local Preview)
        llama_model_path = llama_model_path or os.getenv("LLAMA_MODEL_PATH")
        if llama_model_path and os.path.exists(llama_model_path):
            self.providers["llama-cpp"] = LlamaCppProvider(llama_model_path)
            logger.info(f"LlamaCpp provider initialized with {llama_model_path}")
        else:
            logger.debug(
                "LlamaCpp provider not initialized (model path missing or invalid)"
            )

    def get_provider(
        self, provider_name: Optional[str] = None
    ) -> Optional[LLMProvider]:
        """
        Get LLM provider by name

        Args:
            provider_name: Provider name (required, no fallback)

        Returns:
            LLMProvider instance or None if not found

        Raises:
            ValueError: If provider_name is not specified
        """
        if not provider_name:
            raise ValueError(
                "provider_name is required. Cannot use fallback to first available provider. "
                "Please specify the provider name explicitly."
            )

        if not self.providers:
            return None

        if provider_name in self.providers:
            return self.providers[provider_name]

        return None

    def get_available_providers(self) -> List[str]:
        """Get list of available providers"""
        return list(self.providers.keys())
