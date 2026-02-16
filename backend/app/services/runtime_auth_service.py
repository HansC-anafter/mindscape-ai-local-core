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

    # Persistent key file path for development environments
    _KEY_FILE = os.path.expanduser("~/.mindscape/encryption.key")

    def __init__(self):
        """Initialize the auth service with encryption key.

        Layered key resolution:
          1. RUNTIME_ENCRYPTION_KEY env var (highest priority)
          2. Persistent file at ~/.mindscape/encryption.key
          3. Auto-generate + persist (development) or fail-fast (production)
        """
        encryption_key = self._resolve_encryption_key()

        try:
            if isinstance(encryption_key, str):
                encryption_key = encryption_key.encode()
            self.cipher = Fernet(encryption_key)
        except Exception as e:
            logger.error(f"Failed to initialize encryption: {e}")
            raise

    @classmethod
    def _resolve_encryption_key(cls) -> str:
        """Resolve encryption key using layered strategy."""
        # Layer 1: environment variable
        key = os.getenv("RUNTIME_ENCRYPTION_KEY")
        if key:
            return key

        # Layer 2: persistent file
        key_path = cls._KEY_FILE
        try:
            if os.path.isfile(key_path):
                with open(key_path, "r") as f:
                    key = f.read().strip()
                if key:
                    logger.info("Encryption key loaded from persistent file")
                    return key
        except OSError as e:
            logger.warning(f"Failed to read encryption key file: {e}")

        # Layer 3: environment-dependent fallback
        is_production = os.getenv("ENVIRONMENT", "development").lower() in (
            "production",
            "staging",
        )
        if is_production:
            raise RuntimeError(
                "RUNTIME_ENCRYPTION_KEY is not set and no persistent key file found. "
                "Generate one with: python -c "
                "'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())' "
                "and add it to your .env file."
            )

        # Development: auto-generate and persist
        new_key = Fernet.generate_key().decode()
        try:
            os.makedirs(os.path.dirname(key_path), exist_ok=True)
            with open(key_path, "w") as f:
                f.write(new_key)
            os.chmod(key_path, 0o600)
            logger.warning(
                f"Auto-generated encryption key persisted to {key_path}. "
                f"Set RUNTIME_ENCRYPTION_KEY env var for production."
            )
        except OSError as e:
            logger.warning(
                f"Could not persist encryption key to {key_path}: {e}. "
                f"Key will be lost on restart."
            )
        return new_key

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

    async def get_auth_headers(
        self,
        runtime: RuntimeEnvironment,
        db=None,
    ) -> Dict[str, str]:
        """
        Get authentication headers for a runtime environment.

        Supports:
        - api_key: Bearer token from encrypted API key
        - oauth2: Bearer token from encrypted token blob with auto-refresh

        Args:
            runtime: RuntimeEnvironment instance
            db: Optional SQLAlchemy session for persisting token refresh

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
            try:
                token_data = self.decrypt_token_blob(runtime.auth_config)
                access_token = token_data.get("access_token")

                # Check if token needs refresh
                if self._is_token_expired(token_data) and token_data.get(
                    "refresh_token"
                ):
                    access_token = await self._refresh_oauth_token(
                        runtime,
                        token_data,
                        db=db,
                    )

                if access_token:
                    headers["Authorization"] = f"Bearer {access_token}"
            except Exception as e:
                logger.error(
                    f"Failed to get OAuth2 token for runtime {runtime.id}: {e}"
                )

        return headers

    def encrypt_token_blob(self, token_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Encrypt entire OAuth token blob (access_token, refresh_token, expiry, identity).

        Args:
            token_data: Plain token data dictionary

        Returns:
            Dictionary with 'token_blob' key containing encrypted JSON
        """
        blob_json = json.dumps(token_data)
        encrypted_blob = self.cipher.encrypt(blob_json.encode()).decode()
        # Preserve non-sensitive fields for display
        result = {"token_blob": encrypted_blob}
        if "identity" in token_data:
            result["identity"] = token_data["identity"]
        return result

    def decrypt_token_blob(self, auth_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Decrypt OAuth token blob back to plain token data.

        Args:
            auth_config: Dictionary containing encrypted 'token_blob'

        Returns:
            Decrypted token data dictionary
        """
        token_blob = auth_config.get("token_blob")
        if not token_blob:
            # Fallback: try legacy field-level decryption
            return self.decrypt_credentials(auth_config)

        try:
            decrypted_json = self.cipher.decrypt(token_blob.encode()).decode()
            return json.loads(decrypted_json)
        except Exception as e:
            logger.error(f"Failed to decrypt token blob: {e}")
            raise

    @staticmethod
    def _is_token_expired(token_data: Dict[str, Any]) -> bool:
        """Check if an OAuth2 access token has expired."""
        import time

        expiry = token_data.get("expiry")
        if not expiry:
            return False
        try:
            return float(expiry) < time.time()
        except (ValueError, TypeError):
            return False

    async def _refresh_oauth_token(
        self,
        runtime: RuntimeEnvironment,
        token_data: Dict[str, Any],
        db=None,
    ) -> Optional[str]:
        """
        Refresh an expired OAuth2 access token.

        For OIDC provider tokens (token_source="oidc"), refreshes against
        the provider's OIDC /token endpoint derived from runtime.config_url.
        For legacy Google tokens, refreshes against Google's token endpoint.

        Args:
            runtime: RuntimeEnvironment instance
            token_data: Decrypted token data
            db: Optional SQLAlchemy session for persistence

        Returns:
            New access token string, or None on failure
        """
        import httpx
        import time

        refresh_token = token_data.get("refresh_token")
        if not refresh_token:
            return None

        token_source = token_data.get("token_source", "google")

        if token_source in ("oidc", "site-hub"):
            # Refresh against cloud provider OIDC token endpoint
            # Priority: runtime config_url > env vars
            provider_base = None
            if runtime and runtime.config_url:
                from urllib.parse import urlparse

                parsed = urlparse(runtime.config_url)
                provider_base = f"{parsed.scheme}://{parsed.netloc}"
            if not provider_base:
                provider_base = os.getenv(
                    "CLOUD_PROVIDER_BASE_URL",
                    os.getenv("CLOUD_PROVIDER_API_URL", ""),
                )

            if not provider_base:
                logger.error(
                    f"Cannot refresh OIDC token for runtime {runtime.id}: "
                    f"no config_url or CLOUD_PROVIDER_BASE_URL set"
                )
                return None

            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(
                        f"{provider_base}/api/v1/oidc/token",
                        data={
                            "grant_type": "refresh_token",
                            "refresh_token": refresh_token,
                            "client_id": "runtime-oauth",
                        },
                    )
                    resp.raise_for_status()
                    new_tokens = resp.json()

                token_data["access_token"] = new_tokens["access_token"]
                if "refresh_token" in new_tokens:
                    token_data["refresh_token"] = new_tokens["refresh_token"]
                token_data["expiry"] = time.time() + new_tokens.get("expires_in", 900)

                runtime.auth_config = self.encrypt_token_blob(token_data)

                if db:
                    try:
                        db.add(runtime)
                        db.commit()
                        logger.info(
                            f"OIDC token refreshed and persisted for runtime {runtime.id}"
                        )
                    except Exception as commit_err:
                        logger.error(f"Failed to persist refreshed token: {commit_err}")
                        db.rollback()
                else:
                    logger.warning(
                        f"OIDC token refreshed for runtime {runtime.id} but no db "
                        f"session provided — changes are in-memory only"
                    )

                return new_tokens["access_token"]

            except Exception as e:
                logger.error(f"OIDC token refresh failed for runtime {runtime.id}: {e}")
                return None

        # Legacy: Refresh against Google's token endpoint
        config = runtime.auth_config or {}
        client_id = config.get("client_id")
        client_secret = config.get("client_secret")

        # Decrypt per-runtime client_secret (stored encrypted)
        if client_secret:
            try:
                decrypted_config = self.decrypt_credentials(config)
                client_secret = decrypted_config.get("client_secret", client_secret)
            except Exception:
                pass  # Use as-is if decryption fails

        # Fallback to System Settings (global settings page)
        if not client_id or not client_secret:
            try:
                from app.services.system_settings_store import SystemSettingsStore

                settings = SystemSettingsStore()
                if not client_id:
                    s = settings.get_setting("google_oauth_client_id")
                    if s and s.value:
                        client_id = str(s.value)
                if not client_secret:
                    s = settings.get_setting("google_oauth_client_secret")
                    if s and s.value:
                        client_secret = str(s.value)
            except Exception:
                pass

        # Fallback to env vars
        if not client_id:
            client_id = os.getenv("GOOGLE_CLIENT_ID")
        if not client_secret:
            client_secret = os.getenv("GOOGLE_CLIENT_SECRET")

        if not client_id or not client_secret:
            logger.error(f"Missing OAuth client credentials for runtime {runtime.id}")
            return None

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    "https://oauth2.googleapis.com/token",
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": refresh_token,
                        "client_id": client_id,
                        "client_secret": client_secret,
                    },
                )
                resp.raise_for_status()
                new_tokens = resp.json()

            # Merge new tokens into existing data
            token_data["access_token"] = new_tokens["access_token"]
            if "refresh_token" in new_tokens:
                token_data["refresh_token"] = new_tokens["refresh_token"]
            token_data["expiry"] = time.time() + new_tokens.get("expires_in", 3600)

            # Re-encrypt and update runtime
            runtime.auth_config = self.encrypt_token_blob(token_data)

            # Persist to database if session available
            if db:
                try:
                    db.add(runtime)
                    db.commit()
                    logger.info(
                        f"OAuth token refreshed and persisted for runtime {runtime.id}"
                    )
                except Exception as commit_err:
                    logger.error(f"Failed to persist refreshed token: {commit_err}")
                    db.rollback()
            else:
                logger.warning(
                    f"OAuth token refreshed for runtime {runtime.id} but no db session "
                    f"provided — changes are in-memory only"
                )

            return new_tokens["access_token"]

        except Exception as e:
            logger.error(f"Failed to refresh OAuth token for runtime {runtime.id}: {e}")
            return None

    def validate_auth_config(
        self, auth_type: str, auth_config: Optional[Dict[str, Any]]
    ) -> bool:
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
            return bool("api_key" in auth_config and auth_config["api_key"])

        if auth_type == "oauth2":
            has_client_creds = (
                "client_id" in auth_config and "client_secret" in auth_config
            )
            has_token = "access_token" in auth_config
            has_blob = "token_blob" in auth_config
            return has_client_creds or has_token or has_blob

        return False
