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

    def get_available_backends(self, profile_id: str = "default-user") -> Dict[str, Dict[str, Any]]:
        """Get information about all available backends"""
        # Get current config to check actual availability
        try:
            config = self.config_store.get_config(profile_id)
            if config:
                # Recreate backends with current config to get accurate availability
                openai_key = config.agent_backend.openai_api_key
                anthropic_key = config.agent_backend.anthropic_api_key
                remote_crs_url = config.agent_backend.remote_crs_url
                remote_crs_token = config.agent_backend.remote_crs_token

                # Create temporary backends with current config
                temp_backends = {
                    "local": LocalLLMBackend(
                        openai_key=openai_key,
                        anthropic_key=anthropic_key
                    ),
                    "http_remote": GenericHTTPBackend(
                        base_url=remote_crs_url,
                        api_token=remote_crs_token
                    ) if remote_crs_url and remote_crs_token else GenericHTTPBackend(),
                }

                return {
                    name: backend.get_backend_info()
                    for name, backend in temp_backends.items()
                }
        except Exception as e:
            logger.warning(f"Failed to get config for available backends check: {e}")

        # Fallback to default backends
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
        import logging
        logger = logging.getLogger(__name__)

        logger.info(f"set_backend_mode called: profile_id={profile_id}, mode={mode}, has_openai_key={bool(openai_api_key)}, has_anthropic_key={bool(anthropic_api_key)}")

        if mode not in self.backends:
            logger.error(f"Invalid mode: {mode}, available: {list(self.backends.keys())}")
            return False

        # If setting local mode, update with API keys
        if mode == "local":
            # Get existing config to preserve API keys if not provided
            from backend.app.models.config import UserConfig, AgentBackendConfig
            existing_config = self.config_store.get_config(profile_id)
            existing_openai_key = existing_config.agent_backend.openai_api_key if existing_config else None
            existing_anthropic_key = existing_config.agent_backend.anthropic_api_key if existing_config else None

            # Use provided keys, or fall back to existing keys, or None (will use env vars)
            final_openai_key = openai_api_key if openai_api_key else existing_openai_key
            final_anthropic_key = anthropic_api_key if anthropic_api_key else existing_anthropic_key

            logger.info(f"Creating LocalLLMBackend: openai_key={'***' if final_openai_key else None}, anthropic_key={'***' if final_anthropic_key else None}")
            self.backends["local"] = LocalLLMBackend(
                openai_key=final_openai_key,
                anthropic_key=final_anthropic_key
            )
            backend = self.backends["local"]
            available = backend.is_available()
            logger.info(f"LocalLLMBackend.is_available() = {available}")
            # Don't check availability - allow setting mode even without keys
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
            if not backend.is_available():
                logger.error(f"Remote backend is not available")
                return False
        else:
            backend = self.backends[mode]

        # Save to database
        try:
            from backend.app.models.config import UserConfig, AgentBackendConfig
            config = self.config_store.get_or_create_config(profile_id)
            logger.info(f"Got config for {profile_id}, current mode: {config.agent_backend.mode}")
            config.agent_backend.mode = mode
            if remote_crs_url:
                config.agent_backend.remote_crs_url = remote_crs_url
            if remote_crs_token:
                config.agent_backend.remote_crs_token = remote_crs_token
            # Only update API keys if provided (preserve existing if not)
            if openai_api_key is not None:
                config.agent_backend.openai_api_key = openai_api_key
                logger.info(f"Updating openai_api_key (length: {len(openai_api_key) if openai_api_key else 0})")
            if anthropic_api_key is not None:
                config.agent_backend.anthropic_api_key = anthropic_api_key
                logger.info(f"Updating anthropic_api_key (length: {len(anthropic_api_key) if anthropic_api_key else 0})")
            logger.info(f"Saving config for {profile_id}")
            self.config_store.save_config(config)
            logger.info(f"Successfully saved config for {profile_id}")
        except Exception as e:
            logger.error(f"Failed to save backend config for {profile_id}: {e}", exc_info=True)
            return False

        return True
