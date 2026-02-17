"""
CLI Token Endpoint

Provides a fresh OAuth access_token for CLI bridge processes.
Uses RuntimeAuthService auto-refresh to return a valid token
from the connected OAuth runtime in the database.
"""

import logging
import time

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ...models.runtime_environment import RuntimeEnvironment
from ...services.runtime_auth_service import RuntimeAuthService

try:
    from ...database.session import get_db_postgres as get_db
except ImportError:
    try:
        from ...database import get_db_postgres as get_db
    except ImportError:
        from mindscape.di.providers import get_db_session as get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

_auth_service = RuntimeAuthService()


@router.get("/cli-token")
async def get_cli_token(db: Session = Depends(get_db)):
    """
    Return a fresh IDP access_token for CLI agent authentication.

    Looks up the first connected OAuth runtime, extracts the raw IDP
    access_token (e.g. Google ya29.xxx), auto-refreshes if expired,
    and returns it for injection into CLI env vars.
    No user auth required (called from local bridge process).
    """
    try:
        runtime = (
            db.query(RuntimeEnvironment)
            .filter(
                RuntimeEnvironment.auth_type == "oauth2",
                RuntimeEnvironment.auth_status == "connected",
            )
            .first()
        )

        if not runtime or not runtime.auth_config:
            return JSONResponse(
                status_code=200,
                content={"access_token": None, "error": "no_connected_runtime"},
            )

        # Decrypt token blob
        token_data = _auth_service.decrypt_token_blob(runtime.auth_config)

        # CLI needs raw IDP token (e.g. Google access_token),
        # not the provider's RS256 JWT
        idp_token = token_data.get("idp_access_token")
        idp_expiry = token_data.get("idp_token_expiry", 0)

        # Auto-refresh IDP token if expired
        if idp_token and idp_expiry < time.time():
            idp_refresh = token_data.get("idp_refresh_token")
            if idp_refresh:
                logger.info("IDP token expired, refreshing against IDP endpoint")
                idp_token = await _refresh_idp_token(runtime, token_data, db=db)

        if not idp_token:
            return JSONResponse(
                status_code=200,
                content={
                    "access_token": None,
                    "error": "no_idp_token",
                    "detail": "Re-authenticate runtime to obtain IDP tokens",
                },
            )

        # Compute remaining TTL from IDP expiry
        idp_expiry = token_data.get("idp_token_expiry", 0)
        expires_in = max(0, int(float(idp_expiry) - time.time()))
        if expires_in == 0:
            expires_in = 3600  # Fallback if expiry unknown

        return {
            "access_token": idp_token,
            "expires_in": expires_in,
        }

    except Exception as e:
        logger.error(f"Failed to retrieve CLI token: {e}")
        return JSONResponse(
            status_code=200,
            content={"access_token": None, "error": f"{type(e).__name__}: {e}"},
        )


async def _refresh_idp_token(runtime, token_data, db=None):
    """
    Refresh the raw IDP access_token using IDP refresh_token.

    Uses google_oauth_client_id/secret from system_settings to refresh
    against Google's token endpoint. Returns new access_token or None.
    """
    import httpx

    idp_refresh = token_data.get("idp_refresh_token")
    if not idp_refresh:
        return None

    # Get Google OAuth credentials from system settings
    try:
        from ...services.system_settings_store import SystemSettingsStore

        settings = SystemSettingsStore()
        client_id_setting = settings.get_setting("google_oauth_client_id")
        client_secret_setting = settings.get_setting("google_oauth_client_secret")

        if not (
            client_id_setting
            and client_id_setting.value
            and client_secret_setting
            and client_secret_setting.value
        ):
            logger.error("Missing google_oauth_client_id/secret in system_settings")
            return None

        client_id = str(client_id_setting.value)
        client_secret = str(client_secret_setting.value)
    except Exception as e:
        logger.error(f"Failed to load OAuth credentials from system_settings: {e}")
        return None

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": idp_refresh,
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
            )
            resp.raise_for_status()
            new_tokens = resp.json()

        token_data["idp_access_token"] = new_tokens["access_token"]
        token_data["idp_token_expiry"] = time.time() + new_tokens.get(
            "expires_in", 3600
        )

        # Persist updated token data
        runtime.auth_config = _auth_service.encrypt_token_blob(token_data)
        if db:
            try:
                db.add(runtime)
                db.commit()
                logger.info(
                    "IDP token refreshed and persisted for runtime %s", runtime.id
                )
            except Exception as commit_err:
                logger.error(f"Failed to persist refreshed IDP token: {commit_err}")
                db.rollback()

        return new_tokens["access_token"]

    except Exception as e:
        logger.error(f"IDP token refresh failed: {e}")
        return None
