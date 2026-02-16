"""
Runtime OAuth Routes

OAuth2 authorization flow for external runtime environments.
Supports Google OAuth with per-runtime credential override.
"""

import os
import time
import secrets
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session

from ...models.runtime_environment import RuntimeEnvironment
from ...services.runtime_auth_service import RuntimeAuthService

# Import database session
try:
    from ...database.session import get_db_postgres as get_db
except ImportError:
    try:
        from ...database import get_db_postgres as get_db
    except ImportError:
        from mindscape.di.providers import get_db_session as get_db

# Import auth dependencies
try:
    from ...auth import get_current_user
    from ...models.user import User
except ImportError:
    from fastapi import Depends
    from typing import Any

    async def get_current_user() -> Any:
        """Placeholder for development"""
        return type("User", (), {"id": "dev-user"})()

    User = Any

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/runtime-oauth", tags=["runtime-oauth"])

auth_service = RuntimeAuthService()

# In-memory state store for CSRF protection (keyed by state token)
_pending_states: dict = {}


def _get_oauth_credentials(
    runtime: Optional[RuntimeEnvironment] = None,
) -> tuple:
    """
    Resolve OAuth client credentials using three-layer hybrid strategy:
      1. Per-runtime override (runtime.auth_config.client_id/client_secret)
      2. System Settings (global settings page: google_oauth_client_id/secret)
      3. Environment variable fallback (GOOGLE_CLIENT_ID/SECRET)

    Returns:
        (client_id, client_secret, redirect_uri)

    Raises:
        HTTPException 500 if credentials are not configured at any layer
    """
    config = (runtime.auth_config or {}) if runtime else {}

    # Layer 1: per-runtime override (may be encrypted)
    client_id = config.get("client_id")
    client_secret = config.get("client_secret")
    redirect_uri = None

    # Decrypt per-runtime client_secret if it was encrypted at storage time
    if client_secret and runtime:
        try:
            decrypted_config = auth_service.decrypt_credentials(config)
            client_secret = decrypted_config.get("client_secret", client_secret)
        except Exception as e:
            logger.warning(f"Failed to decrypt per-runtime client_secret: {e}")

    # Layer 2: System Settings (global settings page)
    if not client_id or not client_secret:
        try:
            from ...services.system_settings_store import SystemSettingsStore

            settings_store_instance = SystemSettingsStore()

            if not client_id:
                setting = settings_store_instance.get_setting("google_oauth_client_id")
                if setting and setting.value:
                    client_id = str(setting.value)

            if not client_secret:
                setting = settings_store_instance.get_setting(
                    "google_oauth_client_secret"
                )
                if setting and setting.value:
                    client_secret = str(setting.value)

            if not redirect_uri:
                setting = settings_store_instance.get_setting(
                    "google_oauth_redirect_uri"
                )
                if setting and setting.value:
                    redirect_uri = str(setting.value)
        except Exception as e:
            logger.warning(f"Failed to load OAuth config from System Settings: {e}")

    # Layer 3: environment variable fallback
    if not client_id:
        client_id = os.getenv("GOOGLE_CLIENT_ID")
    if not client_secret:
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    if not redirect_uri:
        redirect_uri = os.getenv(
            "GOOGLE_REDIRECT_URI",
            "http://localhost:8200/api/v1/runtime-oauth/callback",
        )

    if not client_id or not client_secret:
        raise HTTPException(
            status_code=500,
            detail="Google OAuth credentials not configured. "
            "Set them in the Global Settings page, or via "
            "GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET env vars, or "
            "configure per-runtime in auth_config.",
        )

    return client_id, client_secret, redirect_uri


@router.get("/{runtime_id}/authorize")
async def authorize(
    runtime_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Start OAuth2 authorization flow.

    Generates a Google OAuth URL and redirects the browser.
    The state parameter encodes runtime_id and user_id for CSRF protection.
    """
    # Verify runtime exists and user has access
    runtime = (
        db.query(RuntimeEnvironment)
        .filter(
            RuntimeEnvironment.id == runtime_id,
            RuntimeEnvironment.user_id == current_user.id,
        )
        .first()
    )
    if not runtime:
        raise HTTPException(
            status_code=404, detail="Runtime not found or access denied"
        )

    client_id, _, redirect_uri = _get_oauth_credentials(runtime)

    # Generate CSRF state token
    state = secrets.token_urlsafe(32)
    _pending_states[state] = {
        "runtime_id": runtime_id,
        "user_id": current_user.id,
        "created_at": time.time(),
    }

    # Update status to pending
    runtime.auth_status = "pending"
    db.commit()

    # Build Google OAuth URL
    scopes = "openid email profile"
    auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        f"&scope={scopes}"
        f"&state={state}"
        f"&access_type=offline"
        f"&prompt=consent"
    )

    return RedirectResponse(url=auth_url)


@router.get("/callback")
async def callback(
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    OAuth2 callback handler.

    Receives authorization code from Google, sends it to Site-Hub's
    runtime-token-exchange endpoint to get a Site-Hub RS256 JWT,
    encrypts and stores the JWT, then returns HTML that closes the popup.
    """
    if error:
        logger.warning(f"OAuth callback received error: {error}")
        return _popup_close_response(success=False, error=error)

    if not code or not state:
        return _popup_close_response(success=False, error="Missing code or state")

    # Validate state token
    state_data = _pending_states.pop(state, None)
    if not state_data:
        return _popup_close_response(success=False, error="Invalid or expired state")

    # Expire stale states (older than 10 minutes)
    cutoff = time.time() - 600
    stale = [k for k, v in _pending_states.items() if v["created_at"] < cutoff]
    for k in stale:
        _pending_states.pop(k, None)

    runtime_id = state_data["runtime_id"]
    user_id = state_data["user_id"]

    # Load runtime
    runtime = (
        db.query(RuntimeEnvironment)
        .filter(
            RuntimeEnvironment.id == runtime_id,
            RuntimeEnvironment.user_id == user_id,
        )
        .first()
    )
    if not runtime:
        return _popup_close_response(success=False, error="Runtime not found")

    import httpx

    client_id, client_secret, redirect_uri = _get_oauth_credentials(runtime)

    # Extract site_key from runtime metadata for tenant context
    runtime_metadata = runtime.metadata_ if hasattr(runtime, "metadata_") else {}
    if not runtime_metadata:
        runtime_metadata = (runtime.auth_config or {}).get("metadata", {})
    site_key = (runtime_metadata or {}).get("site_key") or os.getenv("SITE_KEY", "")

    # Resolve Site-Hub OIDC base URL
    site_hub_base = os.getenv(
        "SITE_HUB_BASE_URL",
        os.getenv("SITE_HUB_API_URL", "http://site-hub-site-hub-api-1:8000"),
    )

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Exchange Google code via Site-Hub to get a Site-Hub JWT
            resp = await client.post(
                f"{site_hub_base}/api/v1/oidc/binding/runtime-token-exchange",
                json={
                    "code": code,
                    "provider": "google",
                    "site_key": site_key,
                    "redirect_uri": redirect_uri,
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
            )
            if resp.status_code != 200:
                logger.error(
                    f"Site-Hub token exchange failed: status={resp.status_code} "
                    f"body={resp.text}"
                )
                runtime.auth_status = "error"
                db.commit()
                return _popup_close_response(
                    success=False, error="Site-Hub token exchange failed"
                )

            tokens = resp.json()
    except Exception as e:
        logger.error(f"Token exchange failed: {e}")
        runtime.auth_status = "error"
        db.commit()
        return _popup_close_response(success=False, error="Token exchange failed")

    identity = tokens.get("identity")

    # Build token data and encrypt
    # tokens now contains a Site-Hub RS256 JWT (not a Google opaque token)
    token_data = {
        "access_token": tokens["access_token"],
        "refresh_token": tokens.get("refresh_token"),
        "expiry": time.time() + tokens.get("expires_in", 900),
        "identity": identity,
        "token_source": "site-hub",  # Mark as Site-Hub JWT for refresh logic
    }

    # Preserve per-runtime client_id/client_secret if they exist
    existing_config = runtime.auth_config or {}
    encrypted = auth_service.encrypt_token_blob(token_data)
    if existing_config.get("client_id"):
        encrypted["client_id"] = existing_config["client_id"]
    if existing_config.get("client_secret"):
        encrypted["client_secret"] = existing_config["client_secret"]

    runtime.auth_type = "oauth2"
    runtime.auth_config = encrypted
    runtime.auth_status = "connected"
    db.commit()

    logger.info(f"OAuth flow completed for runtime {runtime_id}, identity: {identity}")
    return _popup_close_response(success=True)


@router.get("/{runtime_id}/status")
async def status(
    runtime_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return current auth status and identity for a runtime."""
    runtime = (
        db.query(RuntimeEnvironment)
        .filter(
            RuntimeEnvironment.id == runtime_id,
            RuntimeEnvironment.user_id == current_user.id,
        )
        .first()
    )
    if not runtime:
        raise HTTPException(
            status_code=404, detail="Runtime not found or access denied"
        )

    identity = None
    if runtime.auth_status == "connected" and runtime.auth_config:
        identity = runtime.auth_config.get("identity")

    return {
        "runtime_id": runtime_id,
        "auth_status": runtime.auth_status or "disconnected",
        "auth_identity": identity,
    }


@router.post("/{runtime_id}/disconnect")
async def disconnect(
    runtime_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Disconnect OAuth for a runtime.

    Clears encrypted tokens and resets auth_status.
    Preserves per-runtime client_id/client_secret if configured.
    """
    runtime = (
        db.query(RuntimeEnvironment)
        .filter(
            RuntimeEnvironment.id == runtime_id,
            RuntimeEnvironment.user_id == current_user.id,
        )
        .first()
    )
    if not runtime:
        raise HTTPException(
            status_code=404, detail="Runtime not found or access denied"
        )

    # Preserve per-runtime client credentials
    existing = runtime.auth_config or {}
    preserved = {}
    if existing.get("client_id"):
        preserved["client_id"] = existing["client_id"]
    if existing.get("client_secret"):
        preserved["client_secret"] = existing["client_secret"]

    runtime.auth_config = preserved or None
    runtime.auth_status = "disconnected"
    db.commit()

    logger.info(f"OAuth disconnected for runtime {runtime_id}")
    return {"runtime_id": runtime_id, "auth_status": "disconnected"}


def _popup_close_response(success: bool, error: Optional[str] = None):
    """Return HTML page that posts message to opener and closes the popup."""
    status_msg = "success" if success else f"error: {error or 'unknown'}"
    html = f"""<!DOCTYPE html>
<html><head><title>OAuth</title></head>
<body>
<script>
  if (window.opener) {{
    window.opener.postMessage({{
      type: 'RUNTIME_OAUTH_RESULT',
      success: {'true' if success else 'false'},
      error: {f'"{error}"' if error else 'null'}
    }}, '*');
  }}
  window.close();
</script>
<p>{'Authorization successful. This window will close.' if success else f'Authorization failed: {error}. You may close this window.'}</p>
</body></html>"""

    from fastapi.responses import HTMLResponse

    return HTMLResponse(content=html)
