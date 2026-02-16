"""
Agent Dispatch — Authentication mixin.

Handles HMAC nonce challenge-response and token verification
for IDE agent WebSocket connections.
"""

import hashlib
import hmac
import logging
import secrets
from typing import Any, Dict, Optional

from .models import AgentClient

logger = logging.getLogger(__name__)


class AuthMixin:
    """Mixin: agent authentication (token + HMAC nonce challenge-response)."""

    def generate_challenge(self, client_id: str) -> Dict[str, str]:
        """Generate a nonce challenge for client authentication."""
        nonce = secrets.token_hex(32)
        self._nonces[client_id] = nonce
        return {
            "type": "auth_challenge",
            "nonce": nonce,
        }

    def verify_auth(
        self,
        client_id: str,
        token: str,
        nonce_response: str,
    ) -> bool:
        """
        Verify client authentication.

        The client must provide:
          - token: a pre-shared agent token
          - nonce_response: HMAC-SHA256(auth_secret, nonce + client_id)

        Security:
          - Both secrets None = dev mode (fail-open)
          - Either set = prod mode (fail-closed, both verified)
        """
        if not self._auth_required:
            return True  # Dev mode — both secrets empty

        # Verify pre-shared token
        if not self._expected_token or not token:
            logger.warning(f"[AgentWS] Token missing for client {client_id}")
            return False
        if not hmac.compare_digest(token, self._expected_token):
            logger.warning(f"[AgentWS] Invalid token for client {client_id}")
            return False

        # Verify HMAC nonce
        if not self.auth_secret:
            logger.warning(
                f"[AgentWS] auth_secret missing, cannot verify HMAC "
                f"for client {client_id}"
            )
            return False

        expected_nonce = self._nonces.pop(client_id, None)
        if not expected_nonce:
            logger.warning(f"[AgentWS] No pending nonce for client {client_id}")
            return False

        # Verify HMAC
        expected_hmac = hmac.new(
            self.auth_secret.encode(),
            (expected_nonce + client_id).encode(),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(nonce_response, expected_hmac):
            logger.warning(f"[AgentWS] HMAC mismatch for client {client_id}")
            return False

        return True

    async def _handle_auth_response(
        self,
        client: AgentClient,
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Process client authentication response."""
        token = data.get("token", "")
        nonce_response = data.get("nonce_response", "")

        if self.verify_auth(client.client_id, token, nonce_response):
            client.authenticated = True
            logger.info(f"[AgentWS] Client {client.client_id} authenticated")

            # Flush any pending tasks
            flushed = await self.flush_pending(
                client.workspace_id,
                client,
            )

            return {
                "type": "auth_ok",
                "client_id": client.client_id,
                "flushed_tasks": flushed,
            }
        else:
            logger.warning(f"[AgentWS] Client {client.client_id} auth failed")
            return {
                "type": "auth_failed",
                "error": "Authentication failed",
            }
