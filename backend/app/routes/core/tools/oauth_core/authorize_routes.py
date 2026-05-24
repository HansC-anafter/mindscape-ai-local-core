import base64
import json
import os
import secrets
import uuid
from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse

from backend.app.models.tool_registry import ToolConnectionModel
from backend.app.services.tool_registry import ToolRegistryService
from backend.app.services.tools.discovery_provider import ToolConfig

from ..base import get_tool_registry, raise_api_error
from .helpers import exchange_code_for_token, get_redirect_uri
from .state import OAUTH_CONFIGS, _utc_now, logger

router = APIRouter()

@router.get("/{provider}/authorize")
async def get_authorize_url(
    request: Request,
    provider: str,
    redirect_uri: str = Query(..., description="OAuth redirect URI"),
    state: Optional[str] = Query(None, description="OAuth state parameter"),
    profile_id: str = Query(..., description="Profile ID"),
    workspace_id: Optional[str] = Query(None, description="Workspace ID for context"),
    return_url: Optional[str] = Query(None, description="Custom return URL after OAuth completion"),
    client_id: Optional[str] = Query(None, description="OAuth Client ID (from connection config)"),
    client_secret: Optional[str] = Query(None, description="OAuth Client Secret (from connection config)"),
):
    """
    Generate OAuth 2.0 authorization URL

    Args:
        provider: Social media platform (twitter, facebook, instagram, linkedin, youtube, line)
        redirect_uri: OAuth redirect URI
        state: Optional state parameter for CSRF protection
        profile_id: Profile ID for multi-tenant support
        client_id: OAuth Client ID (from connection config, preferred over env var)
        client_secret: OAuth Client Secret (from connection config, for token exchange)

    Returns:
        Authorization URL with query parameters
    """
    if provider not in OAUTH_CONFIGS:
        logger.error(f"Unsupported OAuth provider: {provider}")
        raise_api_error(400, f"Unsupported provider: {provider}. Available providers: {list(OAUTH_CONFIGS.keys())}")

    config = OAUTH_CONFIGS[provider]

    # Prefer client_id from request parameter (from connection config), fallback to env var
    if not client_id:
        client_id = os.getenv(config["client_id_env"])

    if not client_id:
        logger.error(f"OAuth client ID not configured for {provider}")
        raise_api_error(
            400,
            f"OAuth client ID not configured. Please configure it in the connection settings."
        )

    logger.info(f"Generating OAuth authorization URL for {provider} (client_id: {client_id[:10]}...)")

    # Build state data with context information
    state_data = {
        "profile_id": profile_id,
        "workspace_id": workspace_id,
        "return_url": return_url or "/settings",
        "random": secrets.token_urlsafe(16)
    }

    # Encode state data as base64 JSON
    state_encoded = base64.urlsafe_b64encode(
        json.dumps(state_data).encode()
    ).decode()

    # Use provided state or generated encoded state
    state = state or state_encoded

    # Build authorization URL
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": " ".join(config["scopes"]),
        "state": state,
    }

    # Platform-specific parameters
    if provider == "youtube":
        params["access_type"] = "offline"
        params["prompt"] = "consent"

    auth_url = f"{config['authorize_url']}?{urlencode(params)}"

    # Store client_secret in session/state for token exchange (if provided)
    # For now, we'll pass it in the callback URL or store it temporarily
    # In production, use a secure session store
    if client_secret:
        # Store in a temporary dict (in production, use Redis or similar)
        # For now, we'll need to pass it through the callback
        logger.info(f"Client secret provided for {provider} (will be used in token exchange)")

    return {
        "authorization_url": auth_url,
        "state": state,
    }


@router.get("/{provider}/callback")
async def oauth_callback(
    request: Request,
    provider: str,
    code: str = Query(..., description="OAuth authorization code"),
    state: Optional[str] = Query(None, description="OAuth state parameter"),
    error: Optional[str] = Query(None, description="OAuth error"),
    error_description: Optional[str] = Query(None, description="OAuth error description"),
    profile_id: Optional[str] = Query(None, description="Profile ID (fallback if not in state)"),
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """
    Handle OAuth callback and exchange code for access token

    Args:
        provider: Social media platform
        code: OAuth authorization code
        state: OAuth state parameter
        error: OAuth error (if any)
        error_description: OAuth error description
        profile_id: Profile ID for multi-tenant support
        registry: Tool registry service

    Returns:
        Redirect to frontend with connection status
    """
    # Parse state to get return_url and workspace_id
    return_url = "/settings"
    workspace_id = None
    parsed_profile_id = profile_id

    if state:
        try:
            state_data = json.loads(base64.urlsafe_b64decode(state).decode())
            return_url = state_data.get("return_url", "/settings")
            workspace_id = state_data.get("workspace_id")
            if not parsed_profile_id:
                parsed_profile_id = state_data.get("profile_id")
        except Exception as e:
            logger.warning(f"Failed to parse OAuth state: {e}, using defaults")

    if error:
        logger.error(f"OAuth error for {provider}: {error} - {error_description}")
        # Resolve the frontend URL from port configuration.
        try:
            from backend.app.services.port_config_service import port_config_service
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
            from backend.app.services.service_endpoint_registry import service_endpoint_registry

            frontend_url = (
                os.getenv("FRONTEND_URL")
                or service_endpoint_registry.get_endpoint_url(
                    "local_core.web_console", "browser_public"
                )
                or ""
            )
        error_params = urlencode({
            "error": error,
            "error_description": error_description or "",
        })
        redirect_url = f"{frontend_url}{return_url}?oauth_error=1&{error_params}"
        return RedirectResponse(url=redirect_url)

    if provider not in OAUTH_CONFIGS:
        raise_api_error(400, f"Unsupported provider: {provider}")

    config = OAUTH_CONFIGS[provider]

    # Get OAuth credentials from connection config (preferred) or environment variables
    client_id = None
    client_secret = None

    if not parsed_profile_id:
        raise_api_error(400, "Profile ID is required (either in state or as query parameter)")

    # Try to get from existing connection
    existing_connections = registry.get_connections_by_tool_type(parsed_profile_id, provider)
    if existing_connections:
        conn = existing_connections[0]
        if conn.config and isinstance(conn.config, dict):
            client_id = conn.config.get("client_id")
            client_secret = conn.config.get("client_secret")

    # Fallback to environment variables
    if not client_id:
        client_id = os.getenv(config["client_id_env"])
    if not client_secret:
        client_secret = os.getenv(config["client_secret_env"])

    if not client_id or not client_secret:
        raise_api_error(
            400,
            f"OAuth credentials not configured. Please configure Client ID and Client Secret in the connection settings."
        )

    # Get redirect URI
    redirect_uri = get_redirect_uri(request, provider)

    # Exchange code for access token
    try:
        token_data = await exchange_code_for_token(
            provider=provider,
            code=code,
            redirect_uri=redirect_uri,
            client_id=client_id,
            client_secret=client_secret,
        )
    except Exception as e:
        logger.error(f"Failed to exchange token for {provider}: {str(e)}")
        # Resolve the frontend URL from port configuration.
        try:
            from backend.app.services.port_config_service import port_config_service
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
            from backend.app.services.service_endpoint_registry import service_endpoint_registry

            frontend_url = (
                os.getenv("FRONTEND_URL")
                or service_endpoint_registry.get_endpoint_url(
                    "local_core.web_console", "browser_public"
                )
                or ""
            )
        error_params = urlencode({
            "error": "token_exchange_failed",
            "error_description": str(e),
            "provider": provider,
        })
        redirect_url = f"{frontend_url}{return_url}?oauth_error=1&{error_params}"
        return RedirectResponse(url=redirect_url)

    # Create or update connection
    import uuid
    connection_id = f"{provider}-{uuid.uuid4().hex[:8]}"

    # Check if connection already exists
    existing_connections = registry.get_connections_by_tool_type(parsed_profile_id, provider)
    if existing_connections:
        connection = existing_connections[0]
        connection_id = connection.id
        # Update existing connection
        connection.oauth_token = token_data["access_token"]
        connection.oauth_refresh_token = token_data.get("refresh_token")
        connection.is_validated = True
        connection.last_validated_at = _utc_now()
        registry.update_connection(connection)
    else:
        # Create new connection
        connection = ToolConnectionModel(
            id=connection_id,
            profile_id=parsed_profile_id,
            tool_type=provider,
            connection_type="local",
            name=f"{provider.title()} Account",
            api_key=token_data["access_token"],
            oauth_token=token_data["access_token"],
            oauth_refresh_token=token_data.get("refresh_token"),
            is_active=True,
            is_validated=True,
            last_validated_at=_utc_now(),
        )
        registry.create_connection(connection)

    # Automatically discover tools after OAuth connection
    try:
        from backend.app.services.tools.discovery_provider import ToolConfig
        discovery_config = ToolConfig(
            tool_type=provider,
            connection_type="http_api",
            api_key=token_data["access_token"],
        )
        discovery_result = await registry.discover_tool_capabilities(
            provider_name=provider,
            config=discovery_config,
            connection_id=connection_id,
            profile_id=parsed_profile_id,
        )
        logger.info(
            f"Auto-discovered {len(discovery_result.get('discovered_tools', []))} tools "
            f"for {provider} connection {connection_id}"
        )
    except Exception as e:
        logger.warning(f"Failed to auto-discover tools for {provider}: {str(e)}")
        # Don't fail the OAuth flow if discovery fails

    # Redirect to frontend success page (use return_url from state)
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3001")
    redirect_url = f"{frontend_url}{return_url}?oauth_success=1&connection_id={connection_id}"
    if workspace_id:
        redirect_url += f"&workspace_id={workspace_id}"
    return RedirectResponse(url=redirect_url)
