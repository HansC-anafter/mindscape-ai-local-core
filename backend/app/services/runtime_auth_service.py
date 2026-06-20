"""
Runtime Authentication Service

Handles encryption/decryption of runtime credentials and OAuth2 token management.
"""

import logging
from typing import Optional, Dict, Any
from cryptography.fernet import Fernet
import os
from app.models.runtime_environment import RuntimeEnvironment
from app.services.runtime_route_registration import sync_runtime_registration_metadata
from app.services.runtime_auth_service_core.credential_codec import (
    decrypt_credentials as decrypt_credentials_payload,
    decrypt_token_blob as decrypt_token_blob_payload,
    encrypt_credentials as encrypt_credentials_payload,
    encrypt_token_blob as encrypt_token_blob_payload,
    is_token_expired,
    validate_auth_config as validate_auth_config_payload,
)
from app.services.runtime_auth_service_core.key_resolution import (
    resolve_encryption_key,
)
from app.services.runtime_auth_service_core.token_refresh import refresh_oauth_token

logger = logging.getLogger(__name__)


def _commit_runtime_registration(db, runtime: RuntimeEnvironment) -> None:
    """Persist runtime auth changes through the canonical registration contract."""
    if db is None:
        return
    try:
        sync_runtime_registration_metadata(runtime)
        db.add(runtime)
        db.commit()
    except Exception:
        db.rollback()
        raise


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
        return resolve_encryption_key(cls._KEY_FILE)

    def encrypt_credentials(self, auth_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Encrypt sensitive fields in auth_config.

        Args:
            auth_config: Dictionary containing authentication configuration

        Returns:
            Dictionary with encrypted sensitive fields
        """
        return encrypt_credentials_payload(self.cipher, auth_config)

    def decrypt_credentials(self, auth_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Decrypt sensitive fields in auth_config.

        Args:
            auth_config: Dictionary containing encrypted authentication configuration

        Returns:
            Dictionary with decrypted sensitive fields
        """
        return decrypt_credentials_payload(self.cipher, auth_config)

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

                # Normalize token fields: GCA direct flow uses idp_ prefix
                access_token = token_data.get("access_token") or token_data.get(
                    "idp_access_token"
                )
                refresh_token = token_data.get("refresh_token") or token_data.get(
                    "idp_refresh_token"
                )

                # Check if token needs refresh
                if self._is_token_expired(token_data):
                    if refresh_token:
                        # Ensure _refresh_oauth_token can find the refresh token
                        if not token_data.get("refresh_token") and token_data.get(
                            "idp_refresh_token"
                        ):
                            token_data["refresh_token"] = token_data[
                                "idp_refresh_token"
                            ]
                        refreshed = await self._refresh_oauth_token(
                            runtime,
                            token_data,
                            db=db,
                        )
                        if refreshed:
                            access_token = refreshed
                            # Restore auth_status after successful refresh
                            if runtime.auth_status != "connected":
                                runtime.auth_status = "connected"
                                if db:
                                    try:
                                        _commit_runtime_registration(db, runtime)
                                        logger.info(
                                            f"Restored auth_status to 'connected' for runtime {runtime.id}"
                                        )
                                    except Exception:
                                        logger.exception(
                                            "Failed to persist connected auth_status for runtime %s",
                                            runtime.id,
                                        )
                        else:
                            # Refresh failed; mark runtime as expired
                            logger.warning(
                                f"OAuth token expired and refresh failed for runtime {runtime.id}. "
                                f"Marking auth_status as 'expired'."
                            )
                            access_token = None
                            runtime.auth_status = "expired"
                            if db:
                                try:
                                    _commit_runtime_registration(db, runtime)
                                except Exception:
                                    logger.exception(
                                        "Failed to persist expired auth_status for runtime %s",
                                        runtime.id,
                                    )
                    else:
                        # Expired but no refresh_token; cannot recover
                        logger.warning(
                            f"OAuth token expired for runtime {runtime.id} and no refresh_token available. "
                            f"User must re-authenticate."
                        )
                        access_token = None
                        runtime.auth_status = "expired"
                        if db:
                            try:
                                _commit_runtime_registration(db, runtime)
                            except Exception:
                                logger.exception(
                                    "Failed to persist expired auth_status for runtime %s",
                                    runtime.id,
                                )

                if access_token:
                    headers["Authorization"] = f"Bearer {access_token}"
                else:
                    logger.warning(
                        f"No valid OAuth2 token for runtime {runtime.id}. "
                        f"Auth headers will be empty - expect 401."
                    )
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
        return encrypt_token_blob_payload(self.cipher, token_data)

    def decrypt_token_blob(self, auth_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Decrypt OAuth token blob back to plain token data.

        Args:
            auth_config: Dictionary containing encrypted 'token_blob'

        Returns:
            Decrypted token data dictionary
        """
        return decrypt_token_blob_payload(
            self.cipher,
            auth_config,
            legacy_decrypt=self.decrypt_credentials,
        )

    @staticmethod
    def _is_token_expired(token_data: Dict[str, Any]) -> bool:
        """Check if an OAuth2 access token has expired.

        Checks both standard 'expiry' and GCA-style 'idp_token_expiry' fields.
        """
        return is_token_expired(token_data)

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
        return await refresh_oauth_token(
            runtime,
            token_data,
            db=db,
            encrypt_token_blob=self.encrypt_token_blob,
            commit_runtime_registration=_commit_runtime_registration,
        )

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
        return validate_auth_config_payload(auth_type, auth_config)
