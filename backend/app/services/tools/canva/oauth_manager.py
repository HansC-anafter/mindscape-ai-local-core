"""
Canva OAuth Manager

Handles OAuth 2.0 authorization flow for Canva Connect API integration.
Implements PKCE (Proof Key for Code Exchange) flow as required by Canva.
"""

import os
import secrets
import json
import base64
import hashlib
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from urllib.parse import urlencode
import aiohttp
import logging

logger = logging.getLogger(__name__)


class CanvaOAuthManager:
    """
    Manages Canva OAuth 2.0 flow with PKCE

    Responsibilities:
    - Generate PKCE code verifier and challenge
    - Build Canva OAuth authorization URLs
    - Exchange authorization codes for access tokens
    - Store OAuth state temporarily
    """

    CANVA_AUTH_URL = "https://www.canva.com/api/oauth/authorize"
    CANVA_TOKEN_URL = "https://api.canva.com/rest/v1/oauth/token"

    def __init__(self, data_dir: str = "./data"):
        self.data_dir = data_dir

        # OAuth state storage (in-memory, expires after 10 minutes)
        self._oauth_states: Dict[str, Dict[str, Any]] = {}
        self._code_verifiers: Dict[str, str] = {}  # Store code verifiers for PKCE

    def generate_pkce_pair(self) -> tuple[str, str]:
        """
        Generate PKCE code verifier and challenge

        Returns:
            Tuple of (code_verifier, code_challenge)
        """
        # Generate code verifier (random string, 43-128 characters)
        code_verifier = secrets.token_urlsafe(32)

        # Generate code challenge (SHA256 hash of verifier, base64url encoded)
        code_challenge_bytes = hashlib.sha256(code_verifier.encode()).digest()
        code_challenge = base64.urlsafe_b64encode(code_challenge_bytes).decode().rstrip('=')

        return code_verifier, code_challenge

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
        client_id: str,
        redirect_uri: str,
        scopes: Optional[List[str]] = None,
        connection_id: Optional[str] = None,
        connection_name: Optional[str] = None
    ) -> tuple[str, str]:
        """
        Build Canva OAuth authorization URL with PKCE

        Args:
            client_id: Canva OAuth Client ID
            redirect_uri: OAuth redirect URI
            scopes: List of OAuth scopes (default: basic scopes)
            connection_id: Optional connection ID for state
            connection_name: Optional connection name

        Returns:
            Tuple of (authorization_url, code_verifier)
        """
        if scopes is None:
            scopes = ["design:read", "design:write", "template:read"]

        # Generate PKCE pair
        code_verifier, code_challenge = self.generate_pkce_pair()

        # Generate state token
        state_token = self.generate_state_token(connection_id or "canva", connection_name)

        # Store code verifier for later use
        self._code_verifiers[state_token] = code_verifier

        # Build authorization URL
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(scopes),
            "state": state_token,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256"
        }

        auth_url = f"{self.CANVA_AUTH_URL}?{urlencode(params)}"

        logger.info(f"Generated Canva OAuth authorization URL for connection: {connection_id}")
        return auth_url, code_verifier

    async def exchange_code_for_token(
        self,
        code: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        code_verifier: str
    ) -> Dict[str, Any]:
        """
        Exchange authorization code for access token

        Args:
            code: Authorization code from callback
            client_id: Canva OAuth Client ID
            client_secret: Canva OAuth Client Secret
            redirect_uri: OAuth redirect URI (must match authorization request)
            code_verifier: PKCE code verifier

        Returns:
            Token response with access_token, refresh_token, etc.
        """
        token_data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier
        }

        # Use Basic Authentication (recommended by Canva)
        auth = aiohttp.BasicAuth(client_id, client_secret)

        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.CANVA_TOKEN_URL,
                data=token_data,
                auth=auth,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Token exchange failed: {response.status} - {error_text}")

                token_response = await response.json()

                logger.info("Successfully exchanged authorization code for access token")
                return token_response

    async def refresh_access_token(
        self,
        refresh_token: str,
        client_id: str,
        client_secret: str
    ) -> Dict[str, Any]:
        """
        Refresh access token using refresh token

        Args:
            refresh_token: Refresh token
            client_id: Canva OAuth Client ID
            client_secret: Canva OAuth Client Secret

        Returns:
            Token response with new access_token
        """
        token_data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token
        }

        auth = aiohttp.BasicAuth(client_id, client_secret)

        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.CANVA_TOKEN_URL,
                data=token_data,
                auth=auth,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Token refresh failed: {response.status} - {error_text}")

                token_response = await response.json()
                logger.info("Successfully refreshed access token")
                return token_response

    def get_code_verifier(self, state_token: str) -> Optional[str]:
        """Get code verifier for a state token"""
        return self._code_verifiers.get(state_token)

    def cleanup_state(self, state_token: str):
        """Clean up OAuth state and code verifier"""
        if state_token in self._oauth_states:
            del self._oauth_states[state_token]
        if state_token in self._code_verifiers:
            del self._code_verifiers[state_token]


# Global instance
_oauth_manager = CanvaOAuthManager()


def get_canva_oauth_manager() -> CanvaOAuthManager:
    """Get global Canva OAuth manager instance"""
    return _oauth_manager
