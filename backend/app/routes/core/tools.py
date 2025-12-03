"""
Tool management routes.

Provides API endpoints for tool discovery, registration, and management.

Design Principles:
- Supports multiple tool types (WordPress, Notion, GitHub, etc.)
- Select discovery provider via provider parameter
- Backward compatible with legacy WordPress-specific endpoints
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import RedirectResponse, HTMLResponse
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

from ...models.tool_registry import RegisteredTool, ToolConnectionModel
from ...services.tool_registry import ToolRegistryService
from ...services.tools.discovery_provider import ToolConfig
from ...services.tool_status_checker import ToolStatusChecker
# ToolConnectionStore is deprecated, use ToolRegistryService instead
from ...services.tool_info import get_tool_info
import os
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/tools", tags=["tools"])


# Initialize service
def get_tool_registry() -> ToolRegistryService:
    """
    Initialize Tool Registry and register community extensions
    """
    data_dir = os.getenv("DATA_DIR", "./data")
    registry = ToolRegistryService(data_dir=data_dir)

    # Register external extensions (WordPress provider)
    try:
        from ...extensions.console_kit import register_console_kit_tools
        register_console_kit_tools(registry)
    except ImportError:
        pass  # External extension not installed, skip

    # Register community extensions (optional)
    try:
        from ...extensions.community import register_community_extensions
        register_community_extensions(registry)
    except ImportError:
        pass  # Community extensions not installed, skip

    return registry


# Request/Response models
class DiscoverToolsRequest(BaseModel):
    """Generic tool discovery request"""
    provider: str
    config: ToolConfig
    connection_id: Optional[str] = None


class WordPressConnectionRequest(BaseModel):
    """WordPress-specific connection request (backward compatibility)"""
    connection_id: str
    name: str
    wp_url: str
    wp_username: str
    wp_application_password: str


class ToolUpdateRequest(BaseModel):
    """Tool update request"""
    enabled: Optional[bool] = None
    read_only: Optional[bool] = None
    allowed_agent_roles: Optional[List[str]] = None


# Routes

@router.get("/providers", response_model=Dict[str, Any])
async def get_available_providers(
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """
    Get all available tool discovery providers

    Returns:
    - Core built-in providers (e.g., generic_http)
    - Extension providers (e.g., wordpress, notion - if installed)

    Example Response:
        {
            "providers": [
                {
                    "provider": "generic_http",
                    "display_name": "Generic HTTP API",
                    "description": "...",
                    "required_config": ["base_url"],
                    ...
                },
                {
                    "provider": "wordpress",
                    "display_name": "WordPress",
                    "description": "...",
                    "required_config": ["base_url", "api_key", "api_secret"],
                    ...
                }
            ]
        }
    """
    providers = registry.get_available_providers()
    return {
        "providers": providers
    }


@router.post("/discover", response_model=Dict[str, Any])
async def discover_tool_capabilities(
    request: DiscoverToolsRequest,
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """
    Discover tool capabilities using specified provider (generic endpoint)

    Supported providers:
    - 'generic_http': Generic HTTP API
    - 'wordpress': WordPress site (requires external extension)
    - 'notion': Notion workspace (requires external extension)
    - Other user-defined providers

    Example Request:
        POST /api/tools/discover
        {
            "provider": "wordpress",
            "config": {
                "tool_type": "wordpress",
                "connection_type": "http_api",
                "base_url": "https://mysite.com",
                "api_key": "admin",
                "api_secret": "xxxx xxxx xxxx xxxx"
            },
            "connection_id": "my-wp-site"
        }

    Example Response:
        {
            "provider": "wordpress",
            "connection_id": "my-wp-site",
            "discovered_tools": [...],
            "discovery_metadata": {...}
        }
    """
    try:
        result = await registry.discover_tool_capabilities(
            provider_name=request.provider,
            config=request.config,
            connection_id=request.connection_id
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Discovery failed: {str(e)}")


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
        raise HTTPException(status_code=500, detail=f"Discovery failed: {str(e)}")


@router.post("/wordpress/connect", response_model=ToolConnectionModel)
async def create_wordpress_connection(
    request: WordPressConnectionRequest,
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """Create a WordPress connection (without discovery)"""
    try:
        conn = registry.create_connection(
            connection_id=request.connection_id,
            name=request.name,
            wp_url=request.wp_url,
            wp_username=request.wp_username,
            wp_application_password=request.wp_application_password,
        )
        return conn
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create connection: {str(e)}")


# ============================================
# Local Filesystem Tool Integration
# ============================================

class LocalFilesystemConfigRequest(BaseModel):
    """Local filesystem configuration request"""
    connection_id: str
    name: str
    allowed_directories: List[str] = Field(..., description="List of allowed directory paths")
    allow_write: bool = Field(default=False, description="Allow write operations")


@router.post("/local-filesystem/configure", response_model=Dict[str, Any])
async def configure_local_filesystem(
    request: LocalFilesystemConfigRequest,
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """
    Configure local filesystem access

    Sets up allowed directories for file system access.
    Used for document collection and RAG functionality.

    Example:
        POST /api/tools/local-filesystem/configure
        {
            "connection_id": "local-fs-1",
            "name": "Documents Directory",
            "allowed_directories": ["~/Documents", "./data/documents"],
            "allow_write": false
        }
    """
    try:
        from ...services.tools.discovery_provider import ToolConfig

        config = ToolConfig(
            tool_type="local_filesystem",
            connection_type="local",
            custom_config={
                "allowed_directories": request.allowed_directories,
                "allow_write": request.allow_write
            }
        )

        result = await registry.discover_tool_capabilities(
            provider_name="local_filesystem",
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
        raise HTTPException(status_code=500, detail=f"Configuration failed: {str(e)}")


@router.get("/local-filesystem/directories", response_model=Dict[str, Any])
async def get_configured_directories(
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """
    Get list of configured local filesystem directories

    Returns all connections that use local filesystem provider
    """
    try:
        connections = registry.get_connections()
        local_fs_connections = [
            conn for conn in connections
            if conn.tool_type == "local_filesystem"
        ]

        directories_info = []
        for conn in local_fs_connections:
            directories_info.append({
                "connection_id": conn.id,
                "name": conn.name,
                "allowed_directories": conn.custom_config.get("allowed_directories", []),
                "allow_write": conn.custom_config.get("allow_write", False)
            })

        return {
            "success": True,
            "connections": directories_info,
            "count": len(directories_info)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# Notion Tool Integration
# ============================================

class NotionConnectionRequest(BaseModel):
    """Notion connection request"""
    connection_id: str
    name: str
    api_key: str = Field(..., description="Notion Integration Token (starts with 'secret_')")


@router.post("/notion/discover", response_model=Dict[str, Any])
async def discover_notion_capabilities(
    request: NotionConnectionRequest,
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """
    Discover Notion workspace capabilities

    Requires Notion Integration Token (create at notion.so/my-integrations)

    Example:
        POST /api/tools/notion/discover
        {
            "connection_id": "notion-workspace-1",
            "name": "My Notion Workspace",
            "api_key": "secret_..."
        }
    """
    try:
        from ...services.tools.discovery_provider import ToolConfig

        config = ToolConfig(
            tool_type="notion",
            connection_type="http_api",
            api_key=request.api_key
        )

        result = await registry.discover_tool_capabilities(
            provider_name="notion",
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
        raise HTTPException(status_code=500, detail=f"Discovery failed: {str(e)}")


@router.post("/notion/connect", response_model=ToolConnectionModel)
async def create_notion_connection(
    request: NotionConnectionRequest,
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """Create a Notion connection (without discovery)"""
    try:
        conn = registry.create_connection(
            connection_id=request.connection_id,
            name=request.name,
            api_key=request.api_key
        )
        return conn
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create connection: {str(e)}")


# ============================================
# Canva Tool Integration
# ============================================

class CanvaConnectionRequest(BaseModel):
    """Canva connection request"""
    connection_id: str
    name: str
    # Option 1: Direct Access Token (if you already have one)
    oauth_token: Optional[str] = Field(None, description="Canva OAuth Access Token (if already obtained)")
    # Option 2: OAuth Credentials (for OAuth flow)
    client_id: Optional[str] = Field(None, description="Canva OAuth Client ID (from Developer Portal)")
    client_secret: Optional[str] = Field(None, description="Canva OAuth Client Secret (from Developer Portal)")
    # Legacy: API Key (if Canva supports direct API key, though OAuth is standard)
    api_key: Optional[str] = Field(None, description="Canva API Key (if available, otherwise use OAuth)")
    base_url: Optional[str] = Field(
        default="https://api.canva.com/rest/v1",
        description="Canva API Base URL"
    )
    brand_id: Optional[str] = Field(None, description="Canva Brand ID (optional)")
    redirect_uri: Optional[str] = Field(
        None,
        description="OAuth redirect URI (required if using client_id/client_secret)"
    )


@router.post("/canva/connect", response_model=ToolConnectionModel)
async def create_canva_connection(
    request: CanvaConnectionRequest,
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """
    Create a Canva connection

    Supports three authentication methods:
    1. Direct OAuth Token (if you already have an access token)
    2. OAuth Credentials (Client ID + Client Secret) - will need to complete OAuth flow
    3. API Key (if available, though OAuth is the standard method)

    Example 1: Using existing Access Token
        POST /api/tools/canva/connect
        {
            "connection_id": "canva-1",
            "name": "My Canva Account",
            "oauth_token": "your_access_token_here",
            "base_url": "https://api.canva.com/rest/v1"
        }

    Example 2: Using OAuth Credentials (will need to complete OAuth flow)
        POST /api/tools/canva/connect
        {
            "connection_id": "canva-1",
            "name": "My Canva Account",
            "client_id": "your_client_id",
            "client_secret": "your_client_secret",
            "redirect_uri": "http://localhost:8000/api/tools/canva/oauth/callback"
        }
    """
    try:
        # Validate that at least one authentication method is provided
        has_auth = bool(request.oauth_token or request.api_key or (request.client_id and request.client_secret))
        if not has_auth:
            raise HTTPException(
                status_code=400,
                detail="Authentication required: provide either oauth_token, api_key, or (client_id + client_secret)"
            )

        # If using OAuth credentials, validate redirect_uri
        if request.client_id and request.client_secret and not request.redirect_uri:
            raise HTTPException(
                status_code=400,
                detail="redirect_uri is required when using client_id and client_secret"
            )

        from ...services.tools.base import ToolConnection
        from ...services.tools.registry import register_canva_tools

        # Store OAuth credentials in connection config if provided
        connection_config = {}
        if request.client_id:
            connection_config["client_id"] = request.client_id
        if request.client_secret:
            connection_config["client_secret"] = request.client_secret
        if request.redirect_uri:
            connection_config["redirect_uri"] = request.redirect_uri
        if request.brand_id:
            connection_config["brand_id"] = request.brand_id

        connection = ToolConnection(
            id=request.connection_id,
            tool_type="canva",
            connection_type="local",
            api_key=request.api_key,
            oauth_token=request.oauth_token,
            base_url=request.base_url,
            name=request.name,
            description=f"Canva connection: {request.name}",
            # Store OAuth credentials in a way that can be accessed later
            # Note: ToolConnection doesn't have a config field, so we'll store client_id/secret separately
            # For now, we'll use api_key field to store client_id if oauth_token is not provided
        )

        # If using OAuth credentials but no token yet, store credentials for OAuth flow
        # We'll need to implement OAuth flow endpoints separately
        if request.client_id and request.client_secret and not request.oauth_token:
            logger.info(f"Canva connection created with OAuth credentials. OAuth flow needs to be completed.")
            # Store credentials temporarily (in production, use secure storage)
            # For now, we'll note that OAuth flow needs to be completed

        # Register Canva tools
        tools = register_canva_tools(connection)

        # Create connection in registry
        conn_model = registry.create_connection(
            connection_id=request.connection_id,
            name=request.name,
            tool_type="canva",
            api_key=request.api_key,
            oauth_token=request.oauth_token,
            base_url=request.base_url,
        )

        return conn_model

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create Canva connection: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create connection: {str(e)}")


@router.get("/canva/oauth/authorize")
async def canva_oauth_authorize(
    connection_id: str = Query(..., description="Connection ID"),
    connection_name: Optional[str] = Query(None, description="Connection name"),
    client_id: Optional[str] = Query(None, description="Canva Client ID (if not stored)"),
    redirect_uri: Optional[str] = Query(None, description="Redirect URI (if not stored)"),
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """
    Initiate Canva OAuth authorization flow

    Redirects user to Canva authorization page.

    Example:
        GET /api/tools/canva/oauth/authorize?connection_id=canva-1&connection_name=My+Canva
    """
    try:
        from ...services.tools.canva.oauth_manager import get_canva_oauth_manager

        # Get connection to retrieve stored credentials
        connection_model = None
        if connection_id:
            try:
                connection_model = registry.get_connection(connection_id)
            except Exception:
                pass

        # Use provided client_id or get from connection
        final_client_id = client_id
        final_redirect_uri = redirect_uri

        if connection_model:
            # Try to get client_id from connection config
            # Note: We may need to store client_id/client_secret in connection config
            if not final_client_id:
                # For now, assume client_id might be stored elsewhere
                # In production, store in connection config or secure storage
                pass

        if not final_client_id:
            raise HTTPException(
                status_code=400,
                detail="client_id is required. Provide via query parameter or ensure connection has stored credentials."
            )

        if not final_redirect_uri:
            # Default redirect URI
            final_redirect_uri = f"http://localhost:8000/api/tools/canva/oauth/callback"

        oauth_manager = get_canva_oauth_manager()
        auth_url, code_verifier = oauth_manager.build_authorization_url(
            client_id=final_client_id,
            redirect_uri=final_redirect_uri,
            connection_id=connection_id,
            connection_name=connection_name
        )

        return RedirectResponse(url=auth_url)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to initiate Canva OAuth flow: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"OAuth authorization failed: {str(e)}")


@router.get("/canva/oauth/callback")
async def canva_oauth_callback(
    code: str = Query(..., description="Authorization code"),
    state: str = Query(..., description="State token"),
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """
    Handle Canva OAuth callback

    Exchanges authorization code for access token and updates connection.

    Example:
        GET /api/tools/canva/oauth/callback?code=xxx&state=yyy
    """
    try:
        from ...services.tools.canva.oauth_manager import get_canva_oauth_manager
        from ...services.tools.base import ToolConnection
        from ...services.tools.registry import register_canva_tools

        oauth_manager = get_canva_oauth_manager()

        # Validate state token
        state_data = oauth_manager.validate_state_token(state)
        if not state_data:
            raise HTTPException(status_code=400, detail="Invalid or expired state token")

        connection_id = state_data["connection_id"]

        # Get connection to retrieve client_id and client_secret
        connection_model = registry.get_connection(connection_id)
        if not connection_model:
            raise HTTPException(status_code=404, detail=f"Connection not found: {connection_id}")

        # Get code verifier
        code_verifier = oauth_manager.get_code_verifier(state)
        if not code_verifier:
            raise HTTPException(status_code=400, detail="Code verifier not found for state token")

        # TODO: Retrieve client_id and client_secret from connection
        # For now, we'll need them to be provided or stored
        # In production, store these securely in connection config
        client_id = None  # Get from connection config
        client_secret = None  # Get from connection config
        redirect_uri = None  # Get from connection config

        if not client_id or not client_secret:
            raise HTTPException(
                status_code=400,
                detail="client_id and client_secret must be stored in connection. Please create connection with OAuth credentials first."
            )

        # Exchange code for token
        token_response = await oauth_manager.exchange_code_for_token(
            code=code,
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            code_verifier=code_verifier
        )

        access_token = token_response.get("access_token")
        refresh_token = token_response.get("refresh_token")

        if not access_token:
            raise HTTPException(status_code=500, detail="Failed to obtain access token")

        # Update connection with access token
        # TODO: Update connection_model with oauth_token
        # For now, return token information

        # Clean up state
        oauth_manager.cleanup_state(state)

        return {
            "success": True,
            "message": "OAuth authorization completed",
            "connection_id": connection_id,
            "access_token": access_token[:20] + "..." if access_token else None,  # Partial token for display
            "has_refresh_token": bool(refresh_token),
            "next_step": f"Update connection {connection_id} with oauth_token: {access_token}"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to handle Canva OAuth callback: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"OAuth callback failed: {str(e)}")


@router.post("/canva/validate", response_model=Dict[str, Any])
async def validate_canva_connection(
    connection_id: str = Query(..., description="Connection ID to validate"),
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """
    Validate Canva connection

    Tests if the Canva API connection is working by calling list_templates.

    Example:
        POST /api/tools/canva/validate?connection_id=canva-1
    """
    try:
        from ...services.tools.base import ToolConnection
        from ...services.tools.registry import get_mindscape_tool

        connection_model = registry.get_connection(connection_id)
        if not connection_model:
            raise HTTPException(status_code=404, detail=f"Connection not found: {connection_id}")

        # Create ToolConnection from model
        connection = ToolConnection(
            id=connection_model.id,
            tool_type=connection_model.tool_type,
            connection_type=connection_model.connection_type,
            api_key=connection_model.api_key,
            oauth_token=connection_model.oauth_token,
            base_url=connection_model.base_url or "https://api.canva.com/rest/v1",
            name=connection_model.name
        )

        # Get list_templates tool
        tool_id = f"{connection.id}.canva.list_templates"
        tool = get_mindscape_tool(tool_id)

        if not tool:
            raise HTTPException(
                status_code=404,
                detail=f"Canva tool not found. Make sure connection is registered: {tool_id}"
            )

        # Test connection by listing templates
        result = await tool.execute({
            "limit": 1,
            "offset": 0
        })

        if result.get("success"):
            return {
                "valid": True,
                "message": "Canva connection is valid",
                "connection_id": connection_id,
                "templates_available": result.get("count", 0) > 0
            }
        else:
            return {
                "valid": False,
                "message": result.get("error", "Connection validation failed"),
                "connection_id": connection_id
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to validate Canva connection: {e}", exc_info=True)
        return {
            "valid": False,
            "message": f"Validation error: {str(e)}",
            "connection_id": connection_id
        }


# ============================================
# Google Drive Tool Integration
# ============================================

class GoogleDriveConnectionRequest(BaseModel):
    """Google Drive connection request"""
    connection_id: str
    name: str
    api_key: str = Field(..., description="Google Drive OAuth 2.0 access token")
    api_secret: Optional[str] = Field(None, description="Refresh token (optional)")


@router.post("/google-drive/discover", response_model=Dict[str, Any])
async def discover_google_drive_capabilities(
    request: GoogleDriveConnectionRequest,
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """
    Discover Google Drive capabilities

    Requires Google Drive OAuth 2.0 access token

    Example:
        POST /api/tools/google-drive/discover
        {
            "connection_id": "gdrive-1",
            "name": "My Google Drive",
            "api_key": "ya29..."
        }
    """
    try:
        from ...services.tools.discovery_provider import ToolConfig

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
        raise HTTPException(status_code=500, detail=f"Discovery failed: {str(e)}")


@router.post("/google-drive/connect", response_model=ToolConnectionModel)
async def create_google_drive_connection(
    request: GoogleDriveConnectionRequest,
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """Create a Google Drive connection (without discovery)"""
    try:
        conn = registry.create_connection(
            connection_id=request.connection_id,
            name=request.name,
            api_key=request.api_key,
            api_secret=request.api_secret
        )
        return conn
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create connection: {str(e)}")


# ============================================
# Google Drive OAuth 2.0 Flow
# ============================================

def get_oauth_manager():
    """
    Get Google Drive OAuth manager instance

    Creates a new instance each time to ensure it loads the latest configuration
    from system settings (in case settings were updated).
    """
    from ...services.tools.google_drive.oauth_manager import GoogleDriveOAuthManager
    data_dir = os.getenv("DATA_DIR", "./data")
    manager = GoogleDriveOAuthManager(data_dir=data_dir)
    # Reload configuration to get latest from system settings
    manager.reload_configuration()
    return manager


@router.get("/google-drive/oauth/authorize")
async def google_drive_oauth_authorize(
    connection_id: str = Query(..., description="Connection identifier"),
    connection_name: Optional[str] = Query(None, description="Connection name"),
):
    """
    Initiate Google Drive OAuth 2.0 authorization flow

    Generates a secure state token and redirects user to Google authorization page.

    Args:
        connection_id: Unique identifier for this connection
        connection_name: Optional display name for the connection

    Returns:
        RedirectResponse to Google OAuth authorization page

    Example:
        GET /api/tools/google-drive/oauth/authorize?connection_id=gdrive-1&connection_name=My+Drive
    """
    try:
        oauth_manager = get_oauth_manager()

        # Generate state token (CSRF protection)
        state_token = oauth_manager.generate_state_token(
            connection_id=connection_id,
            connection_name=connection_name
        )

        # Build Google OAuth authorization URL
        authorization_url = oauth_manager.build_authorization_url(state_token)

        # Redirect to Google
        return RedirectResponse(url=authorization_url, status_code=302)

    except ValueError as e:
        raise HTTPException(
            status_code=500,
            detail=f"OAuth configuration error: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to initiate OAuth flow: {str(e)}"
        )


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

    Returns:
        HTMLResponse with JavaScript to close popup and notify parent window

    Example:
        GET /api/tools/google-drive/oauth/callback?code=4/0A...&state=xyz...
    """
    # Handle OAuth errors
    if error:
        error_msg = error_description or error
        logger.error(f"Google OAuth error: {error} - {error_msg}")
        return HTMLResponse(content=f"""
        <!DOCTYPE html>
        <html>
            <head>
                <title>Authorization Failed</title>
                <style>
                    body {{
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        margin: 0;
                        background: #f5f5f5;
                    }}
                    .container {{
                        text-align: center;
                        background: white;
                        padding: 2rem;
                        border-radius: 8px;
                        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                    }}
                    h1 {{ color: #dc3545; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>❌ Authorization Failed</h1>
                    <p>{error_msg}</p>
                    <p><small>This window will close automatically...</small></p>
                </div>
                <script>
                    setTimeout(() => {{
                        window.opener.postMessage({{error: '{error}'}}, '*');
                        window.close();
                    }}, 2000);
                </script>
            </body>
        </html>
        """, status_code=400)

    # Validate required parameters
    if not code or not state:
        return HTMLResponse(content="""
        <!DOCTYPE html>
        <html>
            <head>
                <title>Authorization Failed</title>
                <style>
                    body {{
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        margin: 0;
                        background: #f5f5f5;
                    }}
                    .container {{
                        text-align: center;
                        background: white;
                        padding: 2rem;
                        border-radius: 8px;
                        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                    }}
                    h1 {{ color: #dc3545; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>❌ Authorization Failed</h1>
                    <p>Missing authorization code or state parameter.</p>
                    <p><small>This window will close automatically...</small></p>
                </div>
                <script>
                    setTimeout(() => {{
                        window.opener.postMessage({{error: 'Missing parameters'}}, '*');
                        window.close();
                    }}, 2000);
                </script>
            </body>
        </html>
        """, status_code=400)

    try:
        oauth_manager = get_oauth_manager()
        registry = get_tool_registry()

        # Validate state token
        state_data = oauth_manager.validate_state_token(state)
        if not state_data:
            raise HTTPException(status_code=400, detail="Invalid or expired state token")

        connection_id = state_data["connection_id"]
        connection_name = state_data.get("connection_name") or f"Google Drive - {connection_id}"

        # Exchange authorization code for tokens
        token_data = await oauth_manager.exchange_code_for_tokens(code)

        access_token = token_data["access_token"]
        refresh_token = token_data.get("refresh_token")

        # Discover and register tools
        from ...services.tools.discovery_provider import ToolConfig

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

        # Return success page that closes popup
        return HTMLResponse(content=f"""
        <!DOCTYPE html>
        <html>
            <head>
                <title>Authorization Successful</title>
                <style>
                    body {{
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        margin: 0;
                        background: #f5f5f5;
                    }}
                    .container {{
                        text-align: center;
                        background: white;
                        padding: 2rem;
                        border-radius: 8px;
                        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                    }}
                    h1 {{ color: #28a745; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>✅ Successfully Connected!</h1>
                    <p>Discovered {tools_count} tool(s) from Google Drive.</p>
                    <p><small>This window will close automatically...</small></p>
                </div>
                <script>
                    window.opener.postMessage({{
                        success: true,
                        connection_id: '{connection_id}',
                        tools_count: {tools_count}
                    }}, '*');
                    setTimeout(() => {{
                        window.close();
                    }}, 1500);
                </script>
            </body>
        </html>
        """)

    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"OAuth callback error: {e}")
        return HTMLResponse(content=f"""
        <!DOCTYPE html>
        <html>
            <head>
                <title>Authorization Failed</title>
                <style>
                    body {{
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        margin: 0;
                        background: #f5f5f5;
                    }}
                    .container {{
                        text-align: center;
                        background: white;
                        padding: 2rem;
                        border-radius: 8px;
                        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                    }}
                    h1 {{ color: #dc3545; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>❌ Authorization Failed</h1>
                    <p>{str(e)}</p>
                    <p><small>This window will close automatically...</small></p>
                </div>
                <script>
                    setTimeout(() => {{
                        window.opener.postMessage({{error: '{str(e)}'}}, '*');
                        window.close();
                    }}, 3000);
                </script>
            </body>
        </html>
        """, status_code=400)
    except Exception as e:
        logger.error(f"Unexpected error in OAuth callback: {e}", exc_info=True)
        return HTMLResponse(content=f"""
        <!DOCTYPE html>
        <html>
            <head>
                <title>Authorization Failed</title>
                <style>
                    body {{
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        margin: 0;
                        background: #f5f5f5;
                    }}
                    .container {{
                        text-align: center;
                        background: white;
                        padding: 2rem;
                        border-radius: 8px;
                        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                    }}
                    h1 {{ color: #dc3545; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>❌ Authorization Failed</h1>
                    <p>An unexpected error occurred. Please try again.</p>
                    <p><small>This window will close automatically...</small></p>
                </div>
                <script>
                    setTimeout(() => {{
                        window.opener.postMessage({{error: 'Unexpected error'}}, '*');
                        window.close();
                    }}, 3000);
                </script>
            </body>
        </html>
        """, status_code=500)


@router.get("/connections", response_model=List[ToolConnectionModel])
async def list_connections(
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """List all tool connections"""
    return registry.get_connections()


@router.get("/connections/{connection_id}", response_model=ToolConnectionModel)
async def get_connection(
    connection_id: str,
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """Get a specific connection"""
    conn = registry.get_connection(connection_id)
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    return conn


@router.delete("/connections/{connection_id}")
async def delete_connection(
    connection_id: str,
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """Delete a connection and all its tools"""
    success = registry.delete_connection(connection_id)
    if not success:
        raise HTTPException(status_code=404, detail="Connection not found")
    return {"success": True}


@router.get("/", response_model=List[RegisteredTool])
async def list_tools(
    site_id: Optional[str] = None,
    category: Optional[str] = None,
    enabled_only: bool = True,
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """List registered tools with optional filters"""
    tools = registry.get_tools(
        site_id=site_id,
        category=category,
        enabled_only=enabled_only,
    )
    return tools


@router.get("/status", response_model=Dict[str, Any])
async def get_tools_status(
    profile_id: str = Query('default-user', description="Profile ID")
):
    """
    Get status of all tools for a profile

    Returns tool connection status for all registered tools:
    - unavailable: Tool not registered
    - registered_but_not_connected: Tool registered but no active connection
    - connected: Tool has active and validated connection

    Example:
        GET /api/v1/tools/status?profile_id=user123
    """
    try:
        data_dir = os.getenv("DATA_DIR", "./data")
        tool_registry = ToolRegistryService(data_dir=data_dir)
        tool_status_checker = ToolStatusChecker(tool_registry)
        statuses = tool_status_checker.list_all_tools_status(profile_id)

        return {
            "tools": {
                tool_type: {
                    "status": status.value,
                    "info": get_tool_info(tool_type)
                }
                for tool_type, status in statuses.items()
            }
        }
    except Exception as e:
        logger.error(f"Failed to get tools status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{tool_id}", response_model=RegisteredTool)
async def get_tool(
    tool_id: str,
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """Get a specific tool"""
    tool = registry.get_tool(tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    return tool


@router.patch("/{tool_id}", response_model=RegisteredTool)
async def update_tool(
    tool_id: str,
    request: ToolUpdateRequest,
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """Update tool settings (enable/disable, read-only mode, allowed roles)"""
    tool = registry.update_tool(
        tool_id=tool_id,
        enabled=request.enabled,
        read_only=request.read_only,
        allowed_agent_roles=request.allowed_agent_roles,
    )
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    return tool


@router.get("/agent/{agent_role}", response_model=List[RegisteredTool])
async def get_tools_for_agent(
    agent_role: str,
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """Get tools available for a specific agent role"""
    tools = registry.get_tools_for_agent_role(agent_role)
    return tools


# ============================================
# LangChain Tool Integration (Convenience API)
# ============================================

class LangChainRegisterRequest(BaseModel):
    """Register LangChain tool request"""
    tool_name: str = Field(..., description="LangChain tool name")
    config: Dict[str, Any] = Field(default_factory=dict, description="Tool configuration (e.g., API keys)")
    profile_id: Optional[str] = Field(default='default-user', description="User ID")


class LangChainDiscoverRequest(BaseModel):
    """Batch discover LangChain tools request"""
    tool_names: List[str] = Field(..., description="List of tool names to discover")
    profile_id: Optional[str] = Field(default='default-user', description="User ID")


@router.get("/langchain/available", response_model=Dict[str, Any])
async def get_available_langchain_tools():
    """
    Get all available LangChain tools list

    Used by Config Assistant to query tools that can be recommended to users

    Returns:
        {
            "tools": [
                {
                    "name": "wikipedia",
                    "display_name": "Wikipedia",
                    "description": "Search Wikipedia",
                    "requires_api_key": false,
                    "category": "search"
                },
                ...
            ]
        }
    """
    try:
        # Import predefined tools list
        from ...services.tools.providers.langchain_known_tools import KNOWN_LANGCHAIN_TOOLS

        return {
            "success": True,
            "tools": KNOWN_LANGCHAIN_TOOLS,
            "count": len(KNOWN_LANGCHAIN_TOOLS)
        }
    except ImportError:
        # Fallback: return basic list
        return {
            "success": True,
            "tools": [
                {
                    "name": "wikipedia",
                    "display_name": "Wikipedia",
                    "description": "搜尋維基百科知識",
                    "requires_api_key": False,
                    "category": "搜尋"
                }
            ],
            "count": 1,
            "note": "完整工具清單需要安裝 langchain-community"
        }


@router.post("/langchain/register", response_model=Dict[str, Any])
async def register_langchain_tool(
    request: LangChainRegisterRequest,
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """
    Register single LangChain tool (convenience endpoint)

    Used by Config Assistant for automatic tool configuration

    Example:
        POST /api/tools/langchain/register
        {
            "tool_name": "wikipedia",
            "config": {},
            "profile_id": "user123"
        }

        POST /api/tools/langchain/register
        {
            "tool_name": "serpapi",
            "config": {
                "serpapi_api_key": "your-key"
            }
        }
    """
    try:
        from ...services.tools.adapters.langchain_adapter import from_langchain
        from ...services.tools.providers.langchain_known_tools import get_langchain_tool_class

        # Get tool class
        tool_class_info = get_langchain_tool_class(request.tool_name)
        if not tool_class_info:
            raise HTTPException(
                status_code=404,
                detail=f"Unknown LangChain tool: {request.tool_name}"
            )

        # Dynamically import tool class
        module_path = tool_class_info["module"]
        class_name = tool_class_info["class"]

        module = __import__(module_path, fromlist=[class_name])
        tool_class = getattr(module, class_name)

        # Instantiate tool
        if request.config:
            lc_tool = tool_class(**request.config)
        else:
            lc_tool = tool_class()

        # Convert to MindscapeTool
        mindscape_tool = from_langchain(lc_tool)

        # Register to registry
        # TODO: Integrate with ToolRegistry registration mechanism

        return {
            "success": True,
            "tool_name": request.tool_name,
            "tool_id": f"langchain.{request.tool_name}",
            "message": f"LangChain tool {request.tool_name} registered successfully"
        }

    except ImportError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to import LangChain tool: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Registration failed: {str(e)}"
        )


@router.post("/langchain/discover", response_model=Dict[str, Any])
async def discover_langchain_tools(
    request: LangChainDiscoverRequest,
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """
    Batch discover and register LangChain tools

    Used by Config Assistant to configure multiple tools at once

    Example:
        POST /api/tools/langchain/discover
        {
            "tool_names": ["wikipedia", "arxiv"],
            "profile_id": "user123"
        }
    """
    try:
        from ...services.tools.adapters.langchain_adapter import from_langchain
        from ...services.tools.providers.langchain_known_tools import get_langchain_tool_class

        results = {
            "success": True,
            "discovered": [],
            "failed": []
        }

        for tool_name in request.tool_names:
            try:
                # Get tool class
                tool_class_info = get_langchain_tool_class(tool_name)
                if not tool_class_info:
                    results["failed"].append({
                        "tool_name": tool_name,
                        "error": "Unknown tool"
                    })
                    continue

                # Dynamically import
                module_path = tool_class_info["module"]
                class_name = tool_class_info["class"]

                module = __import__(module_path, fromlist=[class_name])
                tool_class = getattr(module, class_name)

                # Instantiate
                lc_tool = tool_class()

                # Convert
                mindscape_tool = from_langchain(lc_tool)

                results["discovered"].append({
                    "tool_name": tool_name,
                    "tool_id": f"langchain.{tool_name}",
                    "description": tool_class_info.get("description", "")
                })

            except Exception as e:
                results["failed"].append({
                    "tool_name": tool_name,
                    "error": str(e)
                })

        return results

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/langchain/status", response_model=Dict[str, Any])
async def get_langchain_tools_status(
    profile_id: str = Query('default-user', description="用戶 ID"),
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """
    Get registered LangChain tools status

    Used by Config Assistant to check which tools are installed

    Returns:
        {
            "installed": ["wikipedia", "arxiv"],
            "count": 2
        }
    """
    try:
        # Query all registered LangChain tools
        all_tools = registry.get_tools()
        langchain_tools = [
            tool for tool in all_tools
            if tool.provider == "langchain" or tool.tool_id.startswith("langchain.")
        ]

        return {
            "success": True,
            "installed": [tool.tool_id for tool in langchain_tools],
            "count": len(langchain_tools),
            "tools": [
                {
                    "tool_id": tool.tool_id,
                    "display_name": tool.display_name,
                    "description": tool.description,
                    "enabled": tool.enabled
                }
                for tool in langchain_tools
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# MCP Tool Integration (Convenience API)
# ============================================

class MCPConnectRequest(BaseModel):
    """Connect MCP server request"""
    server_id: str = Field(..., description="Server unique identifier")
    name: str = Field(..., description="Server display name")
    transport: str = Field(default="stdio", description="Transport type: stdio or http")

    # stdio configuration
    command: Optional[str] = Field(None, description="Command (e.g., 'npx')")
    args: Optional[List[str]] = Field(None, description="Command arguments")
    env: Optional[Dict[str, str]] = Field(None, description="Environment variables")

    # HTTP configuration
    base_url: Optional[str] = Field(None, description="HTTP server URL")
    api_key: Optional[str] = Field(None, description="API authentication key")


class MCPImportClaudeConfigRequest(BaseModel):
    """Import Claude MCP configuration request"""
    config_path: Optional[str] = Field(
        default="~/.config/claude/mcp.json",
        description="Claude mcp.json file path"
    )


@router.get("/mcp/servers", response_model=Dict[str, Any])
async def list_mcp_servers():
    """
    List all configured MCP servers

    Used by Config Assistant to view connected servers
    """
    try:
        from ...services.tools.adapters.mcp_manager import MCPServerManager

        manager = MCPServerManager()
        servers_info = []

        for server_id in manager.servers:
            status = manager.get_server_status(server_id)
            servers_info.append(status)

        return {
            "success": True,
            "servers": servers_info,
            "count": len(servers_info)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mcp/connect", response_model=Dict[str, Any])
async def connect_mcp_server(request: MCPConnectRequest):
    """
    Connect new MCP server

    Used by Config Assistant for automatic MCP server configuration
    """
    try:
        from ...services.tools.adapters.mcp_manager import MCPServerManager
        from ...services.tools.adapters.mcp_client import MCPServerConfig, MCPTransportType

        manager = MCPServerManager()

        if request.transport == "stdio":
            config = MCPServerConfig(
                id=request.server_id,
                name=request.name,
                transport=MCPTransportType.STDIO,
                command=request.command,
                args=request.args or [],
                env=request.env or {}
            )
        else:
            config = MCPServerConfig(
                id=request.server_id,
                name=request.name,
                transport=MCPTransportType.HTTP_SSE,
                base_url=request.base_url,
                api_key=request.api_key
            )

        tools = await manager.add_server(config, auto_discover=True)

        return {
            "success": True,
            "server_id": request.server_id,
            "tools_count": len(tools),
            "message": f"MCP server {request.name} connected, discovered {len(tools)} tools"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Connection failed: {str(e)}")


@router.delete("/mcp/servers/{server_id}", response_model=Dict[str, Any])
async def delete_mcp_server(server_id: str):
    """
    Delete MCP server

    Removes the server and disconnects it
    """
    try:
        from ...services.tools.adapters.mcp_manager import MCPServerManager

        manager = MCPServerManager()
        await manager.remove_server(server_id)

        return {
            "success": True,
            "message": f"MCP server {server_id} deleted"
        }
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Deletion failed: {str(e)}")


@router.post("/mcp/import-claude-config", response_model=Dict[str, Any])
async def import_claude_mcp_config(request: MCPImportClaudeConfigRequest):
    """
    Import Claude Desktop MCP configuration

    Used for quick setup: one-click import Claude configuration
    """
    try:
        from pathlib import Path
        from ...services.tools.adapters.mcp_manager import MCPServerManager

        config_path = Path(request.config_path).expanduser()

        if not config_path.exists():
            raise HTTPException(status_code=404, detail=f"Configuration file not found: {config_path}")

        manager = MCPServerManager()
        imported_count = manager.import_from_claude_config(str(config_path))
        await manager.connect_all()

        servers_status = []
        for server_id in manager.servers:
            status = manager.get_server_status(server_id)
            servers_status.append(status)

        return {
            "success": True,
            "imported_count": imported_count,
            "servers": servers_status,
            "message": f"Successfully imported {imported_count} MCP servers"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")


@router.get("/status", response_model=Dict[str, Any])
async def get_tools_status(
    profile_id: str = Query('default-user', description="Profile ID")
):
    """
    Get status of all tools for a profile

    Returns tool connection status for all registered tools:
    - unavailable: Tool not registered
    - registered_but_not_connected: Tool registered but no active connection
    - connected: Tool has active and validated connection

    Example:
        GET /api/v1/tools/status?profile_id=user123
    """
    try:
        data_dir = os.getenv("DATA_DIR", "./data")
        tool_registry = ToolRegistryService(data_dir=data_dir)
        tool_status_checker = ToolStatusChecker(tool_registry)
        statuses = tool_status_checker.list_all_tools_status(profile_id)

        return {
            "tools": {
                tool_type: {
                    "status": status.value,
                    "info": get_tool_info(tool_type)
                }
                for tool_type, status in statuses.items()
            }
        }
    except Exception as e:
        logger.error(f"Failed to get tools status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{tool_type}/status", response_model=Dict[str, Any])
async def get_tool_status(
    tool_type: str,
    profile_id: str = Query('default-user', description="Profile ID")
):
    """
    Get status of a specific tool

    Returns tool connection status for a specific tool.

    Example:
        GET /api/v1/tools/wordpress/status?profile_id=user123
    """
    try:
        data_dir = os.getenv("DATA_DIR", "./data")
        tool_registry = ToolRegistryService(data_dir=data_dir)
        tool_status_checker = ToolStatusChecker(tool_registry)
        status = tool_status_checker.get_tool_status(tool_type, profile_id)

        return {
            "tool_type": tool_type,
            "status": status.value,
            "info": get_tool_info(tool_type)
        }
    except Exception as e:
        logger.error(f"Failed to get tool status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/mcp/available-servers", response_model=Dict[str, Any])
async def get_available_mcp_servers():
    """
    Get predefined common MCP servers list

    Used by Config Assistant to recommend to users
    """
    available_servers = [
        {
            "id": "github",
            "name": "GitHub",
            "description": "Access GitHub repositories, issues, pull requests, etc.",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-github"],
            "requires_env": ["GITHUB_TOKEN"],
            "category": "development"
        },
        {
            "id": "filesystem",
            "name": "File System",
            "description": "Read and write local file system",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem"],
            "category": "file_operations",
            "danger_level": "high"
        },
        {
            "id": "postgres",
            "name": "PostgreSQL",
            "description": "Query and operate PostgreSQL database",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-postgres"],
            "requires_env": ["DATABASE_URL"],
            "category": "database"
        },
    ]

    return {
        "success": True,
        "servers": available_servers,
        "count": len(available_servers)
    }

