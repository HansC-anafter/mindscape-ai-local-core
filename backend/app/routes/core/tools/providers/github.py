"""
GitHub tool provider routes with OAuth support
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
import logging
import os

from backend.app.models.tool_registry import ToolConnectionModel
from backend.app.services.tool_registry import ToolRegistryService
from backend.app.services.tools.discovery_provider import ToolConfig
from ..base import get_tool_registry, raise_api_error

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/tools", tags=["tools"])


class GitHubConnectionRequest(BaseModel):
    """GitHub connection request"""
    connection_id: str
    name: str
    oauth_token: Optional[str] = Field(None, description="GitHub OAuth Access Token (if already obtained)")
    client_id: Optional[str] = Field(None, description="GitHub OAuth Client ID (from GitHub App)")
    client_secret: Optional[str] = Field(None, description="GitHub OAuth Client Secret (from GitHub App)")
    access_token: Optional[str] = Field(None, description="GitHub Access Token (Personal Access Token ghp_ or OAuth token gho_)")


@router.post("/github/discover", response_model=Dict[str, Any])
async def discover_github_capabilities(
    request: GitHubConnectionRequest,
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """
    Discover GitHub capabilities using discovery provider

    Uses the new architecture ToolRegistryService with GitHubDiscoveryProvider.

    Example:
        POST /api/v1/tools/github/discover
        {
            "connection_id": "github-account-1",
            "name": "My GitHub Account",
            "access_token": "ghp_..."
        }
    """
    try:
        access_token = request.oauth_token or request.access_token
        if not access_token:
            raise ValueError("GitHub access token is required (oauth_token or access_token)")

        config = ToolConfig(
            tool_type="github",
            connection_type="oauth2" if request.oauth_token or (request.client_id and request.client_secret) else "http_api",
            api_key=access_token
        )

        result = await registry.discover_tool_capabilities(
            provider_name="github",
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
        logger.error(f"GitHub discovery failed: {e}", exc_info=True)
        raise_api_error(500, f"Discovery failed: {str(e)}")


@router.post("/github/connect", response_model=ToolConnectionModel)
async def create_github_connection(
    request: GitHubConnectionRequest,
    profile_id: str = Query("default-user", description="Profile ID for multi-tenant support"),
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """
    Create a GitHub connection

    Supports both OAuth tokens and Personal Access Tokens.
    """
    try:
        access_token = request.oauth_token or request.access_token
        if not access_token:
            raise ValueError("GitHub access token is required (oauth_token or access_token)")

        # Create ToolConnectionModel instance
        connection = ToolConnectionModel(
            id=request.connection_id,
            profile_id=profile_id,
            tool_type="github",
            connection_type="local",
            name=request.name,
            description=f"GitHub connection: {request.name}",
            api_key=access_token,
            oauth_token=request.oauth_token if request.oauth_token else None,
            is_active=True,
            created_at=_utc_now(),
            updated_at=_utc_now()
        )

        # Create connection in registry
        conn_model = registry.create_connection(connection)

        # Register tools
        try:
            from backend.app.services.tools.base import ToolConnection
            from backend.app.services.tools.registry import register_github_tools

            tool_connection = ToolConnection(
                id=conn_model.id,
                tool_type="github",
                connection_type="local",
                api_key=access_token,
                oauth_token=conn_model.oauth_token,
                name=conn_model.name
            )
            tools = register_github_tools(tool_connection)
            logger.info(f"Registered {len(tools)} GitHub tools for connection: {request.connection_id}")
        except ImportError:
            logger.warning("GitHub tools registration not available, skipping tool registration")

        return conn_model
    except Exception as e:
        logger.error(f"Failed to create GitHub connection: {e}", exc_info=True)
        raise_api_error(500, f"Failed to create connection: {str(e)}")


@router.get("/github/oauth/authorize")
async def github_oauth_authorize(
    connection_id: str = Query(..., description="Connection ID"),
    connection_name: Optional[str] = Query(None, description="Connection name"),
    client_id: Optional[str] = Query(None, description="GitHub Client ID (if not stored)"),
):
    """
    Initiate GitHub OAuth authorization flow

    Redirects user to GitHub authorization page.
    """
    try:
        from backend.app.services.tools.github.oauth_manager import get_github_oauth_manager
        oauth_manager = get_github_oauth_manager()

        if not oauth_manager.client_id and not client_id:
            raise_api_error(400, "GitHub Client ID is required. Set GITHUB_CLIENT_ID environment variable or provide client_id parameter.")

        auth_url = oauth_manager.build_authorization_url(
            connection_id=connection_id,
            connection_name=connection_name,
            client_id=client_id
        )

        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=auth_url)
    except Exception as e:
        logger.error(f"Failed to initiate GitHub OAuth flow: {e}", exc_info=True)
        raise_api_error(500, f"Failed to initiate OAuth flow: {str(e)}")


@router.get("/github/oauth/callback")
async def github_oauth_callback(
    code: str = Query(..., description="Authorization code"),
    state: str = Query(..., description="OAuth state token"),
    error: Optional[str] = Query(None, description="OAuth error"),
):
    """
    Handle GitHub OAuth callback

    Exchanges authorization code for access token and creates connection.
    """
    try:
        if error:
            raise_api_error(400, f"OAuth error: {error}")

        from backend.app.services.tools.github.oauth_manager import get_github_oauth_manager
        oauth_manager = get_github_oauth_manager()

        # Validate state token
        state_data = oauth_manager.validate_state_token(state)
        if not state_data:
            raise_api_error(400, "Invalid or expired OAuth state token")

        connection_id = state_data.get("connection_id")
        connection_name = state_data.get("connection_name")

        # Exchange code for token
        token_response = await oauth_manager.exchange_code_for_token(code)

        access_token = token_response.get("access_token")
        if not access_token:
            raise_api_error(400, "Failed to obtain access token from GitHub")

        # Create connection using registry
        from backend.app.services.tool_registry import ToolRegistryService
        from backend.app.models.tool_registry import ToolConnectionModel
        data_dir = os.getenv("DATA_DIR", "./data")
        registry = ToolRegistryService(data_dir=data_dir)

        connection_model = ToolConnectionModel(
            id=connection_id or "github-oauth-1",
            profile_id="default-user",
            tool_type="github",
            connection_type="local",
            name=connection_name or "GitHub OAuth Connection",
            description="GitHub OAuth connection",
            api_key=access_token,
            oauth_token=access_token,
            is_active=True,
            created_at=_utc_now(),
            updated_at=_utc_now()
        )

        connection = registry.create_connection(connection_model)

        # Register tools
        try:
            from backend.app.services.tools.registry import register_github_tools
            from backend.app.services.tools.base import ToolConnection

            tool_connection = ToolConnection(
                id=connection.id,
                tool_type="github",
                connection_type="local",
                api_key=access_token,
                oauth_token=access_token,
                name=connection.name
            )
            tools = register_github_tools(tool_connection)
            logger.info(f"Registered {len(tools)} GitHub tools via OAuth")
        except ImportError:
            logger.warning("GitHub tools registration not available")

        # Redirect to frontend with success
        from fastapi.responses import RedirectResponse
        # 从端口配置服务获取前端 URL
        try:
            from ....services.port_config_service import port_config_service
            import os
            current_cluster = os.getenv('CLUSTER_NAME')
            current_env = os.getenv('ENVIRONMENT')
            current_site = os.getenv('SITE_NAME')
            frontend_url = port_config_service.get_service_url(
                'frontend',
                cluster=current_cluster,
                environment=current_env,
                site=current_site
            )
        except Exception:
            # 回退到环境变量或默认值
            frontend_url = os.getenv("FRONTEND_URL", "http://localhost:8300")
        redirect_url = f"{frontend_url}/settings?tool=github&connected=true"
        return RedirectResponse(url=redirect_url)
    except Exception as e:
        logger.error(f"Failed to handle GitHub OAuth callback: {e}", exc_info=True)
        raise_api_error(500, f"Failed to handle OAuth callback: {str(e)}")


@router.post("/github/validate", response_model=Dict[str, Any])
async def validate_github_connection(
    connection_id: str,
    profile_id: str = Query("default-user", description="Profile ID"),
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """
    Validate GitHub connection

    Tests if the GitHub API connection is working by calling user endpoint.
    """
    try:
        connection_model = registry.get_connection(connection_id=connection_id, profile_id=profile_id)
        if not connection_model:
            raise_api_error(404, f"GitHub connection not found: {connection_id}")

        access_token = connection_model.oauth_token or connection_model.api_key
        if not access_token:
            raise_api_error(400, "No access token found in connection")

        # Test connection by calling user endpoint
        import aiohttp
        url = "https://api.github.com/user"
        headers = {
            "Authorization": f"token {access_token}",
            "Accept": "application/vnd.github.v3+json"
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"GitHub API error: {response.status} - {error_text}")

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
                    "user": result.get("login"),
                    "name": result.get("name"),
                    "type": result.get("type"),
                    "message": "GitHub connection is valid"
                }
    except Exception as e:
        logger.error(f"Failed to validate GitHub connection: {e}", exc_info=True)
        raise_api_error(500, f"Failed to validate connection: {str(e)}")

