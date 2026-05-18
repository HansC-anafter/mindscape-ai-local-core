import os
import time
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.models.runtime_environment import RuntimeEnvironment

from .credentials import _commit_runtime_registration, _get_oauth_credentials
from .dependencies import get_db
from .responses import _popup_close_response
from .state import auth_service, logger

router = APIRouter()

@router.get("/callback")
async def callback(
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    OAuth2 callback handler.

    GCA flow: exchanges code directly with Google using CLI credentials.
    Non-GCA flow: sends code to site-hub for provider JWT exchange.
    """
    if error:
        logger.warning(f"OAuth callback received error: {error}")
        return _popup_close_response(success=False, error=error)

    if not code or not state:
        return _popup_close_response(success=False, error="Missing code or state")

    # Validate state token from DB (supports multi-worker uvicorn)
    # Find the runtime whose extra_metadata.oauth_state.token matches
    all_pending = (
        db.query(RuntimeEnvironment)
        .filter(RuntimeEnvironment.auth_status == "pending")
        .all()
    )

    runtime = None
    state_data = None
    for rt in all_pending:
        meta = rt.extra_metadata or {}
        oauth_state = meta.get("oauth_state", {})
        if oauth_state.get("token") == state:
            # Check expiry (10 minutes)
            if time.time() - oauth_state.get("created_at", 0) > 600:
                logger.warning("OAuth state expired for runtime %s", rt.id)
                rt.auth_status = "disconnected"
                _commit_runtime_registration(db, rt)
                return _popup_close_response(
                    success=False, error="State expired, please try again"
                )
            runtime = rt
            state_data = oauth_state
            break

    if not runtime or not state_data:
        logger.warning("OAuth callback: no matching state found in DB")
        # Reset stale pending runtimes
        cutoff = time.time() - 600
        for rt in all_pending:
            meta = rt.extra_metadata or {}
            created = meta.get("oauth_state", {}).get("created_at", 0)
            if created and created < cutoff:
                rt.auth_status = "disconnected"
                logger.info("Reset stale pending runtime %s", rt.id)
        _commit_runtime_registration(
            db,
            *(rt for rt in all_pending if (rt.extra_metadata or {}).get("oauth_state", {}).get("created_at", 0) and (rt.extra_metadata or {}).get("oauth_state", {}).get("created_at", 0) < cutoff),
        )
        return _popup_close_response(success=False, error="Invalid or expired state")

    runtime_id = runtime.id
    user_id = state_data.get("user_id", "")
    is_gca_flow = state_data.get("flow") == "gca"

    logger.info(
        "OAuth callback: matched state to runtime %s, flow=%s",
        runtime_id,
        "gca" if is_gca_flow else "provider",
    )

    # Clear the oauth_state from metadata now that it's consumed
    meta = dict(runtime.extra_metadata or {})
    meta.pop("oauth_state", None)
    runtime.extra_metadata = meta
    _commit_runtime_registration(db, runtime)

    if is_gca_flow:
        return await _handle_gca_callback(code, runtime_id, runtime, db)

    # Non-GCA: exchange via site-hub provider
    return await _handle_provider_callback(code, runtime_id, runtime, db)


async def _handle_gca_callback(code, runtime_id, runtime, db):
    """Exchange Google auth code directly using CLI credentials.

    Tokens obtained with CLI's Client ID bind to project 681255809395
    where cloudcode-pa.googleapis.com is enabled.
    """
    import httpx
    from backend.app.routes.core.gca_constants import get_gca_client_id, get_gca_client_secret

    GCA_OAUTH_CLIENT_ID = get_gca_client_id()
    GCA_OAUTH_CLIENT_SECRET = get_gca_client_secret()

    base = os.getenv(
        "RUNTIME_OAUTH_BASE_URL", f"http://localhost:{os.getenv('PORT', '8200')}"
    )
    redirect_uri = f"{base.rstrip('/')}/api/v1/runtime-oauth/callback"

    logger.info(
        "GCA callback: starting token exchange for runtime %s, redirect_uri=%s",
        runtime_id,
        redirect_uri,
    )

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Exchange code directly with Google (not via site-hub)
            token_resp = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": GCA_OAUTH_CLIENT_ID,
                    "client_secret": GCA_OAUTH_CLIENT_SECRET,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            logger.info(
                "GCA callback: Google token response status=%s",
                token_resp.status_code,
            )
            if token_resp.status_code != 200:
                logger.error(
                    "GCA token exchange failed: status=%s body=%s",
                    token_resp.status_code,
                    token_resp.text,
                )
                runtime.auth_status = "error"
                _commit_runtime_registration(db, runtime)
                return _popup_close_response(
                    success=False, error="Google token exchange failed"
                )

            google_tokens = token_resp.json()
            logger.info(
                "GCA callback: got tokens, has_access=%s has_refresh=%s",
                bool(google_tokens.get("access_token")),
                bool(google_tokens.get("refresh_token")),
            )

            # Fetch user email for identity display
            identity = ""
            access_token = google_tokens.get("access_token", "")
            if access_token:
                userinfo_resp = await client.get(
                    "https://www.googleapis.com/oauth2/v2/userinfo",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                if userinfo_resp.status_code == 200:
                    identity = userinfo_resp.json().get("email", "")
                    logger.info("GCA callback: user identity=%s", identity)

    except Exception as e:
        logger.error("GCA OAuth exchange error: %s", e, exc_info=True)
        runtime.auth_status = "error"
        _commit_runtime_registration(db, runtime)
        return _popup_close_response(success=False, error="GCA token exchange failed")

    # Store tokens and update runtime status
    try:
        expires_in = google_tokens.get("expires_in", 3600)
        token_data = {
            "access_token": "",  # No site-hub JWT needed for GCA
            "refresh_token": "",
            "expiry": 0,
            "identity": identity,
            "token_source": "gca_direct",
            # IDP tokens obtained with CLI's Client ID
            "idp_access_token": google_tokens.get("access_token"),
            "idp_refresh_token": google_tokens.get("refresh_token"),
            "idp_token_expiry": time.time() + expires_in,
        }

        logger.info("GCA callback: encrypting token blob")
        encrypted = auth_service.encrypt_token_blob(token_data)
        logger.info(
            "GCA callback: encrypted blob length=%s",
            len(encrypted) if encrypted else 0,
        )

        runtime.auth_type = "oauth2"
        runtime.auth_config = encrypted
        runtime.auth_status = "connected"
        logger.info(
            "GCA callback: set runtime fields, about to commit. "
            "runtime.id=%s auth_status=%s",
            runtime.id,
            runtime.auth_status,
        )

        _commit_runtime_registration(db, runtime)
        logger.info("GCA callback: DB commit successful")

        # Verify the commit persisted
        db.refresh(runtime)
        logger.info(
            "GCA callback: post-commit verify auth_status=%s has_config=%s",
            runtime.auth_status,
            bool(runtime.auth_config),
        )

    except Exception as e:
        logger.error("GCA callback: failed to store tokens: %s", e, exc_info=True)
        try:
            runtime.auth_status = "error"
            _commit_runtime_registration(db, runtime)
        except Exception:
            pass
        return _popup_close_response(
            success=False, error=f"Failed to store tokens: {e}"
        )

    logger.info(
        "GCA OAuth completed for runtime %s, identity: %s",
        runtime_id,
        identity,
    )
    return _popup_close_response(success=True)


async def _handle_provider_callback(code, runtime_id, runtime, db):
    """Exchange code via site-hub provider for a Site-Hub JWT."""
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
        _commit_runtime_registration(db, runtime)
        return _popup_close_response(
            success=False, error="Cloud provider URL not configured"
        )

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
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
                _commit_runtime_registration(db, runtime)
                return _popup_close_response(
                    success=False, error="Provider token exchange failed"
                )

            tokens = resp.json()
    except Exception as e:
        logger.error(f"Token exchange failed: {e}")
        runtime.auth_status = "error"
        _commit_runtime_registration(db, runtime)
        return _popup_close_response(success=False, error="Token exchange failed")

    identity = tokens.get("identity")

    token_data = {
        "access_token": tokens["access_token"],
        "refresh_token": tokens.get("refresh_token"),
        "expiry": time.time() + tokens.get("expires_in", 900),
        "identity": identity,
        "token_source": "oidc",
        "idp_access_token": tokens.get("idp_access_token"),
        "idp_refresh_token": tokens.get("idp_refresh_token"),
        "idp_token_expiry": time.time() + tokens.get("idp_token_expiry", 3600),
    }

    encrypted = auth_service.encrypt_token_blob(token_data)

    runtime.auth_type = "oauth2"
    runtime.auth_config = encrypted
    runtime.auth_status = "connected"
    _commit_runtime_registration(db, runtime)

    logger.info(f"OAuth flow completed for runtime {runtime_id}, identity: {identity}")
    return _popup_close_response(success=True)
