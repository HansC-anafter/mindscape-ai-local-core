from typing import Optional

from pydantic import BaseModel

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
