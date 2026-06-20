"""OAuth refresh helper for GCA pool runtimes."""

from __future__ import annotations

import json
import logging
import time
import urllib.parse
import urllib.request
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


def try_refresh_token(
    runtime,
    auth_service,
    token_data: dict[str, Any],
    db,
    commit_runtime_updates: Callable[..., None],
) -> Optional[str]:
    """Attempt token refresh and persist the updated runtime credentials."""
    refresh_token = token_data.get("idp_refresh_token")
    if not refresh_token:
        return None

    from backend.app.routes.core.gca_constants import (
        get_gca_client_id,
        get_gca_client_secret,
    )

    client_id = get_gca_client_id()
    client_secret = get_gca_client_secret()

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

        new_token = result.get("access_token")
        if not new_token:
            return None

        token_data["idp_access_token"] = new_token
        token_data["idp_token_expiry"] = time.time() + result.get(
            "expires_in", 3600
        )
        token_data.pop("google_client_id", None)
        token_data.pop("google_client_secret", None)

        runtime.auth_config = auth_service.encrypt_token_blob(token_data)
        runtime.auth_status = "connected"
        commit_runtime_updates(db, runtime)
        return new_token
    except Exception as e:
        logger.error("Token refresh failed for %s: %s", runtime.id, e)
        return None
