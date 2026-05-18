"""Tool OAuth route compatibility facade."""

from .oauth_core.authorize_routes import get_authorize_url, oauth_callback
from .oauth_core.helpers import exchange_code_for_token, get_redirect_uri
from .oauth_core.refresh_routes import refresh_token
from .oauth_core.router import router
from .oauth_core.schemas import (
    OAuthAuthorizeRequest,
    OAuthCallbackRequest,
    OAuthTokenResponse,
)
from .oauth_core.state import OAUTH_CONFIGS, _utc_now, logger

__all__ = [
    "OAUTH_CONFIGS",
    "OAuthAuthorizeRequest",
    "OAuthCallbackRequest",
    "OAuthTokenResponse",
    "_utc_now",
    "exchange_code_for_token",
    "get_authorize_url",
    "get_redirect_uri",
    "logger",
    "oauth_callback",
    "refresh_token",
    "router",
]
