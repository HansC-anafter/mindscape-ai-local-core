"""
Authentication helpers for the cloud connector.
"""

import logging
import os

logger = logging.getLogger(__name__)


async def get_device_token() -> str:
    """
    Get device token for WebSocket authentication.

    Token resolution order:
    1. CLOUD_PROVIDER_TOKEN / CLOUD_API_TOKEN environment variable
    2. OAuth access_token from the cloud provider runtime in the database
    3. Raise ValueError if no valid token is available

    Returns:
        Access token for WebSocket authentication
    """
    user_token = os.getenv("CLOUD_PROVIDER_TOKEN") or os.getenv("CLOUD_API_TOKEN")

    if not user_token:
        user_token = await get_runtime_oauth_token()

    if not user_token:
        logger.error(
            "No auth token available for CloudConnector. "
            "Set CLOUD_PROVIDER_TOKEN / CLOUD_API_TOKEN env var, "
            "or connect an OAuth runtime in the database."
        )
        raise ValueError(
            "CloudConnector requires authentication. "
            "No OAuth token available (env vars not set, "
            "runtime OAuth token not found)."
        )

    logger.info("Using OAuth token for CloudConnector WebSocket authentication")
    return user_token


async def get_runtime_oauth_token() -> str | None:
    """
    Read OAuth access_token from a connected OAuth runtime in DB.

    Uses RuntimeAuthService.get_auth_headers() which handles automatic
    refresh of expired tokens using refresh_token grants.

    Returns:
        Access token string, or None if unavailable.
    """
    try:
        from app.database import get_db_postgres
        from app.models.runtime_environment import RuntimeEnvironment
        from app.services.runtime_auth_service import RuntimeAuthService

        db = next(get_db_postgres())
        try:
            runtimes = (
                db.query(RuntimeEnvironment)
                .filter(
                    RuntimeEnvironment.auth_type == "oauth2",
                    RuntimeEnvironment.auth_status.in_(["connected", "expired"]),
                )
                .all()
            )
            if not runtimes:
                logger.debug("No connected OAuth runtimes found in DB")
                return None

            svc = RuntimeAuthService()

            for runtime in runtimes:
                if not runtime.auth_config:
                    continue
                try:
                    headers = await svc.get_auth_headers(runtime, db)
                    auth_header = headers.get("Authorization", "")
                    if auth_header.startswith("Bearer "):
                        access_token = auth_header[7:]
                        logger.info(
                            "Retrieved OAuth token (with auto-refresh) from runtime %s",
                            runtime.id,
                        )
                        return access_token
                except Exception as e:
                    logger.warning(
                        "Failed to get valid token from runtime %s: %s",
                        runtime.id,
                        e,
                    )
            logger.debug("All connected runtimes have empty access_token")
            return None
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"Failed to read runtime OAuth token: {e}")
        return None
