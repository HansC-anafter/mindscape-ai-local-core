"""Shared WordPress REST API client utilities."""

from __future__ import annotations

import os
from base64 import b64encode
from typing import Optional

import aiohttp

from backend.app.services.tools.base import ToolConnection


def _resolve_wp_client_credentials(
    connection: ToolConnection,
) -> tuple[str, str, str, Optional[str]]:
    wp_base_url = (
        connection.base_url
        or os.getenv("WORDPRESS_URL", "http://wordpress:80")
    ).rstrip("/")
    wp_username = connection.api_key or os.getenv("WORDPRESS_USERNAME", "admin")
    wp_password = (
        connection.api_secret
        or os.getenv("WORDPRESS_APPLICATION_PASSWORD", "")
    )

    if wp_username and wp_password:
        credentials = f"{wp_username}:{wp_password}"
        token = b64encode(credentials.encode()).decode()
        auth_header = f"Basic {token}"
    else:
        auth_header = None

    return wp_base_url, wp_username, wp_password, auth_header


def _init_wp_client_from_connection(connection: ToolConnection) -> tuple[str, str | None]:
    """
    Initialize WordPress REST API client from connection.

    Returns:
        Tuple of WordPress base URL and optional auth header.
    """
    wp_base_url, _, _, auth_header = _resolve_wp_client_credentials(connection)
    return wp_base_url, auth_header


def apply_wp_client_connection(target: object, connection: ToolConnection) -> None:
    """Attach resolved WordPress client fields to a tool instance."""
    wp_base_url, wp_username, wp_password, auth_header = _resolve_wp_client_credentials(
        connection
    )
    setattr(target, "wp_base_url", wp_base_url)
    setattr(target, "wp_username", wp_username)
    setattr(target, "wp_password", wp_password)
    setattr(target, "auth_header", auth_header)


async def validate_wp_connection(connection: ToolConnection) -> bool:
    """
    Validate WordPress REST API connection.

    Args:
        connection: WordPress connection configuration

    Returns:
        True if connection is valid, False otherwise
    """
    try:
        wp_base_url, auth_header = _init_wp_client_from_connection(connection)
        async with aiohttp.ClientSession() as session:
            headers = {}
            if auth_header:
                headers["Authorization"] = auth_header

            url = f"{wp_base_url}/wp-json/wp/v2"
            async with session.get(
                url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=5),
            ) as response:
                return response.status == 200
    except Exception:
        return False
