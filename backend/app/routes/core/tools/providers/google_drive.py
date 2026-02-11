"""
Google Drive tool provider routes with OAuth 2.0 support
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import RedirectResponse
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
import os
import logging

from backend.app.models.tool_registry import ToolConnectionModel
from backend.app.services.tool_registry import ToolRegistryService
from backend.app.services.tools.discovery_provider import ToolConfig
from ..base import get_tool_registry, raise_api_error
from ..utils import render_oauth_page

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/tools", tags=["tools"])


class GoogleDriveConnectionRequest(BaseModel):
    """Google Drive connection request"""
    connection_id: str
    name: str
    api_key: str = Field(..., description="Google Drive OAuth 2.0 access token")
    api_secret: Optional[str] = Field(None, description="Refresh token (optional)")


def get_oauth_manager():
    """
    Get Google Drive OAuth manager instance

    Creates a new instance each time to ensure it loads the latest configuration
    from system settings (in case settings were updated).
    """
    from backend.app.services.tools.google_drive.oauth_manager import GoogleDriveOAuthManager
    data_dir = os.getenv("DATA_DIR", "./data")
    manager = GoogleDriveOAuthManager(data_dir=data_dir)
    manager.reload_configuration()
    return manager


@router.post("/google-drive/discover", response_model=Dict[str, Any])
async def discover_google_drive_capabilities(
    request: GoogleDriveConnectionRequest,
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """
    Discover Google Drive capabilities

    Requires Google Drive OAuth 2.0 access token
    """
    try:
        config = ToolConfig(
            tool_type="google_drive",
            connection_type="oauth2",
            api_key=request.api_key,
            api_secret=request.api_secret
        )

        result = await registry.discover_tool_capabilities(
            provider_name="google_drive",
            config=config,
            connection_id=request.connection_id
        )

        return {
            "success": True,
            "connection_id": request.connection_id,
            "name": request.name,
            "discovered_tools": result.get("discovered_tools", []),
            "tools_count": len(result.get("discovered_tools", []))
        }
    except Exception as e:
        raise_api_error(500, f"Discovery failed: {str(e)}")


@router.post("/google-drive/connect", response_model=ToolConnectionModel)
async def create_google_drive_connection(
    request: GoogleDriveConnectionRequest,
    profile_id: str = Query("default-user", description="Profile ID for multi-tenant support"),
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """Create a Google Drive connection (without discovery)"""
    try:
        connection = ToolConnectionModel(
            id=request.connection_id,
            profile_id=profile_id,
            tool_type="google_drive",
            connection_type="local",
            name=request.name,
            description=f"Google Drive connection: {request.name}",
            api_key=request.api_key,
            api_secret=request.api_secret,
            oauth_token=request.api_key,
            oauth_refresh_token=request.api_secret,
            is_active=True,
            created_at=_utc_now(),
            updated_at=_utc_now()
        )
        conn = registry.create_connection(connection)
        return conn
    except Exception as e:
        raise_api_error(500, f"Failed to create connection: {str(e)}")


@router.get("/google-drive/oauth/authorize")
async def google_drive_oauth_authorize(
    connection_id: str = Query(..., description="Connection identifier"),
    connection_name: Optional[str] = Query(None, description="Connection name"),
):
    """
    Initiate Google Drive OAuth 2.0 authorization flow

    Generates a secure state token and redirects user to Google authorization page.
    """
    try:
        oauth_manager = get_oauth_manager()

        state_token = oauth_manager.generate_state_token(
            connection_id=connection_id,
            connection_name=connection_name
        )

        authorization_url = oauth_manager.build_authorization_url(state_token)

        return RedirectResponse(url=authorization_url, status_code=302)

    except ValueError as e:
        raise_api_error(500, f"OAuth configuration error: {str(e)}")
    except Exception as e:
        raise_api_error(500, f"Failed to initiate OAuth flow: {str(e)}")


@router.get("/google-drive/oauth/callback")
async def google_drive_oauth_callback(
    code: Optional[str] = Query(None, description="Authorization code from Google"),
    state: Optional[str] = Query(None, description="State token for CSRF protection"),
    error: Optional[str] = Query(None, description="Error code from OAuth provider"),
    error_description: Optional[str] = Query(None, description="Error description"),
):
    """
    Handle Google Drive OAuth 2.0 callback

    Receives authorization code from Google, exchanges it for tokens,
    and automatically discovers and registers tools.
    """
    if error:
        error_msg = error_description or error
        logger.error(f"Google OAuth error: {error} - {error_msg}")
        return render_oauth_page(
            success=False,
            message=error_msg,
            meta={"error": error, "status_code": 400}
        )

    if not code or not state:
        return render_oauth_page(
            success=False,
            message="Missing authorization code or state parameter.",
            meta={"error": "Missing parameters", "status_code": 400}
        )

    try:
        from ..base import get_tool_registry as _get_tool_registry
        oauth_manager = get_oauth_manager()
        registry = _get_tool_registry()

        state_data = oauth_manager.validate_state_token(state)
        if not state_data:
            raise_api_error(400, "Invalid or expired state token")

        connection_id = state_data["connection_id"]
        connection_name = state_data.get("connection_name") or f"Google Drive - {connection_id}"

        token_data = await oauth_manager.exchange_code_for_tokens(code)

        access_token = token_data["access_token"]
        refresh_token = token_data.get("refresh_token")

        config = ToolConfig(
            tool_type="google_drive",
            connection_type="oauth2",
            api_key=access_token,
            api_secret=refresh_token
        )

        result = await registry.discover_tool_capabilities(
            provider_name="google_drive",
            config=config,
            connection_id=connection_id
        )

        tools_count = len(result.get("discovered_tools", []))

        return render_oauth_page(
            success=True,
            message=f"Discovered {tools_count} tool(s) from Google Drive.",
            meta={
                "connection_id": connection_id,
                "tools_count": tools_count
            }
        )

    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"OAuth callback error: {e}")
        return render_oauth_page(
            success=False,
            message=str(e),
            meta={"error": str(e), "status_code": 400}
        )
    except Exception as e:
        logger.error(f"Unexpected error in OAuth callback: {e}", exc_info=True)
        return render_oauth_page(
            success=False,
            message="An unexpected error occurred. Please try again.",
            meta={"error": "Unexpected error", "status_code": 500}
        )

