"""
Configuration helpers for the cloud connector.
"""

import logging
import os
import uuid
from typing import Optional

logger = logging.getLogger(__name__)


def resolve_cloud_base_url() -> Optional[str]:
    """
    Read execution-control base URL from RuntimeEnvironment DB.

    Falls back to explicit environment overrides. Returns None if not configured.
    """
    try:
        from app.database import get_db_postgres
        from app.models.runtime_environment import RuntimeEnvironment

        db = next(get_db_postgres())
        try:
            runtime = (
                db.query(RuntimeEnvironment)
                .filter(
                    RuntimeEnvironment.id == "site-hub",
                    RuntimeEnvironment.supports_dispatch.is_(True),
                    RuntimeEnvironment.config_url.isnot(None),
                    RuntimeEnvironment.config_url != "",
                )
                .order_by(RuntimeEnvironment.updated_at.desc())
                .first()
            )
            if not runtime:
                runtime = (
                    db.query(RuntimeEnvironment)
                    .filter(
                        RuntimeEnvironment.supports_dispatch.is_(True),
                        RuntimeEnvironment.config_url.isnot(None),
                        RuntimeEnvironment.config_url != "",
                        RuntimeEnvironment.auth_type == "oauth2",
                    )
                    .order_by(
                        RuntimeEnvironment.recommended_for_dispatch.desc(),
                        RuntimeEnvironment.is_default.desc(),
                        RuntimeEnvironment.updated_at.desc(),
                    )
                    .first()
                )
            if runtime and runtime.config_url:
                logger.debug(
                    "Cloud base URL from DB runtime %s: %s",
                    runtime.id,
                    runtime.config_url,
                )
                return runtime.config_url.rstrip("/")
        finally:
            db.close()
    except Exception as e:
        logger.debug("Could not read cloud URL from DB: %s", e)

    return None


def resolve_execution_control_base_url() -> Optional[str]:
    """Resolve execution-control base URL from env or RuntimeEnvironment."""
    return (
        os.getenv("EXECUTION_CONTROL_API_URL")
        or os.getenv("SITE_HUB_API_URL")
        or os.getenv("CLOUD_API_URL")
        or resolve_cloud_base_url()
    )


def resolve_ws_url() -> str:
    """
    Resolve WebSocket URL: explicit env, derived base URL, then empty fallback.
    """
    env_ws = (
        os.getenv("EXECUTION_CONTROL_WS_URL")
        or os.getenv("SITE_HUB_WS_URL")
        or os.getenv("CLOUD_WS_URL")
    )
    if env_ws:
        return env_ws

    base = resolve_execution_control_base_url()
    if base:
        scheme = "wss" if base.startswith("https") else "ws"
        host = base.split("://", 1)[-1]
        return f"{scheme}://{host}/api/v1/executor/ws"

    logger.warning(
        "Execution-control WS URL not configured. "
        "Set Runtime Environments config_url or "
        "EXECUTION_CONTROL_WS_URL / SITE_HUB_WS_URL / CLOUD_WS_URL."
    )
    return ""


def get_or_create_device_id() -> str:
    """
    Get or create device ID.

    Returns:
        Device identifier
    """
    device_id_file = os.path.expanduser("~/.mindscape/device_id")
    os.makedirs(os.path.dirname(device_id_file), exist_ok=True)

    if os.path.exists(device_id_file):
        with open(device_id_file, "r") as f:
            return f.read().strip()

    device_id = f"device_{uuid.uuid4().hex[:16]}"
    with open(device_id_file, "w") as f:
        f.write(device_id)
    return device_id
