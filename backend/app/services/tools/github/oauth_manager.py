"""
GitHub OAuth Manager

Handles OAuth 2.0 authorization flow for GitHub integration.
"""
import os
import secrets
import json
import base64
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from urllib.parse import urlencode
import aiohttp
import logging

logger = logging.getLogger(__name__)


class GitHubOAuthManager:
    """
    Manages GitHub OAuth 2.0 flow

    Responsibilities:
    - Generate and validate OAuth state tokens (CSRF protection)
    - Build GitHub OAuth authorization URLs
    - Exchange authorization codes for access tokens
    - Store OAuth state temporarily
    """

    GITHUB_AUTH_URL = "https://github.com/login/oauth/authorize"
    GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"

    def __init__(self, data_dir: str = "./data"):
        self.data_dir = data_dir

        # Load configuration from environment variables
        self.client_id = os.getenv("GITHUB_CLIENT_ID")
        self.client_secret = os.getenv("GITHUB_CLIENT_SECRET")
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
            self.redirect_uri = os.getenv(
                "GITHUB_REDIRECT_URI",
                f"{backend_url}/api/v1/tools/github/oauth/callback"
            )
        except Exception:
            # 回退到环境变量或默认值
        self.redirect_uri = os.getenv(
            "GITHUB_REDIRECT_URI",
                "http://localhost:8200/api/v1/tools/github/oauth/callback"
        )

        # OAuth state storage (in-memory, expires after 10 minutes)
        self._oauth_states: Dict[str, Dict[str, Any]] = {}

        if not self.client_id or not self.client_secret:
            logger.warning(
                "GitHub OAuth credentials not configured. "
                "Set GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET environment variables."
            )

    def generate_state_token(self, connection_id: str, connection_name: Optional[str] = None) -> str:
        """
        Generate a secure state token for OAuth flow (CSRF protection)

        Args:
            connection_id: Connection identifier
            connection_name: Optional connection name

        Returns:
            Base64-encoded state token
        """
        random_state = secrets.token_urlsafe(32)

        state_data = {
            "random": random_state,
            "connection_id": connection_id,
            "connection_name": connection_name,
            "timestamp": datetime.now().isoformat()
        }

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
        if state_token not in self._oauth_states:
            return None

        state_data = self._oauth_states[state_token]

        # Check expiration
        if datetime.now() > state_data["expires_at"]:
            del self._oauth_states[state_token]
            return None

        return state_data

    def build_authorization_url(
        self,
        scopes: Optional[List[str]] = None,
        connection_id: Optional[str] = None,
        connection_name: Optional[str] = None,
        client_id: Optional[str] = None
    ) -> str:
        """
        Build GitHub OAuth authorization URL

        Args:
            scopes: List of OAuth scopes (default: repo scope)
            connection_id: Optional connection ID for state
            connection_name: Optional connection name
            client_id: Optional client ID (overrides env var)

        Returns:
            Authorization URL
        """
        if scopes is None:
            scopes = [
                "repo",
                "read:org",
                "read:user"
            ]

        if not client_id:
            client_id = self.client_id

        if not client_id:
            raise ValueError("GitHub Client ID is required")

        # Generate state token
        state_token = self.generate_state_token(connection_id or "github", connection_name)

        # Build authorization URL
        params = {
            "client_id": client_id,
            "scope": ",".join(scopes),
            "redirect_uri": self.redirect_uri,
            "state": state_token
        }

        auth_url = f"{self.GITHUB_AUTH_URL}?{urlencode(params)}"
        logger.info(f"Built GitHub OAuth authorization URL for connection: {connection_id}")
        return auth_url

    async def exchange_code_for_token(
        self,
        code: str,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Exchange authorization code for access token

        Args:
            code: Authorization code from OAuth callback
            client_id: Optional client ID (overrides env var)
            client_secret: Optional client secret (overrides env var)

        Returns:
            Token response with access_token, scope, token_type, etc.
        """
        if not client_id:
            client_id = self.client_id
        if not client_secret:
            client_secret = self.client_secret

        if not client_id or not client_secret:
            raise ValueError("GitHub Client ID and Client Secret are required")

        url = self.GITHUB_TOKEN_URL

        data = {
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": self.redirect_uri
        }

        headers = {
            "Accept": "application/json"
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=data, headers=headers) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"GitHub OAuth token exchange failed: {response.status} - {error_text}")

                result = await response.json()

                if "error" in result:
                    error = result.get("error_description", result.get("error", "Unknown error"))
                    raise Exception(f"GitHub OAuth error: {error}")

                return result


def get_github_oauth_manager(data_dir: str = "./data") -> GitHubOAuthManager:
    """Get GitHub OAuth manager instance"""
    return GitHubOAuthManager(data_dir=data_dir)

