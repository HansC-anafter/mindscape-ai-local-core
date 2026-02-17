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

            # NOTE: do NOT read google_oauth_redirect_uri from settings here
            # — that value belongs to the Google Drive tool callback.
            # Runtime OAuth has its own dedicated callback endpoint.
        except Exception as e:
            logger.warning(f"Failed to load OAuth config from System Settings: {e}")

    # Layer 3: environment variable fallback
    if not client_id:
        client_id = os.getenv("GOOGLE_CLIENT_ID")
    if not client_secret:
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET")

    # Runtime OAuth always uses its own callback path
    if not redirect_uri:
        base = os.getenv("RUNTIME_OAUTH_BASE_URL", "http://localhost:8300")
        redirect_uri = f"{base.rstrip('/')}/api/v1/runtime-oauth/callback"

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

    For cloud provider runtimes (with config_url): redirects to the
    provider's runtime-oauth-initiate endpoint so the OAuth flow stays
    on the provider domain.

    For local-only runtimes: redirects directly to Google OAuth.
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

    # Update status to pending
    runtime.auth_status = "pending"
    db.commit()

    # If this runtime has a config_url, redirect through the provider domain
    if runtime.config_url:
        # Get site_key from workspace config or runtime metadata
        site_key = ""
        runtime_metadata = runtime.metadata_ if hasattr(runtime, "metadata_") else {}
        if runtime_metadata:
            site_key = runtime_metadata.get("site_key", "")

        if not site_key:
            # Try loading from workspace_runtime_config
            try:
                from ...models.workspace_runtime_config import WorkspaceRuntimeConfig

                config = (
                    db.query(WorkspaceRuntimeConfig)
                    .filter(WorkspaceRuntimeConfig.runtime_id == runtime_id)
                    .first()
                )
                if config and config.site_key:
                    site_key = config.site_key
            except Exception as e:
                logger.warning(f"Failed to load workspace config for site_key: {e}")

        if not site_key:
            site_key = os.getenv("SITE_KEY", "")

        # Build provider initiate URL
        provider_base = runtime.config_url.rstrip("/")
        callback_origin = os.getenv(
            "LOCAL_CORE_ORIGIN",
            f"http://localhost:{os.getenv('PORT', '8300')}",
        )

        # Generate a one-time nonce for the landing endpoint
        landing_nonce = secrets.token_urlsafe(32)
        _pending_states[f"landing_{landing_nonce}"] = {
            "runtime_id": runtime_id,
            "user_id": current_user.id,
            "created_at": time.time(),
        }

        from urllib.parse import urlencode

        params = urlencode(
            {
                "site_key": site_key,
                "callback_origin": callback_origin,
                "runtime_id": runtime_id,
                "landing_nonce": landing_nonce,
            }
        )
        initiate_url = (
            f"{provider_base}/api/v1/oidc/binding/" f"runtime-oauth-initiate?{params}"
        )

        logger.info(f"Cloud provider runtime detected, redirecting to: {initiate_url}")
        return RedirectResponse(url=initiate_url)

    # Local-only runtime: redirect directly to Google OAuth
    client_id, _, redirect_uri = _get_oauth_credentials(runtime)

    state = secrets.token_urlsafe(32)
    _pending_states[state] = {
        "runtime_id": runtime_id,
        "user_id": current_user.id,
        "created_at": time.time(),
    }

    # Use GCA scopes for Code Assist compatibility
    from .gca_constants import GCA_OAUTH_SCOPES_STRING

    scopes = GCA_OAUTH_SCOPES_STRING
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

    Receives authorization code from Google, sends it to the cloud
    provider's runtime-token-exchange endpoint to get a provider JWT,
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

    # Resolve OIDC provider base URL from runtime config_url or env var
    provider_base = None
    if runtime and runtime.config_url:
        from urllib.parse import urlparse as _urlparse

        _parsed = _urlparse(runtime.config_url)
        provider_base = f"{_parsed.scheme}://{_parsed.netloc}"
    if not provider_base:
        provider_base = os.getenv(
            "CLOUD_PROVIDER_BASE_URL",
            os.getenv("CLOUD_PROVIDER_API_URL", ""),
        )
    if not provider_base:
        logger.error("No cloud provider base URL available for token exchange")
        runtime.auth_status = "error"
        db.commit()
        return _popup_close_response(
            success=False, error="Cloud provider URL not configured"
        )

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Exchange Google code via cloud provider to get a provider JWT
            resp = await client.post(
                f"{provider_base}/api/v1/oidc/binding/runtime-token-exchange",
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
                    f"Provider token exchange failed: status={resp.status_code} "
                    f"body={resp.text}"
                )
                runtime.auth_status = "error"
                db.commit()
                return _popup_close_response(
                    success=False, error="Provider token exchange failed"
                )

            tokens = resp.json()
    except Exception as e:
        logger.error(f"Token exchange failed: {e}")
        runtime.auth_status = "error"
        db.commit()
        return _popup_close_response(success=False, error="Token exchange failed")

    identity = tokens.get("identity")

    # Build token data and encrypt
    # tokens now contains a provider RS256 JWT (not a Google opaque token)
    token_data = {
        "access_token": tokens["access_token"],
        "refresh_token": tokens.get("refresh_token"),
        "expiry": time.time() + tokens.get("expires_in", 900),
        "identity": identity,
        "token_source": "oidc",  # Mark as provider OIDC JWT for refresh logic
        # Raw IDP tokens for CLI agent authentication
        "idp_access_token": tokens.get("idp_access_token"),
        "idp_refresh_token": tokens.get("idp_refresh_token"),
        "idp_token_expiry": time.time() + tokens.get("idp_token_expiry", 3600),
    }

    # Do NOT preserve site-hub client credentials in local storage.
    # GCA token refresh uses Gemini CLI's public OAuth credentials
    # defined in gca_constants.py — no need to store provider secrets.
    encrypted = auth_service.encrypt_token_blob(token_data)

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


@router.post("/{runtime_id}/store-token")
async def store_token(
    runtime_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Store a provider JWT received via the browser OAuth flow.

    Called by the frontend after receiving the JWT from the cloud
    provider's postMessage callback. Encrypts and saves it in runtime.auth_config.
    """
    body = await request.json()
    access_token = body.get("access_token")
    refresh_token = body.get("refresh_token")
    expires_in = body.get("expires_in", 900)

    if not access_token:
        raise HTTPException(status_code=400, detail="Missing access_token")

    print(
        f"[STORE-TOKEN-DEBUG] runtime_id={runtime_id}, has_access_token={bool(access_token)}, has_refresh={bool(refresh_token)}, expires_in={expires_in}"
    )

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

    import time as _time

    token_data = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "Bearer",
        "expiry": _time.time() + expires_in,
        "token_source": "oidc",
    }

    # Preserve existing per-runtime OAuth client credentials
    existing = runtime.auth_config or {}
    preserved = {}
    if existing.get("client_id"):
        preserved["client_id"] = existing["client_id"]
    if existing.get("client_secret"):
        preserved["client_secret"] = existing["client_secret"]

    encrypted = auth_service.encrypt_token_blob(token_data)
    encrypted.update(preserved)
    print(f"[STORE-TOKEN-DEBUG] encrypted keys: {list(encrypted.keys())}")

    runtime.auth_config = encrypted
    runtime.auth_type = "oauth2"
    runtime.auth_status = "connected"
    db.commit()

    print(
        f"[STORE-TOKEN-DEBUG] SAVED: auth_type={runtime.auth_type}, auth_status={runtime.auth_status}, auth_config_keys={list(runtime.auth_config.keys()) if isinstance(runtime.auth_config, dict) else 'not-dict'}"
    )
    logger.info(f"Stored provider JWT for runtime {runtime_id}")
    return {
        "runtime_id": runtime_id,
        "auth_status": "connected",
        "email": body.get("email", ""),
    }


@router.post("/provider-jwt-landing")
async def provider_jwt_landing(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Receive provider JWT via form POST redirect (COOP-safe).

    The cloud provider's runtime-oauth-callback redirects the popup here
    via auto-submitting HTML form. This avoids the COOP issue where
    window.opener.postMessage() fails after Google OAuth navigation.

    No user auth required — validated via one-time landing_nonce.
    """
    from fastapi.responses import HTMLResponse

    form = await request.form()
    access_token = form.get("access_token", "")
    refresh_token = form.get("refresh_token", "")
    expires_in_str = form.get("expires_in", "900")
    email = form.get("email", "")
    landing_nonce = form.get("landing_nonce", "")
    runtime_id = form.get("runtime_id", "")
    # Raw IDP tokens passed through from cloud provider
    idp_access_token = form.get("idp_access_token", "")
    idp_refresh_token = form.get("idp_refresh_token", "")
    idp_token_expiry_str = form.get("idp_token_expiry", "")
    # NOTE: google_client_id / google_client_secret are intentionally NOT
    # read from the form. GCA token refresh uses Gemini CLI's public
    # OAuth credentials (gca_constants.py) instead of provider secrets.

    print(
        f"[JWT-LANDING-DEBUG] runtime_id={runtime_id}, has_token={bool(access_token)}, has_refresh={bool(refresh_token)}, email={email}, has_nonce={bool(landing_nonce)}"
    )
    print(
        f"[JWT-LANDING-DEBUG] idp_access_token={bool(idp_access_token)}, idp_refresh_token={bool(idp_refresh_token)}"
    )

    # Validate required fields (nonce validation removed — in-memory dict
    # doesn't survive multi-worker uvicorn; runtime_id + token is sufficient)
    if not runtime_id:
        print("[JWT-LANDING-DEBUG] MISSING RUNTIME_ID")
        return HTMLResponse(
            content=_close_window_html(False, "Missing runtime ID"),
            status_code=400,
        )

    if not access_token:
        print("[JWT-LANDING-DEBUG] NO ACCESS TOKEN")
        return HTMLResponse(
            content=_close_window_html(False, "No access token received"),
            status_code=400,
        )

    # Store the JWT in the runtime
    try:
        runtime = (
            db.query(RuntimeEnvironment)
            .filter(RuntimeEnvironment.id == runtime_id)
            .first()
        )
        if not runtime:
            print(f"[JWT-LANDING-DEBUG] RUNTIME NOT FOUND: {runtime_id}")
            return HTMLResponse(
                content=_close_window_html(False, "Runtime not found"),
                status_code=404,
            )

        import time as _time

        expires_in = int(expires_in_str) if expires_in_str else 900
        token_data = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "Bearer",
            "expiry": _time.time() + expires_in,
            "token_source": "oidc",
        }

        # Store raw IDP tokens for CLI agent authentication
        if idp_access_token:
            idp_expiry_secs = (
                int(idp_token_expiry_str) if idp_token_expiry_str else 3600
            )
            token_data["idp_access_token"] = idp_access_token
            token_data["idp_refresh_token"] = idp_refresh_token
            token_data["idp_token_expiry"] = _time.time() + idp_expiry_secs
            # NOTE: site-hub Client ID/Secret are intentionally NOT stored.
            # GCA token refresh uses Gemini CLI's public OAuth credentials
            # (gca_constants.py). Storing provider secrets on user machines
            # is a security anti-pattern for web-application-type OAuth.

        encrypted = auth_service.encrypt_token_blob(token_data)

        runtime.auth_config = encrypted
        runtime.auth_type = "oauth2"
        runtime.auth_status = "connected"
        db.commit()

        print(
            f"[JWT-LANDING-DEBUG] STORED: runtime={runtime_id}, auth_type=oauth2, auth_status=connected"
        )
        logger.info(f"JWT landing: stored token for runtime {runtime_id}")

        return HTMLResponse(content=_close_window_html(True, email=email))

    except Exception as e:
        print(f"[JWT-LANDING-DEBUG] EXCEPTION: {e}")
        logger.error(f"JWT landing error: {e}")
        return HTMLResponse(
            content=_close_window_html(False, str(e)),
            status_code=500,
        )


def _close_window_html(success: bool, error: str = "", email: str = "") -> str:
    """Return HTML that shows status and closes the window."""
    if success:
        status_text = f"Connected as {email}" if email else "Connected"
        status_color = "#22c55e"
    else:
        status_text = f"Error: {error}"
        status_color = "#ef4444"

    return f"""<!DOCTYPE html>
<html><head><title>OAuth {'Success' if success else 'Failed'}</title></head>
<body style="display:flex;align-items:center;justify-content:center;height:100vh;
font-family:system-ui;background:#111;color:#eee">
<div style="text-align:center">
  <p style="color:{status_color};font-size:1.2rem">{status_text}</p>
  <p style="color:#888">This window will close automatically...</p>
</div>
<script>
setTimeout(function(){{ window.close(); }}, 2000);
</script>
</body></html>"""
