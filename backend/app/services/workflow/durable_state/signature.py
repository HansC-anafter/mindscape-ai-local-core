"""Local Ed25519 signing with one fail-closed mounted-file provider."""

from __future__ import annotations

import base64
import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

SIGNING_KEY_FILE_ENV = "MINDSCAPE_WORKFLOW_SIGNING_KEY_FILE"


class SigningKeyError(RuntimeError):
    """Raised when the exact local signing-key contract is unavailable."""


@dataclass(frozen=True)
class Signature:
    key_id: str
    value: str


class Ed25519Signer:
    """Signer backed by a raw 32-byte Ed25519 private key."""

    def __init__(self, private_key: Ed25519PrivateKey) -> None:
        self._private_key = private_key
        public = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        self.key_id = f"ed25519:{hashlib.sha256(public).hexdigest()}"

    @classmethod
    def from_mounted_file(cls) -> "Ed25519Signer":
        raw_path = os.environ.get(SIGNING_KEY_FILE_ENV)
        if not raw_path:
            raise SigningKeyError(f"{SIGNING_KEY_FILE_ENV} is required")
        path = Path(raw_path)
        try:
            mode = path.stat().st_mode & 0o777
            raw_key = path.read_bytes()
        except OSError as exc:
            raise SigningKeyError("mounted signing key is unreadable") from exc
        if mode & 0o077:
            raise SigningKeyError("mounted signing key permissions must be 0600 or stricter")
        if len(raw_key) != 32:
            raise SigningKeyError("mounted signing key must contain exactly 32 raw bytes")
        return cls(Ed25519PrivateKey.from_private_bytes(raw_key))

    def sign(self, payload: bytes) -> Signature:
        encoded = base64.urlsafe_b64encode(
            self._private_key.sign(payload)
        ).rstrip(b"=").decode("ascii")
        return Signature(key_id=self.key_id, value=encoded)

    def public_key(self) -> Ed25519PublicKey:
        return self._private_key.public_key()


def verify(public_key: Ed25519PublicKey, payload: bytes, signature: str) -> None:
    padding = "=" * (-len(signature) % 4)
    try:
        decoded = base64.urlsafe_b64decode(signature + padding)
        public_key.verify(decoded, payload)
    except Exception as exc:
        raise SigningKeyError("durable workflow signature is invalid") from exc
