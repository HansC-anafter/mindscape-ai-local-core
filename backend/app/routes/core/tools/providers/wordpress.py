"""
WordPress tool provider routes
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Dict, Any
from pydantic import BaseModel
from datetime import datetime

from backend.app.models.tool_registry import ToolConnectionModel
from backend.app.services.tool_registry import ToolRegistryService
from ..base import get_tool_registry, raise_api_error

router = APIRouter(prefix="/api/v1/tools", tags=["tools"])


class WordPressConnectionRequest(BaseModel):
    """WordPress-specific connection request (backward compatibility)"""
    connection_id: str
    name: str
    wp_url: str
    wp_username: str
    wp_application_password: str


@router.post("/wordpress/discover", response_model=Dict[str, Any])
async def discover_wordpress_capabilities(
    request: WordPressConnectionRequest,
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """
    Discover WordPress capabilities (backward compatibility endpoint)

    Note: This is a legacy endpoint kept for backward compatibility.
    New code should use POST /api/tools/discover endpoint.

    This endpoint:
    1. Connects to WordPress site
    2. Discovers available capabilities (via plugin or fallback)
    3. Registers them as tools in the registry
    """
    try:
        result = await registry.discover_wordpress_capabilities(
            connection_id=request.connection_id,
            wp_url=request.wp_url,
            wp_username=request.wp_username,
            wp_password=request.wp_application_password,
        )
        return result
    except Exception as e:
        raise_api_error(500, f"Discovery failed: {str(e)}")


@router.post("/wordpress/connect", response_model=ToolConnectionModel)
async def create_wordpress_connection(
    request: WordPressConnectionRequest,
    profile_id: str = Query("default-user", description="Profile ID for multi-tenant support"),
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """Create a WordPress connection (without discovery)"""
    try:
        # Use legacy method for WordPress (maintains backward compatibility)
        conn = registry.create_connection_legacy(
            connection_id=request.connection_id,
            name=request.name,
            wp_url=request.wp_url,
            wp_username=request.wp_username,
            wp_application_password=request.wp_application_password,
            profile_id=profile_id
        )
        return conn
    except Exception as e:
        raise_api_error(500, f"Failed to create connection: {str(e)}")

