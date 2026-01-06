"""
Runtime Authentication Service

Handles encryption/decryption of runtime credentials and OAuth2 token management.
"""

import json
import logging
from typing import Optional, Dict, Any
from cryptography.fernet import Fernet
import os
from app.models.runtime_environment import RuntimeEnvironment

logger = logging.getLogger(__name__)


class RuntimeAuthService:
    """
    Service for managing runtime authentication credentials.

    Responsibilities:
    - Encrypt/decrypt API keys and secrets
    - Manage OAuth2 tokens
    - Validate authentication configurations
    """

    def __init__(self):
        """Initialize the auth service with encryption key."""
        # Get encryption key from environment or use a default (for development only)
        encryption_key = os.getenv("RUNTIME_ENCRYPTION_KEY")
        if not encryption_key:
            logger.warning("RUNTIME_ENCRYPTION_KEY not set, using default (NOT SECURE FOR PRODUCTION)")
            # Default key for development - MUST be changed in production
            encryption_key = Fernet.generate_key().decode()

        try:
            if isinstance(encryption_key, str):
                encryption_key = encryption_key.encode()
            self.cipher = Fernet(encryption_key)
        except Exception as e:
            logger.error(f"Failed to initialize encryption: {e}")
            raise

    def encrypt_credentials(self, auth_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Encrypt sensitive fields in auth_config.

        Args:
            auth_config: Dictionary containing authentication configuration

        Returns:
            Dictionary with encrypted sensitive fields
        """
        encrypted = auth_config.copy()

        # Encrypt API key if present
        if "api_key" in encrypted and encrypted["api_key"]:
            try:
                encrypted["api_key"] = self.cipher.encrypt(
                    encrypted["api_key"].encode()
                ).decode()
            except Exception as e:
                logger.error(f"Failed to encrypt API key: {e}")
                raise

        # Encrypt client secret if present
        if "client_secret" in encrypted and encrypted["client_secret"]:
            try:
                encrypted["client_secret"] = self.cipher.encrypt(
                    encrypted["client_secret"].encode()
                ).decode()
            except Exception as e:
                logger.error(f"Failed to encrypt client secret: {e}")
                raise

        return encrypted

    def decrypt_credentials(self, auth_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Decrypt sensitive fields in auth_config.

        Args:
            auth_config: Dictionary containing encrypted authentication configuration

        Returns:
            Dictionary with decrypted sensitive fields
        """
        decrypted = auth_config.copy()

        # Decrypt API key if present
        if "api_key" in decrypted and decrypted["api_key"]:
            try:
                decrypted["api_key"] = self.cipher.decrypt(
                    decrypted["api_key"].encode()
                ).decode()
            except Exception as e:
                logger.error(f"Failed to decrypt API key: {e}")
                raise

        # Decrypt client secret if present
        if "client_secret" in decrypted and decrypted["client_secret"]:
            try:
                decrypted["client_secret"] = self.cipher.decrypt(
                    decrypted["client_secret"].encode()
                ).decode()
            except Exception as e:
                logger.error(f"Failed to decrypt client secret: {e}")
                raise

        return decrypted

    def get_auth_headers(self, runtime: RuntimeEnvironment) -> Dict[str, str]:
        """
        Get authentication headers for a runtime environment.

        Args:
            runtime: RuntimeEnvironment instance

        Returns:
            Dictionary of HTTP headers for authentication
        """
        headers = {}

        if runtime.auth_type == "api_key" and runtime.auth_config:
            try:
                decrypted = self.decrypt_credentials(runtime.auth_config)
                api_key = decrypted.get("api_key")
                if api_key:
                    headers["Authorization"] = f"Bearer {api_key}"
            except Exception as e:
                logger.error(f"Failed to get API key for runtime {runtime.id}: {e}")

        elif runtime.auth_type == "oauth2" and runtime.auth_config:
            # TODO: Implement OAuth2 token retrieval/refresh
            # For now, use stored access token
            try:
                decrypted = self.decrypt_credentials(runtime.auth_config)
                access_token = decrypted.get("access_token")
                if access_token:
                    headers["Authorization"] = f"Bearer {access_token}"
            except Exception as e:
                logger.error(f"Failed to get OAuth2 token for runtime {runtime.id}: {e}")

        return headers

    def validate_auth_config(self, auth_type: str, auth_config: Optional[Dict[str, Any]]) -> bool:
        """
        Validate authentication configuration.

        Args:
            auth_type: Type of authentication ("api_key", "oauth2", "none")
            auth_config: Authentication configuration dictionary

        Returns:
            True if valid, False otherwise
        """
        if auth_type == "none":
            return True

        if not auth_config:
            return False

        if auth_type == "api_key":
            return "api_key" in auth_config and auth_config["api_key"]

        if auth_type == "oauth2":
            # OAuth2 requires client_id and client_secret (or access_token)
            has_client_creds = "client_id" in auth_config and "client_secret" in auth_config
            has_token = "access_token" in auth_config
            return has_client_creds or has_token

        return False

