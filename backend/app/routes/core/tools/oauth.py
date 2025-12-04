"""
OAuth 2.0 authentication routes for social media integrations

Handles OAuth 2.0 flow for social media platforms:
- Generate authorization URLs
- Handle OAuth callbacks
- Exchange authorization codes for access tokens
- Refresh access tokens
"""
import os
import secrets
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
import httpx
from urllib.parse import urlencode, parse_qs, urlparse

from backend.app.services.tool_registry import ToolRegistryService
from backend.app.models.tool_registry import ToolConnectionModel
from .base import get_tool_registry, raise_api_error

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/tools/oauth", tags=["tools", "oauth"])


# OAuth configuration for each platform
OAUTH_CONFIGS: Dict[str, Dict[str, Any]] = {
    "twitter": {
        "authorize_url": "https://twitter.com/i/oauth2/authorize",
        "token_url": "https://api.twitter.com/2/oauth2/token",
        "scopes": ["tweet.read", "tweet.write", "users.read", "offline.access"],
        "client_id_env": "TWITTER_CLIENT_ID",
        "client_secret_env": "TWITTER_CLIENT_SECRET",
    },
    "facebook": {
        "authorize_url": "https://www.facebook.com/v18.0/dialog/oauth",
        "token_url": "https://graph.facebook.com/v18.0/oauth/access_token",
        "scopes": ["pages_manage_posts", "pages_read_engagement", "pages_show_list"],
        "client_id_env": "FACEBOOK_CLIENT_ID",
        "client_secret_env": "FACEBOOK_CLIENT_SECRET",
    },
    "instagram": {
        "authorize_url": "https://api.instagram.com/oauth/authorize",
        "token_url": "https://api.instagram.com/oauth/access_token",
        "scopes": ["user_profile", "user_media"],
        "client_id_env": "INSTAGRAM_CLIENT_ID",
        "client_secret_env": "INSTAGRAM_CLIENT_SECRET",
    },
    "linkedin": {
        "authorize_url": "https://www.linkedin.com/oauth/v2/authorization",
        "token_url": "https://www.linkedin.com/oauth/v2/accessToken",
        "scopes": ["openid", "profile", "email", "w_member_social"],
        "client_id_env": "LINKEDIN_CLIENT_ID",
        "client_secret_env": "LINKEDIN_CLIENT_SECRET",
    },
    "youtube": {
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "scopes": [
            "https://www.googleapis.com/auth/youtube.upload",
            "https://www.googleapis.com/auth/youtube.readonly",
            "https://www.googleapis.com/auth/youtube.force-ssl",
        ],
        "client_id_env": "GOOGLE_CLIENT_ID",
        "client_secret_env": "GOOGLE_CLIENT_SECRET",
    },
    "line": {
        "authorize_url": "https://access.line.me/oauth2/v2.1/authorize",
        "token_url": "https://api.line.me/oauth2/v2.1/token",
        "scopes": ["profile", "openid", "email"],
        "client_id_env": "LINE_CHANNEL_ID",
        "client_secret_env": "LINE_CHANNEL_SECRET",
    },
}


class OAuthAuthorizeRequest(BaseModel):
    """Request to generate OAuth authorization URL"""
    redirect_uri: str
    state: Optional[str] = None


class OAuthCallbackRequest(BaseModel):
    """OAuth callback request"""
    code: str
    state: Optional[str] = None


class OAuthTokenResponse(BaseModel):
    """OAuth token response"""
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "Bearer"
    expires_in: Optional[int] = None
    scope: Optional[str] = None


def get_redirect_uri(request: Request, provider: str) -> str:
    """Generate redirect URI for OAuth callback"""
    base_url = str(request.base_url).rstrip("/")
    return f"{base_url}/api/v1/tools/oauth/{provider}/callback"


@router.get("/{provider}/authorize")
async def get_authorize_url(
    request: Request,
    provider: str,
    redirect_uri: str = Query(..., description="OAuth redirect URI"),
    state: Optional[str] = Query(None, description="OAuth state parameter"),
    profile_id: str = Query(..., description="Profile ID"),
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

    # Generate state if not provided
    if not state:
        state = secrets.token_urlsafe(32)

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
    profile_id: str = Query(..., description="Profile ID"),
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
    if error:
        logger.error(f"OAuth error for {provider}: {error} - {error_description}")
        # Redirect to frontend error page
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3001")
        error_params = urlencode({
            "error": error,
            "error_description": error_description or "",
        })
        return RedirectResponse(url=f"{frontend_url}/settings?tab=social_media&provider={provider}&oauth_error=1&{error_params}")

    if provider not in OAUTH_CONFIGS:
        raise_api_error(400, f"Unsupported provider: {provider}")

    config = OAUTH_CONFIGS[provider]

    # Get OAuth credentials from connection config (preferred) or environment variables
    client_id = None
    client_secret = None

    # Try to get from existing connection
    existing_connections = registry.get_connections_by_tool_type(profile_id, provider)
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
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3001")
        error_params = urlencode({
            "error": "token_exchange_failed",
            "error_description": str(e),
            "provider": provider,
        })
        return RedirectResponse(url=f"{frontend_url}/settings?tab=social_media&provider={provider}&oauth_error=1&{error_params}")

    # Create or update connection
    import uuid
    connection_id = f"{provider}-{uuid.uuid4().hex[:8]}"

    # Check if connection already exists
    existing_connections = registry.get_connections_by_tool_type(profile_id, provider)
    if existing_connections:
        connection = existing_connections[0]
        connection_id = connection.id
        # Update existing connection
        connection.oauth_token = token_data["access_token"]
        connection.oauth_refresh_token = token_data.get("refresh_token")
        connection.is_validated = True
        connection.last_validated_at = datetime.utcnow()
        registry.update_connection(connection)
    else:
        # Create new connection
        connection = ToolConnectionModel(
            id=connection_id,
            profile_id=profile_id,
            tool_type=provider,
            connection_type="local",
            name=f"{provider.title()} Account",
            api_key=token_data["access_token"],
            oauth_token=token_data["access_token"],
            oauth_refresh_token=token_data.get("refresh_token"),
            is_active=True,
            is_validated=True,
            last_validated_at=datetime.utcnow(),
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
            profile_id=profile_id,
        )
        logger.info(
            f"Auto-discovered {len(discovery_result.get('discovered_tools', []))} tools "
            f"for {provider} connection {connection_id}"
        )
    except Exception as e:
        logger.warning(f"Failed to auto-discover tools for {provider}: {str(e)}")
        # Don't fail the OAuth flow if discovery fails

    # Redirect to frontend success page
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3001")
    return RedirectResponse(
        url=f"{frontend_url}/settings?tab=social_media&provider={provider}&oauth_success=1&connection_id={connection_id}"
    )


async def exchange_code_for_token(
    provider: str,
    code: str,
    redirect_uri: str,
    client_id: str,
    client_secret: str,
) -> Dict[str, Any]:
    """
    Exchange OAuth authorization code for access token

    Args:
        provider: Social media platform
        code: OAuth authorization code
        redirect_uri: OAuth redirect URI
        client_id: OAuth client ID
        client_secret: OAuth client secret

    Returns:
        Token data (access_token, refresh_token, etc.)
    """
    config = OAUTH_CONFIGS[provider]

    # Prepare token request data
    token_data = {
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "client_secret": client_secret,
    }

    # Platform-specific token request parameters
    if provider == "twitter":
        token_data["grant_type"] = "authorization_code"
        token_data["code_verifier"] = "challenge"  # PKCE support (simplified)
    elif provider == "youtube":
        token_data["grant_type"] = "authorization_code"
    elif provider == "line":
        token_data["grant_type"] = "authorization_code"
        # Line requires client_id and client_secret in the request body
        token_data["client_id"] = client_id
        token_data["client_secret"] = client_secret
    else:
        token_data["grant_type"] = "authorization_code"

    # Make token request
    async with httpx.AsyncClient() as client:
        response = await client.post(
            config["token_url"],
            data=token_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        if response.status_code != 200:
            error_detail = response.text
            try:
                error_json = response.json()
                error_detail = error_json.get("error_description", error_json.get("error", error_detail))
            except:
                pass
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Token exchange failed: {error_detail}"
            )

        token_response = response.json()

        # Normalize token response
        result = {
            "access_token": token_response.get("access_token") or token_response.get("accessToken"),
            "token_type": token_response.get("token_type", "Bearer"),
            "expires_in": token_response.get("expires_in") or token_response.get("expiresIn"),
            "scope": token_response.get("scope"),
        }

        # Handle refresh token
        refresh_token = token_response.get("refresh_token") or token_response.get("refreshToken")
        if refresh_token:
            result["refresh_token"] = refresh_token

        return result


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
            connection.last_validated_at = datetime.utcnow()
            registry.update_connection(connection)

            return {
                "access_token": new_access_token,
                "refresh_token": new_refresh_token,
                "expires_in": token_response.get("expires_in"),
            }

    except Exception as e:
        logger.error(f"Failed to refresh token for {provider}: {str(e)}")
        raise_api_error(500, f"Token refresh failed: {str(e)}")

