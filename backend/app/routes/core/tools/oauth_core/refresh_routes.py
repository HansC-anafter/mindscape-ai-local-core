import os

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from backend.app.services.tool_registry import ToolRegistryService

from ..base import get_tool_registry, raise_api_error
from .state import OAUTH_CONFIGS, _utc_now, logger

router = APIRouter()

@router.post("/{provider}/refresh")
async def refresh_token(
    provider: str,
    connection_id: str = Query(..., description="Connection ID"),
    profile_id: str = Query(..., description="Profile ID"),
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """
    Refresh OAuth access token

    Args:
        provider: Social media platform
        connection_id: Connection ID
        profile_id: Profile ID
        registry: Tool registry service

    Returns:
        Updated token information
    """
    if provider not in OAUTH_CONFIGS:
        raise_api_error(400, f"Unsupported provider: {provider}")

    # Get connection
    connection = registry.get_connection(connection_id, profile_id)
    if not connection:
        raise_api_error(404, "Connection not found")

    if not connection.oauth_refresh_token:
        raise_api_error(400, "No refresh token available for this connection")

    config = OAUTH_CONFIGS[provider]
    client_id = os.getenv(config["client_id_env"])
    client_secret = os.getenv(config["client_secret_env"])

    if not client_id or not client_secret:
        raise_api_error(
            500,
            f"OAuth credentials not configured. Please set {config['client_id_env']} and {config['client_secret_env']} environment variables."
        )

    # Refresh token
    try:
        refresh_data = {
            "grant_type": "refresh_token",
            "refresh_token": connection.oauth_refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                config["token_url"],
                data=refresh_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Token refresh failed: {response.text}"
                )

            token_response = response.json()
            new_access_token = token_response.get("access_token") or token_response.get("accessToken")
            new_refresh_token = token_response.get("refresh_token") or token_response.get("refreshToken")

            # Update connection
            connection.oauth_token = new_access_token
            if new_refresh_token:
                connection.oauth_refresh_token = new_refresh_token
            connection.last_validated_at = _utc_now()
            registry.update_connection(connection)

            return {
                "access_token": new_access_token,
                "refresh_token": new_refresh_token,
                "expires_in": token_response.get("expires_in"),
            }

    except Exception as e:
        logger.error(f"Failed to refresh token for {provider}: {str(e)}")
        raise_api_error(500, f"Token refresh failed: {str(e)}")
