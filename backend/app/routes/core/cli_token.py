"""
CLI Token Endpoint

Returns auth environment variables for CLI bridge processes.
Reads the configured auth mode and credentials from system_settings,
returning them as env-var key-value pairs that the bridge script
injects into the Gemini CLI subprocess.

Supported modes:
  - gca           : returns GOOGLE_CLOUD_ACCESS_TOKEN + GOOGLE_GENAI_USE_GCA
                    (reads stored Google IDP token from runtime auth_config)
  - gemini_api_key: returns GEMINI_API_KEY
  - vertex_ai     : returns GOOGLE_CLOUD_PROJECT + GOOGLE_CLOUD_LOCATION
"""

import logging
import os
import time

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _get_gca_token() -> dict:
    """Retrieve Google IDP access token from the first connected runtime.

    Looks up the first runtime with auth_status='connected' and
    decrypts idp_access_token from the encrypted token blob.
    Refreshes the token if expired using idp_refresh_token.

    Returns:
        dict with env vars or error details.
    """
    try:
        from ...database.session import get_db_postgres as get_db
    except ImportError:
        try:
            from ...database import get_db_postgres as get_db
        except ImportError:
            from mindscape.di.providers import get_db_session as get_db

    from ...models.runtime_environment import RuntimeEnvironment
    from ...services.runtime_auth_service import RuntimeAuthService

    db = next(get_db())
    try:
        # Use the dedicated gca-local runtime for GCA token storage
        runtime = (
            db.query(RuntimeEnvironment)
            .filter(
                RuntimeEnvironment.id == "gca-local",
                RuntimeEnvironment.auth_status == "connected",
            )
            .first()
        )
        if not runtime:
            return {
                "error": "GCA not connected. "
                "Connect via Web Console > Settings > CLI Agent Keys > "
                "Google Account tab."
            }

        auth_service = RuntimeAuthService()
        token_data = auth_service.decrypt_token_blob(runtime.auth_config or {})
        if not token_data:
            return {"error": "Failed to decrypt token blob from runtime"}

        idp_access_token = token_data.get("idp_access_token")
        idp_refresh_token = token_data.get("idp_refresh_token")
        idp_expiry = token_data.get("idp_token_expiry", 0)

        if not idp_access_token:
            return {"error": "No IDP access token stored in runtime auth_config"}

        # Refresh if expired (with 60s buffer)
        if idp_expiry and time.time() > (idp_expiry - 60):
            logger.info("IDP token expired, refreshing via Google OAuth")
            refreshed = _refresh_google_token(
                idp_refresh_token, runtime, auth_service, token_data, db
            )
            if refreshed:
                idp_access_token = refreshed
            else:
                return {"error": "IDP token expired and refresh failed"}

        # Resolve GCP project ID (required by cloudcode-pa)
        gcp_project = token_data.get("gcp_project") or ""
        if not gcp_project:
            try:
                from ...services.system_settings_store import SystemSettingsStore

                s = SystemSettingsStore()
                gcp_project = s.get("google_cloud_project", "")
            except Exception:
                pass
        if not gcp_project:
            gcp_project = os.getenv("GOOGLE_CLOUD_PROJECT", "")

        env = {
            "GOOGLE_GENAI_USE_GCA": "true",
            "GOOGLE_CLOUD_ACCESS_TOKEN": idp_access_token,
        }
        if gcp_project:
            env["GOOGLE_CLOUD_PROJECT"] = gcp_project

        return {"env": env}
    finally:
        db.close()


def _refresh_google_token(refresh_token, runtime, auth_service, token_data, db):
    """Refresh Google IDP token using Gemini CLI's public OAuth credentials.

    Uses the CLI's installed-application Client ID/Secret (public by
    design) to refresh the access token via Google's OAuth2 endpoint.

    Returns new access_token string on success, None on failure.
    """
    if not refresh_token:
        logger.warning("No IDP refresh token available")
        return None

    # Use Gemini CLI's public OAuth credentials (installed app type).
    # These are intentionally public and safe to embed in client code.
    from .gca_constants import GCA_OAUTH_CLIENT_ID, GCA_OAUTH_CLIENT_SECRET

    client_id = GCA_OAUTH_CLIENT_ID
    client_secret = GCA_OAUTH_CLIENT_SECRET

    import urllib.request
    import urllib.parse
    import json

    try:
        data = urllib.parse.urlencode(
            {
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            }
        ).encode()

        req = urllib.request.Request(
            "https://oauth2.googleapis.com/token",
            data=data,
            method="POST",
        )
        req.add_header("Content-Type", "application/x-www-form-urlencoded")

        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())

        new_access_token = result.get("access_token")
        expires_in = result.get("expires_in", 3600)

        if not new_access_token:
            logger.error("Google token refresh returned no access_token")
            return None

        # Update stored token data
        token_data["idp_access_token"] = new_access_token
        token_data["idp_token_expiry"] = time.time() + expires_in

        # Remove any leaked site-hub credentials from stored data
        token_data.pop("google_client_id", None)
        token_data.pop("google_client_secret", None)

        encrypted = auth_service.encrypt_token_blob(token_data)

        runtime.auth_config = encrypted
        db.commit()

        logger.info("IDP token refreshed successfully, expires_in=%s", expires_in)
        return new_access_token

    except Exception as e:
        logger.error("Google IDP token refresh failed: %s", e)
        return None


@router.get("/cli-token")
async def get_cli_token():
    """Return auth env vars for CLI bridge processes.

    Queries system_settings for gemini_cli_auth_mode and the
    corresponding credentials.  Falls back to host environment
    variables when system_settings is unavailable or empty.

    Returns:
        JSON with auth_mode and env dict, or error details.
    """
    try:
        from ...services.system_settings_store import SystemSettingsStore

        settings = SystemSettingsStore()

        auth_mode = settings.get("gemini_cli_auth_mode", "gca")

        # ── GCA mode: return stored Google IDP token ──
        if auth_mode == "gca":
            result = _get_gca_token()
            if "error" in result:
                logger.warning("GCA token retrieval failed: %s", result["error"])
                return {
                    "auth_mode": "gca",
                    "env": {},
                    "error": result["error"],
                }
            return {
                "auth_mode": "gca",
                "env": result["env"],
            }

        # ── API key mode ──
        if auth_mode == "gemini_api_key":
            api_key = settings.get("gemini_api_key", "")
            if not api_key:
                api_key = os.environ.get("GEMINI_API_KEY", "")
            if not api_key:
                return {
                    "auth_mode": auth_mode,
                    "env": {},
                    "error": "gemini_api_key not configured in system_settings",
                }
            return {
                "auth_mode": auth_mode,
                "env": {"GEMINI_API_KEY": api_key},
            }

        # ── Vertex AI mode ──
        if auth_mode == "vertex_ai":
            project = settings.get(
                "google_cloud_project",
                os.environ.get("GOOGLE_CLOUD_PROJECT", ""),
            )
            location = settings.get(
                "google_cloud_location",
                os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
            )
            if not project:
                return {
                    "auth_mode": auth_mode,
                    "env": {},
                    "error": "google_cloud_project not configured",
                }
            return {
                "auth_mode": auth_mode,
                "env": {
                    "GOOGLE_GENAI_USE_VERTEXAI": "true",
                    "GOOGLE_CLOUD_PROJECT": project,
                    "GOOGLE_CLOUD_LOCATION": location,
                },
            }

        return {
            "auth_mode": auth_mode,
            "env": {},
            "error": f"Unknown auth_mode: {auth_mode}",
        }

    except Exception as e:
        logger.error("Failed to retrieve CLI auth config: %s", e)
        # Graceful fallback: check host env vars directly
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if api_key:
            return {
                "auth_mode": "gemini_api_key",
                "env": {"GEMINI_API_KEY": api_key},
                "warning": f"system_settings unavailable ({e}), using env fallback",
            }
        return {
            "auth_mode": "unknown",
            "env": {},
            "error": f"system_settings unavailable and no env fallback: {e}",
        }
