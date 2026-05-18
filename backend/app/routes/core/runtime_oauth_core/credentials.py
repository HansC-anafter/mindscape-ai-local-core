import os
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.app.models.runtime_environment import RuntimeEnvironment
from backend.app.services.runtime_route_registration import (
    sync_runtime_registration_metadata,
)

from .state import auth_service, logger

def _commit_runtime_registration(
    db: Session,
    *runtimes: Optional[RuntimeEnvironment],
) -> None:
    seen: set[int] = set()
    for runtime in runtimes:
        if runtime is None:
            continue
        marker = id(runtime)
        if marker in seen:
            continue
        seen.add(marker)
        sync_runtime_registration_metadata(runtime)
    db.commit()


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
            from backend.app.services.system_settings_store import SystemSettingsStore

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
            # - that value belongs to the Google Drive tool callback.
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
        base = os.getenv(
            "RUNTIME_OAUTH_BASE_URL", f"http://localhost:{os.getenv('PORT', '8200')}"
        )
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
