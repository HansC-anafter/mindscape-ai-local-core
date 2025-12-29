"""
Google Drive OAuth Manager

Handles OAuth 2.0 authorization flow for Google Drive integration.
"""
import os
import secrets
import json
import base64
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from urllib.parse import urlencode
import aiohttp
import logging

logger = logging.getLogger(__name__)


class GoogleDriveOAuthManager:
    """
    Manages Google Drive OAuth 2.0 flow

    Responsibilities:
    - Generate and validate OAuth state tokens (CSRF protection)
    - Build Google OAuth authorization URLs
    - Exchange authorization codes for access tokens
    - Store OAuth state temporarily
    """

    def __init__(self, data_dir: str = "./data"):
        self.data_dir = data_dir

        # Load configuration from system settings first, fallback to environment variables
        self._load_configuration()

        # OAuth state storage (in-memory, expires after 10 minutes)
        self._oauth_states: Dict[str, Dict[str, Any]] = {}

        # Validate required configuration
        if not self.client_id or not self.client_secret:
            logger.warning(
                "Google OAuth credentials not configured. "
                "Configure via System Settings or set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET environment variables."
            )

    def _load_configuration(self):
        """Load OAuth configuration from system settings, fallback to environment variables"""
        try:
            from ...system_settings_store import SystemSettingsStore
            settings_store = SystemSettingsStore()

            # Try to load from system settings
            client_id_setting = settings_store.get_setting("google_oauth_client_id")
            client_secret_setting = settings_store.get_setting("google_oauth_client_secret")
            redirect_uri_setting = settings_store.get_setting("google_oauth_redirect_uri")
            backend_url_setting = settings_store.get_setting("backend_url")

            # Use system settings if available, otherwise use environment variables
            self.client_id = (
                str(client_id_setting.value) if client_id_setting and client_id_setting.value
                else os.getenv("GOOGLE_CLIENT_ID")
            )

            self.client_secret = (
                str(client_secret_setting.value) if client_secret_setting and client_secret_setting.value
                else os.getenv("GOOGLE_CLIENT_SECRET")
            )

            # For redirect URI, prefer system setting, then env var, then default
            redirect_uri_from_setting = (
                str(redirect_uri_setting.value) if redirect_uri_setting and redirect_uri_setting.value
                else None
            )
            redirect_uri_from_env = os.getenv("GOOGLE_REDIRECT_URI")

            if redirect_uri_from_setting:
                self.redirect_uri = redirect_uri_from_setting
            elif redirect_uri_from_env:
                self.redirect_uri = redirect_uri_from_env
            else:
                # Auto-generate from backend URL
                backend_url = self._get_backend_url(backend_url_setting)
                self.redirect_uri = f"{backend_url}/api/tools/google-drive/oauth/callback"

            self.backend_url = self._get_backend_url(backend_url_setting)

        except Exception as e:
            logger.warning(f"Failed to load OAuth config from system settings: {e}, using environment variables")
            # Fallback to environment variables only
            self.client_id = os.getenv("GOOGLE_CLIENT_ID")
            self.client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
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
                self.backend_url = backend_url
                self.redirect_uri = f"{backend_url}/api/tools/google-drive/oauth/callback"
            except Exception:
                # 回退到环境变量或默认值
                self.backend_url = os.getenv("BACKEND_URL", "http://localhost:8200")
            self.redirect_uri = os.getenv(
                "GOOGLE_REDIRECT_URI",
                    f"{self.backend_url}/api/tools/google-drive/oauth/callback"
            )

    def _get_backend_url(self, backend_url_setting=None):
        """Get backend URL from system settings or environment variable"""
        if backend_url_setting and backend_url_setting.value:
            return str(backend_url_setting.value)
        # 从端口配置服务获取后端 URL
        try:
            from ....services.port_config_service import port_config_service
            import os
            current_cluster = os.getenv('CLUSTER_NAME')
            current_env = os.getenv('ENVIRONMENT')
            current_site = os.getenv('SITE_NAME')
            return port_config_service.get_service_url(
                'backend_api',
                cluster=current_cluster,
                environment=current_env,
                site=current_site
            )
        except Exception:
            # 回退到环境变量或默认值
            return os.getenv("BACKEND_URL", "http://localhost:8200")

    def reload_configuration(self):
        """Reload configuration from system settings (useful after settings update)"""
        self._load_configuration()

    def generate_state_token(self, connection_id: str, connection_name: Optional[str] = None) -> str:
        """
        Generate a secure state token for OAuth flow (CSRF protection)

        Args:
            connection_id: Connection identifier
            connection_name: Optional connection name

        Returns:
            Base64-encoded state token
        """
        # Generate random state string
        random_state = secrets.token_urlsafe(32)

        # Create state payload
        state_data = {
            "random": random_state,
            "connection_id": connection_id,
            "connection_name": connection_name,
            "timestamp": datetime.now().isoformat()
        }

        # Encode to base64
        state_json = json.dumps(state_data)
        state_token = base64.urlsafe_b64encode(state_json.encode()).decode().rstrip('=')

        # Store state with expiration (10 minutes)
        self._oauth_states[state_token] = {
            "connection_id": connection_id,
            "connection_name": connection_name,
            "created_at": datetime.now(),
            "expires_at": datetime.now() + timedelta(minutes=10)
        }

        logger.info(f"Generated OAuth state token for connection: {connection_id}")
        return state_token

    def validate_state_token(self, state_token: str) -> Optional[Dict[str, Any]]:
        """
        Validate OAuth state token

        Args:
            state_token: State token to validate

        Returns:
            State data if valid, None otherwise
        """
        # Check if state exists
        if state_token not in self._oauth_states:
            logger.warning(f"Invalid OAuth state token: {state_token}")
            return None

        state_data = self._oauth_states[state_token]

        # Check expiration
        if datetime.now() > state_data["expires_at"]:
            logger.warning(f"OAuth state token expired: {state_token}")
            del self._oauth_states[state_token]
            return None

        # Return state data
        result = {
            "connection_id": state_data["connection_id"],
            "connection_name": state_data.get("connection_name")
        }

        # Clean up (one-time use)
        del self._oauth_states[state_token]

        return result

    def build_authorization_url(self, state_token: str, scopes: Optional[List[str]] = None) -> str:
        """
        Build Google OAuth 2.0 authorization URL

        Args:
            state_token: OAuth state token
            scopes: Optional list of OAuth scopes. If not provided, defaults to Google Drive read-only scope.

        Returns:
            Google OAuth authorization URL
        """
        if not self.client_id:
            raise ValueError("GOOGLE_CLIENT_ID not configured")

        # Google OAuth 2.0 authorization endpoint
        auth_url = "https://accounts.google.com/o/oauth2/v2/auth"

        # Default scopes for Google Drive read-only access
        if scopes is None:
            scopes = [
                "https://www.googleapis.com/auth/drive.readonly"
            ]
        scope_string = " ".join(scopes)

        # Build query parameters
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": scope_string,
            "state": state_token,
            "access_type": "offline",  # Required to get refresh_token
            "prompt": "consent"  # Force consent screen to get refresh_token
        }

        authorization_url = f"{auth_url}?{urlencode(params)}"
        logger.info(f"Built Google OAuth authorization URL for state: {state_token[:20]}...")

        return authorization_url

    async def exchange_code_for_tokens(self, authorization_code: str) -> Dict[str, Any]:
        """
        Exchange authorization code for access token and refresh token

        Args:
            authorization_code: Authorization code from OAuth callback

        Returns:
            Dictionary containing access_token, refresh_token, expires_in, etc.

        Raises:
            ValueError: If token exchange fails
        """
        if not self.client_id or not self.client_secret:
            raise ValueError("Google OAuth credentials not configured")

        token_url = "https://oauth2.googleapis.com/token"

        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": authorization_code,
            "grant_type": "authorization_code",
            "redirect_uri": self.redirect_uri
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    token_url,
                    data=payload,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Google OAuth token exchange failed: {response.status} - {error_text}")
                        raise ValueError(f"Token exchange failed: {error_text}")

                    token_data = await response.json()

                    logger.info("Successfully exchanged authorization code for tokens")

                    return {
                        "access_token": token_data.get("access_token"),
                        "refresh_token": token_data.get("refresh_token"),
                        "expires_in": token_data.get("expires_in", 3600),
                        "token_type": token_data.get("token_type", "Bearer"),
                        "scope": token_data.get("scope")
                    }

        except aiohttp.ClientError as e:
            logger.error(f"Network error during token exchange: {e}")
            raise ValueError(f"Network error: {str(e)}")

    async def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        """
        Refresh access token using refresh token

        Args:
            refresh_token: Refresh token

        Returns:
            Dictionary containing new access_token, expires_in, etc.
        """
        if not self.client_id or not self.client_secret:
            raise ValueError("Google OAuth credentials not configured")

        token_url = "https://oauth2.googleapis.com/token"

        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token"
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    token_url,
                    data=payload,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Token refresh failed: {response.status} - {error_text}")
                        raise ValueError(f"Token refresh failed: {error_text}")

                    token_data = await response.json()

                    logger.info("Successfully refreshed access token")

                    return {
                        "access_token": token_data.get("access_token"),
                        "expires_in": token_data.get("expires_in", 3600),
                        "token_type": token_data.get("token_type", "Bearer")
                    }

        except aiohttp.ClientError as e:
            logger.error(f"Network error during token refresh: {e}")
            raise ValueError(f"Network error: {str(e)}")

    def cleanup_expired_states(self):
        """Remove expired OAuth states (call periodically)"""
        now = datetime.now()
        expired_keys = [
            key for key, state in self._oauth_states.items()
            if now > state["expires_at"]
        ]
        for key in expired_keys:
            del self._oauth_states[key]

        if expired_keys:
            logger.info(f"Cleaned up {len(expired_keys)} expired OAuth states")
