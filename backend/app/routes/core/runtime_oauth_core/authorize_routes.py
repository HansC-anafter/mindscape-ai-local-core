import os
import secrets
import time

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from backend.app.models.runtime_environment import RuntimeEnvironment

from .credentials import _commit_runtime_registration, _get_oauth_credentials
from .dependencies import User, get_current_user, get_db
from .state import logger

router = APIRouter()

@router.get("/{runtime_id}/authorize")
async def authorize(
    runtime_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Start OAuth2 authorization flow.

    GCA mode: always uses local OAuth with Gemini CLI's Client ID.
    cloudcode-pa.googleapis.com is a restricted API only available on
    CLI's project (681255809395). Tokens must be obtained using CLI's
    Client ID so they bind to the correct project.

    Non-GCA: uses site-hub provider flow if config_url is present.
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

    # Determine auth mode - GCA always uses local OAuth with CLI Client ID
    is_gca = False
    try:
        from backend.app.services.system_settings_store import SystemSettingsStore

        auth_mode = SystemSettingsStore().get("gemini_cli_auth_mode", "gca")
        is_gca = auth_mode == "gca"
    except Exception:
        is_gca = True  # Default to GCA

    if is_gca:
        # GCA mode: direct Google OAuth with CLI's Client ID.
        # CLI's OAuth app is installed-app type, only allows localhost
        # redirect URIs. Site-hub's domain would cause redirect_uri_mismatch.
        from backend.app.routes.core.gca_constants import get_gca_client_id, GCA_OAUTH_SCOPES_STRING

        GCA_OAUTH_CLIENT_ID = get_gca_client_id()

        base = os.getenv(
            "RUNTIME_OAUTH_BASE_URL", f"http://localhost:{os.getenv('PORT', '8200')}"
        )
        redirect_uri = f"{base.rstrip('/')}/api/v1/runtime-oauth/callback"

        state = secrets.token_urlsafe(32)

        # Store state in DB (not in-memory) so all uvicorn workers can access it
        meta = dict(runtime.extra_metadata or {})
        meta["oauth_state"] = {
            "token": state,
            "user_id": current_user.id,
            "created_at": time.time(),
            "flow": "gca",
        }
        runtime.extra_metadata = meta
        runtime.auth_status = "pending"
        _commit_runtime_registration(db, runtime)
        logger.info("GCA authorize: state stored in DB for runtime %s", runtime_id)

        auth_url = (
            "https://accounts.google.com/o/oauth2/v2/auth"
            f"?client_id={GCA_OAUTH_CLIENT_ID}"
            f"&redirect_uri={redirect_uri}"
            f"&response_type=code"
            f"&scope={GCA_OAUTH_SCOPES_STRING}"
            f"&state={state}"
            f"&access_type=offline"
            f"&prompt=consent"
        )

        logger.info(
            "GCA mode: local OAuth with CLI Client ID for runtime %s",
            runtime_id,
        )
        return RedirectResponse(url=auth_url)

    # Non-GCA: if runtime has config_url, redirect through site-hub
    if runtime.config_url:
        # Get site_key from workspace config or runtime metadata
        site_key = ""
        runtime_metadata = runtime.metadata_ if hasattr(runtime, "metadata_") else {}
        if runtime_metadata:
            site_key = runtime_metadata.get("site_key", "")

        if not site_key:
            # Try loading from workspace_runtime_config
            try:
                from backend.app.models.workspace_runtime_config import WorkspaceRuntimeConfig

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

        # Store landing state in DB for cross-worker access
        meta = dict(runtime.extra_metadata or {})
        meta["oauth_state"] = {
            "token": f"landing_{landing_nonce}",
            "user_id": current_user.id,
            "created_at": time.time(),
        }
        runtime.extra_metadata = meta
        runtime.auth_status = "pending"
        _commit_runtime_registration(db, runtime)

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

    # Local-only, non-GCA runtime: redirect directly to Google OAuth
    client_id, _, redirect_uri = _get_oauth_credentials(runtime)

    state = secrets.token_urlsafe(32)

    # Store state in DB for cross-worker access
    meta = dict(runtime.extra_metadata or {})
    meta["oauth_state"] = {
        "token": state,
        "user_id": current_user.id,
        "created_at": time.time(),
    }
    runtime.extra_metadata = meta
    runtime.auth_status = "pending"
    _commit_runtime_registration(db, runtime)

    from backend.app.routes.core.gca_constants import GCA_OAUTH_SCOPES_STRING

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
