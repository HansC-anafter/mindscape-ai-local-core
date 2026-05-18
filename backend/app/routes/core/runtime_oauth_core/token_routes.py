from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from backend.app.models.runtime_environment import RuntimeEnvironment

from .credentials import _commit_runtime_registration
from .dependencies import User, get_current_user, get_db
from .responses import _close_window_html
from .state import auth_service, logger

router = APIRouter()

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
    _commit_runtime_registration(db, runtime)

    logger.info(f"OAuth disconnected for runtime {runtime_id}")
    return {"runtime_id": runtime_id, "auth_status": "disconnected"}


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
    _commit_runtime_registration(db, runtime)

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

    No user auth required - validated via one-time landing_nonce.
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

    # Validate required fields (nonce validation removed - in-memory dict
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
        _commit_runtime_registration(db, runtime)

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
