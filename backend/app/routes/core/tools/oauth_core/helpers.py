from typing import Any, Dict

import httpx
from fastapi import HTTPException, Request

from .state import OAUTH_CONFIGS

def get_redirect_uri(request: Request, provider: str) -> str:
    """Generate redirect URI for OAuth callback"""
    base_url = str(request.base_url).rstrip("/")
    return f"{base_url}/api/v1/tools/oauth/{provider}/callback"


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
            except Exception:
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
