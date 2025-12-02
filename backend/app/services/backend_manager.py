"""
Backend Manager
Manages different agent backends and selects the active one
"""

import os
import logging
from typing import Optional, Dict, Any

from backend.app.services.agent_backend import AgentBackend
from backend.app.services.backends.local_llm_backend import LocalLLMBackend
from backend.app.services.backends.generic_http_backend import GenericHTTPBackend
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.config_store import ConfigStore

logger = logging.getLogger(__name__)


class BackendManager:
    """Manages agent backends and configuration"""

    def __init__(self, store: MindscapeStore = None, config_store: ConfigStore = None):
        self.store = store or MindscapeStore()
        self.config_store = config_store or ConfigStore()

        # Initialize available backends
        self.backends: Dict[str, AgentBackend] = {
            "local": LocalLLMBackend(),
            "http_remote": GenericHTTPBackend(),
        }

    def get_active_backend(self, profile_id: str = "default-user") -> AgentBackend:
        """
        Get the active backend for a profile

        Priority:
        1. User's saved preference (from database)
        2. Environment variable AGENT_BACKEND_MODE
        3. Default to "local"
        """
        # Try to get user preference from database
        mode = None
        remote_crs_url = None
        remote_crs_token = None
        openai_key = None
        anthropic_key = None

        try:
            config = self.config_store.get_config(profile_id)
            if config:
                mode = config.agent_backend.mode
                remote_crs_url = config.agent_backend.remote_crs_url
                remote_crs_token = config.agent_backend.remote_crs_token
                openai_key = config.agent_backend.openai_api_key
                anthropic_key = config.agent_backend.anthropic_api_key
        except Exception as e:
            logger.warning(f"Failed to load backend config: {e}")

        # Fallback to environment variable
        if not mode:
            mode = os.getenv("AGENT_BACKEND_MODE", "local")
            remote_crs_url = os.getenv("REMOTE_AGENT_URL") or os.getenv("REMOTE_CRS_URL")  # 向後兼容
            remote_crs_token = os.getenv("REMOTE_AGENT_TOKEN") or os.getenv("REMOTE_CRS_TOKEN")  # 向後兼容
            openai_key = os.getenv("OPENAI_API_KEY")
            anthropic_key = os.getenv("ANTHROPIC_API_KEY")

        # If local mode with API keys, create backend with keys
        if mode == "local" and (openai_key or anthropic_key):
            self.backends["local"] = LocalLLMBackend(
                openai_key=openai_key,
                anthropic_key=anthropic_key
            )
        # If remote mode with custom credentials, create backend with credentials
        # 向後兼容：remote_crs → http_remote
        elif mode in ("http_remote", "remote_crs") and remote_crs_url and remote_crs_token:
            self.backends["http_remote"] = GenericHTTPBackend(
                base_url=remote_crs_url,
                api_token=remote_crs_token
            )
            # 確保使用統一的 key
            mode = "http_remote"

        # Get backend
        backend = self.backends.get(mode)
        if not backend:
            logger.warning(f"Backend '{mode}' not found, falling back to 'local'")
            backend = self.backends["local"]

        # Check if backend is available
        if not backend.is_available():
            if mode != "local":
                logger.warning(f"Backend '{mode}' not available, falling back to 'local'")
                backend = self.backends["local"]
            else:
                raise Exception("No agent backend available. Please configure at least one LLM provider.")

        return backend

    def get_available_backends(self) -> Dict[str, Dict[str, Any]]:
        """Get information about all available backends"""
        return {
            name: backend.get_backend_info()
            for name, backend in self.backends.items()
        }

    def set_backend_mode(
        self,
        profile_id: str,
        mode: str,
        remote_crs_url: Optional[str] = None,
        remote_crs_token: Optional[str] = None,
        openai_api_key: Optional[str] = None,
        anthropic_api_key: Optional[str] = None
    ) -> bool:
        """
        Set backend mode for a profile

        Returns True if successful, False otherwise
        """
        if mode not in self.backends:
            return False

        # If setting local mode, update with API keys
        if mode == "local":
            # Recreate backend with API keys (from config or env)
            # If keys provided, use them; otherwise backend will use env vars
            self.backends["local"] = LocalLLMBackend(
                openai_key=openai_api_key,
                anthropic_key=anthropic_api_key
            )
        # If setting remote mode, update the backend with new credentials
        # 向後兼容：remote_crs → http_remote
        elif mode in ("http_remote", "remote_crs") and remote_crs_url and remote_crs_token:
            # Recreate backend with new credentials
            self.backends["http_remote"] = GenericHTTPBackend(
                base_url=remote_crs_url,
                api_token=remote_crs_token
            )
            mode = "http_remote"  # 標準化為 http_remote

        backend = self.backends[mode]
        # For local mode, check availability after setting keys
        # For remote mode, check if credentials are provided
        if mode == "local":
            # Local mode is available if backend has at least one provider
            # (either from provided keys or env vars)
            if not backend.is_available():
                return False
        elif mode == "http_remote":
            # Remote mode requires both URL and token
            if not remote_crs_url or not remote_crs_token:
                return False
            if not backend.is_available():
                return False

        # Save to database
        try:
            from backend.app.models.config import UserConfig, AgentBackendConfig
            config = self.config_store.get_or_create_config(profile_id)
            config.agent_backend.mode = mode
            if remote_crs_url:
                config.agent_backend.remote_crs_url = remote_crs_url
            if remote_crs_token:
                config.agent_backend.remote_crs_token = remote_crs_token
            if openai_api_key:
                config.agent_backend.openai_api_key = openai_api_key
            if anthropic_api_key:
                config.agent_backend.anthropic_api_key = anthropic_api_key
            self.config_store.save_config(config)
        except Exception as e:
            logger.error(f"Failed to save backend config: {e}")
            return False

        return True
