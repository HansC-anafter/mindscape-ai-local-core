"""OAuth token refresh helper for RuntimeAuthService."""

import logging
import os
import time
from typing import Any, Callable, Dict, Optional
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

EncryptTokenBlob = Callable[[Dict[str, Any]], Dict[str, Any]]
CommitRuntimeRegistration = Callable[[Any, Any], None]


async def refresh_oauth_token(
    runtime,
    token_data: Dict[str, Any],
    *,
    db=None,
    encrypt_token_blob: EncryptTokenBlob,
    commit_runtime_registration: CommitRuntimeRegistration,
) -> Optional[str]:
    """Refresh an expired OAuth2 access token through the existing runtime path."""
    refresh_token = token_data.get("refresh_token")
    if not refresh_token:
        return None

    token_source = token_data.get("token_source", "google")

    if token_source in ("oidc", "site-hub"):
        provider_base = None
        if runtime and runtime.config_url:
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

            runtime.auth_config = encrypt_token_blob(token_data)

            if db:
                try:
                    commit_runtime_registration(db, runtime)
                    logger.info(
                        f"OIDC token refreshed and persisted for runtime {runtime.id}"
                    )
                except Exception as commit_err:
                    logger.error(f"Failed to persist refreshed token: {commit_err}")
                    db.rollback()
            else:
                logger.warning(
                    f"OIDC token refreshed for runtime {runtime.id} but no db "
                    f"session provided - changes are in-memory only"
                )

            return new_tokens["access_token"]

        except Exception as e:
            logger.error(f"OIDC token refresh failed for runtime {runtime.id}: {e}")
            return None

    from app.routes.core.gca_constants import (
        get_gca_client_id,
        get_gca_client_secret,
    )

    client_id = get_gca_client_id()
    client_secret = get_gca_client_secret()

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

        token_data["access_token"] = new_tokens["access_token"]
        if "refresh_token" in new_tokens:
            token_data["refresh_token"] = new_tokens["refresh_token"]
        token_data["expiry"] = time.time() + new_tokens.get("expires_in", 3600)

        runtime.auth_config = encrypt_token_blob(token_data)

        if db:
            try:
                commit_runtime_registration(db, runtime)
                logger.info(
                    f"OAuth token refreshed and persisted for runtime {runtime.id}"
                )
            except Exception as commit_err:
                logger.error(f"Failed to persist refreshed token: {commit_err}")
                db.rollback()
        else:
            logger.warning(
                f"OAuth token refreshed for runtime {runtime.id} but no db session "
                f"provided - changes are in-memory only"
            )

        return new_tokens["access_token"]

    except Exception as e:
        logger.error(f"Failed to refresh OAuth token for runtime {runtime.id}: {e}")
        return None
