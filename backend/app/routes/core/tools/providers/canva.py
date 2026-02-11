"""
Canva tool provider routes with OAuth support
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import RedirectResponse
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
import logging

from backend.app.models.tool_registry import ToolConnectionModel
from backend.app.services.tool_registry import ToolRegistryService
from backend.app.services.tools.discovery_provider import ToolConfig
from ..base import get_tool_registry, raise_api_error

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/tools", tags=["tools"])


class CanvaConnectionRequest(BaseModel):
    """Canva connection request"""
    connection_id: str
    name: str
    oauth_token: Optional[str] = Field(None, description="Canva OAuth Access Token (if already obtained)")
    client_id: Optional[str] = Field(None, description="Canva OAuth Client ID (from Developer Portal)")
    client_secret: Optional[str] = Field(None, description="Canva OAuth Client Secret (from Developer Portal)")
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


@router.post("/canva/discover", response_model=Dict[str, Any])
async def discover_canva_capabilities(
    request: CanvaConnectionRequest,
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """
    Discover Canva capabilities using discovery provider

    Uses the new architecture ToolRegistryService with CanvaDiscoveryProvider.
    """
    try:
        config = ToolConfig(
            tool_type="canva",
            connection_type="oauth2" if request.oauth_token or (request.client_id and request.client_secret) else "http_api",
            api_key=request.api_key,
            base_url=request.base_url or "https://api.canva.com/rest/v1",
            custom_config={
                "oauth_token": request.oauth_token,
                "client_id": request.client_id,
                "client_secret": request.client_secret,
                "brand_id": request.brand_id,
            }
        )

        result = await registry.discover_tool_capabilities(
            provider_name="canva",
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
        logger.error(f"Canva discovery failed: {e}", exc_info=True)
        raise_api_error(500, f"Discovery failed: {str(e)}")


@router.post("/canva/connect", response_model=ToolConnectionModel)
async def create_canva_connection(
    request: CanvaConnectionRequest,
    profile_id: str = Query("default-user", description="Profile ID for multi-tenant support"),
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """
    Create a Canva connection

    Supports three authentication methods:
    1. Direct OAuth Token (if you already have an access token)
    2. OAuth Credentials (Client ID + Client Secret) - will need to complete OAuth flow
    3. API Key (if available, though OAuth is the standard method)
    """
    try:
        has_auth = bool(request.oauth_token or request.api_key or (request.client_id and request.client_secret))
        if not has_auth:
            raise_api_error(400, "Authentication required: provide either oauth_token, api_key, or (client_id + client_secret)")

        if request.client_id and request.client_secret and not request.redirect_uri:
            raise_api_error(400, "redirect_uri is required when using client_id and client_secret")

        from backend.app.services.tools.base import ToolConnection
        # ✅ Updated: Import from capability pack instead of local-core
        try:
            from capabilities.canva.services.tool_registration import register_canva_tools
        except ImportError:
            # Fallback to local-core version if capability pack not installed
            from backend.app.services.tools.registry import register_canva_tools
            logger.warning("Canva capability pack not found, using local-core version")

        # Create ToolConnectionModel instance
        connection_model = ToolConnectionModel(
            id=request.connection_id,
            profile_id=profile_id,
            tool_type="canva",
            connection_type="local",
            name=request.name,
            description=f"Canva connection: {request.name}",
            api_key=request.api_key,
            oauth_token=request.oauth_token,
            base_url=request.base_url or "https://api.canva.com/rest/v1",
            config={
                "client_id": request.client_id,
                "client_secret": request.client_secret,
                "brand_id": request.brand_id,
                "redirect_uri": request.redirect_uri
            } if (request.client_id or request.brand_id or request.redirect_uri) else {},
            is_active=True,
            created_at=_utc_now(),
            updated_at=_utc_now()
        )

        # Create connection in registry
        conn_model = registry.create_connection(connection_model)

        # Register tools
        tool_connection = ToolConnection(
            id=conn_model.id,
            tool_type="canva",
            connection_type="local",
            api_key=request.api_key,
            oauth_token=request.oauth_token,
            base_url=conn_model.base_url,
            name=conn_model.name
        )

        if request.client_id and request.client_secret and not request.oauth_token:
            logger.info(f"Canva connection created with OAuth credentials. OAuth flow needs to be completed.")

        # ✅ Updated: Call register_canva_tools from capability pack
        tools = register_canva_tools(tool_connection)
        logger.info(f"Registered {len(tools)} Canva tools for connection: {request.connection_id}")

        return conn_model

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create Canva connection: {e}", exc_info=True)
        raise_api_error(500, f"Failed to create connection: {str(e)}")


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
    """
    try:
        # ✅ Updated: Import from capability pack
        try:
            from capabilities.canva.services.oauth_manager import get_canva_oauth_manager
        except ImportError:
            # Fallback to local-core version if capability pack not installed
            from backend.app.services.tools.canva.oauth_manager import get_canva_oauth_manager
            logger.warning("Canva capability pack not found, using local-core OAuth manager")

        connection_model = None
        if connection_id:
            try:
                connection_model = registry.get_connection(connection_id)
            except Exception:
                pass

        final_client_id = client_id
        final_redirect_uri = redirect_uri

        if connection_model and not final_client_id:
            pass

        if not final_client_id:
            raise_api_error(400, "client_id is required. Provide via query parameter or ensure connection has stored credentials.")

        if not final_redirect_uri:
            # 从端口配置服务获取后端 URL
            try:
                from ....services.port_config_service import port_config_service
                import os
                current_cluster = os.getenv('CLUSTER_NAME')
                current_env = os.getenv('ENVIRONMENT')
                current_site = os.getenv('SITE_NAME')
                backend_url = port_config_service.get_service_url(
                    'backend_api',
                    cluster=current_cluster,
                    environment=current_env,
                    site=current_site
                )
                final_redirect_uri = f"{backend_url}/api/tools/canva/oauth/callback"
            except Exception:
                # 回退到默认值
                final_redirect_uri = f"http://localhost:8200/api/tools/canva/oauth/callback"

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
        raise_api_error(500, f"OAuth authorization failed: {str(e)}")


@router.get("/canva/oauth/callback")
async def canva_oauth_callback(
    code: str = Query(..., description="Authorization code"),
    state: str = Query(..., description="State token"),
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """
    Handle Canva OAuth callback

    Exchanges authorization code for access token and updates connection.
    """
    try:
        # ✅ Updated: Import from capability pack
        try:
            from capabilities.canva.services.oauth_manager import get_canva_oauth_manager
        except ImportError:
            # Fallback to local-core version if capability pack not installed
            from backend.app.services.tools.canva.oauth_manager import get_canva_oauth_manager
            logger.warning("Canva capability pack not found, using local-core OAuth manager")

        oauth_manager = get_canva_oauth_manager()

        state_data = oauth_manager.validate_state_token(state)
        if not state_data:
            raise_api_error(400, "Invalid or expired state token")

        connection_id = state_data["connection_id"]
        profile_id = state_data.get("profile_id", "default-user")

        connection_model = registry.get_connection(connection_id, profile_id)
        if not connection_model:
            raise_api_error(404, f"Connection not found: {connection_id}")

        code_verifier = oauth_manager.get_code_verifier(state)
        if not code_verifier:
            raise_api_error(400, "Code verifier not found for state token")

        # Get client_id and client_secret from connection config
        config = connection_model.config or {}
        client_id = config.get("client_id")
        client_secret = config.get("client_secret")
        redirect_uri = config.get("redirect_uri")

        if not client_id or not client_secret:
            raise_api_error(400, "client_id and client_secret must be stored in connection. Please create connection with OAuth credentials first.")

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
            raise_api_error(500, "Failed to obtain access token")

        oauth_manager.cleanup_state(state)

        # Update connection with OAuth token
        connection_model.oauth_token = access_token
        if refresh_token:
            connection_model.oauth_refresh_token = refresh_token
        connection_model.updated_at = _utc_now()
        registry.update_connection(connection_model)

        # Register tools after OAuth completion
        try:
            from backend.app.services.tools.base import ToolConnection
            # ✅ Updated: Import from capability pack instead of local-core
            try:
                from capabilities.canva.services.tool_registration import register_canva_tools
            except ImportError:
                # Fallback to local-core version if capability pack not installed
                from backend.app.services.tools.registry import register_canva_tools
                logger.warning("Canva capability pack not found, using local-core version")

            tool_connection = ToolConnection(
                id=connection_model.id,
                tool_type="canva",
                connection_type="local",
                oauth_token=access_token,
                base_url=connection_model.base_url,
                name=connection_model.name
            )
            # ✅ Updated: Call register_canva_tools from capability pack
            tools = register_canva_tools(tool_connection)
            logger.info(f"Registered {len(tools)} Canva tools after OAuth completion")
        except Exception as e:
            logger.warning(f"Failed to register Canva tools: {e}")

        return {
            "success": True,
            "message": "OAuth authorization completed",
            "connection_id": connection_id,
            "tools_registered": len(tools) if 'tools' in locals() else 0
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to handle Canva OAuth callback: {e}", exc_info=True)
        raise_api_error(500, f"OAuth callback failed: {str(e)}")


@router.post("/canva/validate", response_model=Dict[str, Any])
async def validate_canva_connection(
    connection_id: str = Query(..., description="Connection ID to validate"),
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """
    Validate Canva connection

    Tests if the Canva API connection is working by calling list_templates.
    """
    try:
        from backend.app.services.tools.base import ToolConnection
        from backend.app.services.tools.registry import get_mindscape_tool

        connection_model = registry.get_connection(connection_id)
        if not connection_model:
            raise_api_error(404, f"Connection not found: {connection_id}")

        connection = ToolConnection(
            id=connection_model.id,
            tool_type=connection_model.tool_type,
            connection_type=connection_model.connection_type,
            api_key=connection_model.api_key,
            oauth_token=connection_model.oauth_token,
            base_url=connection_model.base_url or "https://api.canva.com/rest/v1",
            name=connection_model.name
        )

        tool_id = f"{connection.id}.canva.list_templates"
        tool = get_mindscape_tool(tool_id)

        if not tool:
            raise_api_error(404, f"Canva tool not found. Make sure connection is registered: {tool_id}")

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

