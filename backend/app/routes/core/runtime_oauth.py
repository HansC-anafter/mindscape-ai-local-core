"""Runtime OAuth route compatibility facade."""

from .runtime_oauth_core.authorize_routes import authorize
from .runtime_oauth_core.callback_routes import (
    _handle_gca_callback,
    _handle_provider_callback,
    callback,
)
from .runtime_oauth_core.credentials import (
    _commit_runtime_registration,
    _get_oauth_credentials,
)
from .runtime_oauth_core.dependencies import User, get_current_user, get_db
from .runtime_oauth_core.responses import _close_window_html, _popup_close_response
from .runtime_oauth_core.router import router
from .runtime_oauth_core.state import _pending_states, auth_service, logger
from .runtime_oauth_core.token_routes import (
    disconnect,
    provider_jwt_landing,
    status,
    store_token,
)

__all__ = [
    "User",
    "_close_window_html",
    "_commit_runtime_registration",
    "_get_oauth_credentials",
    "_handle_gca_callback",
    "_handle_provider_callback",
    "_pending_states",
    "_popup_close_response",
    "auth_service",
    "authorize",
    "callback",
    "disconnect",
    "get_current_user",
    "get_db",
    "logger",
    "provider_jwt_landing",
    "router",
    "status",
    "store_token",
]
