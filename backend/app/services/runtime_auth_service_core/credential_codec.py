"""Credential and token blob helpers for RuntimeAuthService."""

import json
import logging
import time
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

LegacyDecrypt = Callable[[Dict[str, Any]], Dict[str, Any]]


def encrypt_credentials(cipher, auth_config: Dict[str, Any]) -> Dict[str, Any]:
    """Encrypt sensitive fields in auth_config."""
    encrypted = auth_config.copy()

    if "api_key" in encrypted and encrypted["api_key"]:
        try:
            encrypted["api_key"] = cipher.encrypt(
                encrypted["api_key"].encode()
            ).decode()
        except Exception as e:
            logger.error(f"Failed to encrypt API key: {e}")
            raise

    if "client_secret" in encrypted and encrypted["client_secret"]:
        try:
            encrypted["client_secret"] = cipher.encrypt(
                encrypted["client_secret"].encode()
            ).decode()
        except Exception as e:
            logger.error(f"Failed to encrypt client secret: {e}")
            raise

    return encrypted


def decrypt_credentials(cipher, auth_config: Dict[str, Any]) -> Dict[str, Any]:
    """Decrypt sensitive fields in auth_config."""
    decrypted = auth_config.copy()

    if "api_key" in decrypted and decrypted["api_key"]:
        try:
            decrypted["api_key"] = cipher.decrypt(
                decrypted["api_key"].encode()
            ).decode()
        except Exception as e:
            logger.error(f"Failed to decrypt API key: {e}")
            raise

    if "client_secret" in decrypted and decrypted["client_secret"]:
        try:
            decrypted["client_secret"] = cipher.decrypt(
                decrypted["client_secret"].encode()
            ).decode()
        except Exception as e:
            logger.error(f"Failed to decrypt client secret: {e}")
            raise

    return decrypted


def encrypt_token_blob(cipher, token_data: Dict[str, Any]) -> Dict[str, Any]:
    """Encrypt an OAuth token blob and preserve display-only fields."""
    blob_json = json.dumps(token_data)
    encrypted_blob = cipher.encrypt(blob_json.encode()).decode()
    result = {"token_blob": encrypted_blob}
    if "identity" in token_data:
        result["identity"] = token_data["identity"]
    return result


def decrypt_token_blob(
    cipher,
    auth_config: Dict[str, Any],
    *,
    legacy_decrypt: LegacyDecrypt,
) -> Dict[str, Any]:
    """Decrypt an OAuth token blob, falling back to legacy field decryption."""
    token_blob = auth_config.get("token_blob")
    if not token_blob:
        return legacy_decrypt(auth_config)

    try:
        decrypted_json = cipher.decrypt(token_blob.encode()).decode()
        return json.loads(decrypted_json)
    except Exception as e:
        logger.error(f"Failed to decrypt token blob: {e}")
        raise


def is_token_expired(token_data: Dict[str, Any], now: Optional[float] = None) -> bool:
    """Check whether an OAuth2 access token is expired."""
    expiry = token_data.get("expiry") or token_data.get("idp_token_expiry")
    if not expiry:
        return False
    if now is None:
        now = time.time()
    try:
        exp_val = float(expiry)
        if exp_val == 0:
            idp_expiry = token_data.get("idp_token_expiry")
            if idp_expiry:
                return float(idp_expiry) < now
            return False
        return exp_val < now
    except (ValueError, TypeError):
        return False


def validate_auth_config(
    auth_type: str, auth_config: Optional[Dict[str, Any]]
) -> bool:
    """Validate authentication configuration."""
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
