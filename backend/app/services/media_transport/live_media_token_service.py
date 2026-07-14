"""RS256 token issuance and public JWKS export for MediaMTX."""

from __future__ import annotations

import base64
import json
import secrets
import stat
import time
from pathlib import Path
from typing import Callable, Literal

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from jose import jwt
from jose.exceptions import JWSError

from backend.app.models.media_transport import (
    LiveMediaSessionDescriptor,
    LiveMediaSessionTokens,
)

from .live_media_config import LiveMediaConfig


MediaAccessRole = Literal["publisher", "preview", "receiver"]


class LiveMediaTokenError(RuntimeError):
    """Raised when signing material is missing or violates key policy."""


def _base64url_uint(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8, byteorder="big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


class LiveMediaTokenService:
    """Issue exact-path MediaMTX JWTs without persisting credentials."""

    def __init__(
        self,
        config: LiveMediaConfig,
        *,
        now: Callable[[], float] = time.time,
    ) -> None:
        self._config = config
        self._now = now
        self._private_key = self._load_private_key(config.jwt_private_key_path)
        self._signing_key_pem = self._private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("ascii")

    @staticmethod
    def _load_private_key(path: Path) -> RSAPrivateKey:
        try:
            file_mode = stat.S_IMODE(path.stat().st_mode)
        except OSError as exc:
            raise LiveMediaTokenError("live_media_private_key_unavailable") from exc
        if file_mode & 0o077:
            raise LiveMediaTokenError("live_media_private_key_permissions_invalid")
        try:
            key = serialization.load_pem_private_key(path.read_bytes(), password=None)
        except (OSError, ValueError, TypeError) as exc:
            raise LiveMediaTokenError("live_media_private_key_invalid") from exc
        if not isinstance(key, RSAPrivateKey) or key.key_size < 2048:
            raise LiveMediaTokenError("live_media_private_key_must_be_rsa_2048")
        return key

    def issue_session_tokens(
        self,
        descriptor: LiveMediaSessionDescriptor,
    ) -> LiveMediaSessionTokens:
        return LiveMediaSessionTokens(
            publish=self._issue(descriptor, role="publisher", action="publish"),
            preview=self._issue(descriptor, role="preview", action="read"),
        )

    def issue_receiver_token(self, descriptor: LiveMediaSessionDescriptor) -> str:
        return self._issue(descriptor, role="receiver", action="read")

    def _issue(
        self,
        descriptor: LiveMediaSessionDescriptor,
        *,
        role: MediaAccessRole,
        action: Literal["publish", "read"],
    ) -> str:
        now_epoch = int(self._now())
        expires_epoch = int(descriptor.expires_at_epoch)
        if expires_epoch <= now_epoch:
            raise LiveMediaTokenError("live_media_session_expired")
        claims = {
            "iss": self._config.jwt_issuer,
            "aud": self._config.jwt_audience,
            "sub": (
                f"{descriptor.workspace_id}:{descriptor.device_session_id}:"
                f"{descriptor.media_session_id}"
            ),
            "iat": now_epoch,
            "nbf": now_epoch - 5,
            "exp": expires_epoch,
            "jti": secrets.token_urlsafe(18),
            "media_session_id": descriptor.media_session_id,
            "media_access_role": role,
            "mediamtx_permissions": [
                {"action": action, "path": descriptor.stream_path}
            ],
        }
        try:
            return jwt.encode(
                claims,
                self._signing_key_pem,
                algorithm="RS256",
                headers={"kid": self._config.jwt_key_id, "typ": "JWT"},
            )
        except JWSError as exc:
            raise LiveMediaTokenError("live_media_token_signing_failed") from exc

    def public_jwks(self) -> dict[str, list[dict[str, str]]]:
        public_numbers = self._private_key.public_key().public_numbers()
        return {
            "keys": [
                {
                    "kty": "RSA",
                    "use": "sig",
                    "alg": "RS256",
                    "kid": self._config.jwt_key_id,
                    "n": _base64url_uint(public_numbers.n),
                    "e": _base64url_uint(public_numbers.e),
                }
            ]
        }

    def public_jwks_json(self) -> str:
        return json.dumps(self.public_jwks(), sort_keys=True, separators=(",", ":"))


__all__ = ["LiveMediaTokenError", "LiveMediaTokenService", "MediaAccessRole"]
