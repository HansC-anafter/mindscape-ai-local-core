"""
Google Sheets tool provider routes with OAuth support

Reuses Google Drive OAuth configuration for authentication.
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime
import logging
import os

from backend.app.models.tool_registry import ToolConnectionModel
from backend.app.services.tool_registry import ToolRegistryService
from backend.app.services.tools.discovery_provider import ToolConfig
from ..base import get_tool_registry, raise_api_error

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/tools", tags=["tools"])


class GoogleSheetsConnectionRequest(BaseModel):
    """Google Sheets connection request"""
    connection_id: str
    name: str
    api_key: Optional[str] = Field(None, description="Google OAuth access token (if already obtained)")
    reuse_google_drive_oauth: bool = Field(True, description="Reuse Google Drive OAuth if available")


@router.post("/google-sheets/discover", response_model=Dict[str, Any])
async def discover_google_sheets_capabilities(
    request: GoogleSheetsConnectionRequest,
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """
    Discover Google Sheets capabilities using discovery provider

    Uses the new architecture ToolRegistryService with GoogleSheetsDiscoveryProvider.
    Can reuse Google Drive OAuth token if available.

    Example:
        POST /api/v1/tools/google-sheets/discover
        {
            "connection_id": "google-sheets-1",
            "name": "My Google Sheets",
            "api_key": "ya29...",
            "reuse_google_drive_oauth": true
        }
    """
    try:
        access_token = request.api_key

        # Try to reuse Google Drive OAuth if not provided and reuse is enabled
        if not access_token and request.reuse_google_drive_oauth:
            google_drive_connections = registry.get_connections_by_tool_type("default-user", "google_drive")
            if google_drive_connections:
                active_connection = next(
                    (conn for conn in google_drive_connections if conn.is_active and conn.oauth_token),
                    None
                )
                if active_connection:
                    access_token = active_connection.oauth_token
                    logger.info(f"Reusing Google Drive OAuth token for Google Sheets connection: {request.connection_id}")

        if not access_token:
            raise ValueError("Google Sheets access token is required. Provide api_key or enable reuse_google_drive_oauth with an active Google Drive connection.")

        config = ToolConfig(
            tool_type="google_sheets",
            connection_type="oauth2",
            api_key=access_token
        )

        result = await registry.discover_tool_capabilities(
            provider_name="google_sheets",
            config=config,
            connection_id=request.connection_id
        )

        return {
            "success": True,
            "connection_id": request.connection_id,
            "name": request.name,
            "discovered_tools": result.get("discovered_tools", []),
            "tools_count": len(result.get("discovered_tools", [])),
            "oauth_reused": not request.api_key and request.reuse_google_drive_oauth
        }
    except Exception as e:
        logger.error(f"Google Sheets discovery failed: {e}", exc_info=True)
        raise_api_error(500, f"Discovery failed: {str(e)}")


@router.post("/google-sheets/connect", response_model=ToolConnectionModel)
async def create_google_sheets_connection(
    request: GoogleSheetsConnectionRequest,
    profile_id: str = Query("default-user", description="Profile ID for multi-tenant support"),
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """
    Create a Google Sheets connection

    Supports reusing Google Drive OAuth token if available.
    """
    try:
        access_token = request.api_key

        # Try to reuse Google Drive OAuth if not provided and reuse is enabled
        if not access_token and request.reuse_google_drive_oauth:
            google_drive_connections = registry.get_connections_by_tool_type(profile_id, "google_drive")
            if google_drive_connections:
                active_connection = next(
                    (conn for conn in google_drive_connections if conn.is_active and conn.oauth_token),
                    None
                )
                if active_connection:
                    access_token = active_connection.oauth_token
                    logger.info(f"Reusing Google Drive OAuth token for Google Sheets connection: {request.connection_id}")

        if not access_token:
            raise ValueError("Google Sheets access token is required. Provide api_key or enable reuse_google_drive_oauth with an active Google Drive connection.")

        # Create ToolConnectionModel instance
        connection = ToolConnectionModel(
            id=request.connection_id,
            profile_id=profile_id,
            tool_type="google_sheets",
            connection_type="local",
            name=request.name,
            description=f"Google Sheets connection: {request.name}",
            api_key=access_token,
            oauth_token=access_token,
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        # Create connection in registry
        conn_model = registry.create_connection(connection)

        # Register tools
        try:
            from backend.app.services.tools.base import ToolConnection
            from backend.app.services.tools.registry import register_google_sheets_tools

            tool_connection = ToolConnection(
                id=conn_model.id,
                tool_type="google_sheets",
                connection_type="local",
                api_key=access_token,
                oauth_token=access_token,
                name=conn_model.name
            )
            tools = register_google_sheets_tools(tool_connection)
            logger.info(f"Registered {len(tools)} Google Sheets tools for connection: {request.connection_id}")
        except ImportError:
            logger.warning("Google Sheets tools registration not available, skipping tool registration")

        return conn_model
    except Exception as e:
        logger.error(f"Failed to create Google Sheets connection: {e}", exc_info=True)
        raise_api_error(500, f"Failed to create connection: {str(e)}")


@router.get("/google-sheets/oauth/authorize")
async def google_sheets_oauth_authorize(
    connection_id: str = Query(..., description="Connection ID"),
    connection_name: Optional[str] = Query(None, description="Connection name"),
):
    """
    Initiate Google Sheets OAuth authorization flow

    Reuses Google Drive OAuth manager and configuration.
    Redirects user to Google authorization page.
    """
    try:
        from backend.app.services.tools.google_drive.oauth_manager import get_oauth_manager
        oauth_manager = get_oauth_manager()

        state_token = oauth_manager.generate_state_token(
            connection_id=connection_id,
            connection_name=connection_name
        )

        # Add Sheets API scope to existing scopes
        scopes = [
            "https://www.googleapis.com/auth/drive.readonly",
            "https://www.googleapis.com/auth/spreadsheets"
        ]

        authorization_url = oauth_manager.build_authorization_url(state_token, scopes)

        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=authorization_url, status_code=302)
    except Exception as e:
        logger.error(f"Failed to initiate Google Sheets OAuth flow: {e}", exc_info=True)
        raise_api_error(500, f"Failed to initiate OAuth flow: {str(e)}")


@router.get("/google-sheets/oauth/callback")
async def google_sheets_oauth_callback(
    code: Optional[str] = Query(None, description="Authorization code from Google"),
    state: Optional[str] = Query(None, description="State token for CSRF protection"),
    error: Optional[str] = Query(None, description="Error code from OAuth provider"),
):
    """
    Handle Google Sheets OAuth callback

    Reuses Google Drive OAuth manager to exchange code for tokens.
    """
    if error:
        raise_api_error(400, f"OAuth error: {error}")

    if not code or not state:
        raise_api_error(400, "Missing authorization code or state parameter")

    try:
        from backend.app.services.tools.google_drive.oauth_manager import get_oauth_manager
        from ..base import get_tool_registry as _get_tool_registry
        oauth_manager = get_oauth_manager()
        registry = _get_tool_registry()

        state_data = oauth_manager.validate_state_token(state)
        if not state_data:
            raise_api_error(400, "Invalid or expired state token")

        connection_id = state_data["connection_id"]
        connection_name = state_data.get("connection_name") or f"Google Sheets - {connection_id}"

        token_data = await oauth_manager.exchange_code_for_tokens(code)

        access_token = token_data["access_token"]
        refresh_token = token_data.get("refresh_token")

        # Create connection
        connection_model = ToolConnectionModel(
            id=connection_id or "google-sheets-oauth-1",
            profile_id="default-user",
            tool_type="google_sheets",
            connection_type="local",
            name=connection_name,
            description="Google Sheets OAuth connection",
            api_key=access_token,
            oauth_token=access_token,
            oauth_refresh_token=refresh_token,
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        connection = registry.create_connection(connection_model)

        # Register tools
        try:
            from backend.app.services.tools.registry import register_google_sheets_tools
            from backend.app.services.tools.base import ToolConnection

            tool_connection = ToolConnection(
                id=connection.id,
                tool_type="google_sheets",
                connection_type="local",
                api_key=access_token,
                oauth_token=access_token,
                name=connection.name
            )
            tools = register_google_sheets_tools(tool_connection)
            logger.info(f"Registered {len(tools)} Google Sheets tools via OAuth")
        except ImportError:
            logger.warning("Google Sheets tools registration not available")

        # Redirect to frontend with success
        from fastapi.responses import RedirectResponse
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3001")
        redirect_url = f"{frontend_url}/settings?tool=google_sheets&connected=true"
        return RedirectResponse(url=redirect_url)
    except Exception as e:
        logger.error(f"Failed to handle Google Sheets OAuth callback: {e}", exc_info=True)
        raise_api_error(500, f"Failed to handle OAuth callback: {str(e)}")


@router.post("/google-sheets/validate", response_model=Dict[str, Any])
async def validate_google_sheets_connection(
    connection_id: str,
    profile_id: str = Query("default-user", description="Profile ID"),
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """
    Validate Google Sheets connection

    Tests if the Google Sheets API connection is working by calling spreadsheets.get.
    """
    try:
        connection_model = registry.get_connection(connection_id=connection_id, profile_id=profile_id)
        if not connection_model:
            raise_api_error(404, f"Google Sheets connection not found: {connection_id}")

        access_token = connection_model.oauth_token or connection_model.api_key
        if not access_token:
            raise_api_error(400, "No access token found in connection")

        # Test connection by calling a simple API endpoint
        import aiohttp
        url = "https://www.googleapis.com/drive/v3/files"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        params = {
            "q": "mimeType='application/vnd.google-apps.spreadsheet'",
            "pageSize": 1
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Google Sheets API error: {response.status} - {error_text}")

                result = await response.json()

                # Update connection validation status
                registry.update_validation_status(
                    connection_id=connection_id,
                    profile_id=profile_id,
                    is_valid=True,
                    error_message=None
                )

                return {
                    "success": True,
                    "valid": True,
                    "spreadsheets_count": len(result.get("files", [])),
                    "message": "Google Sheets connection is valid"
                }
    except Exception as e:
        logger.error(f"Failed to validate Google Sheets connection: {e}", exc_info=True)
        raise_api_error(500, f"Failed to validate connection: {str(e)}")

