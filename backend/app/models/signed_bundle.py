"""
Signed Handoff Bundle - portable, verifiable handoff packages.

Enables channel-independent transport of handoff contracts between
Mindscape AI instances. Each bundle includes HMAC-SHA256 signature
and SHA-256 content hash for integrity verification.
"""

import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


class SignedHandoffBundle(BaseModel):
    """Self-contained, portable handoff package with integrity verification.

    Bundles can be transported via any channel (email, Slack, API, file)
    and verified at the receiving end using the shared secret.
    """

    version: str = Field(default="0.1", description="Bundle schema version")
    payload_type: str = Field(
        ...,
        description="Payload type: handoff_in, commitment, or result",
    )
    payload: Dict[str, Any] = Field(
        ..., description="Serialized HandoffIn / Commitment / Result"
    )
    source_device_id: str = Field(..., description="Originating device identifier")
    target_device_id: Optional[str] = Field(
        None, description="Intended recipient device"
    )
    created_at: datetime = Field(
        default_factory=_utc_now, description="Bundle creation timestamp"
    )
    content_hash: str = Field(
        ..., description="SHA-256 hex digest of canonical payload JSON"
    )
    signature: str = Field(
        ..., description="HMAC-SHA256 hex digest over canonical payload JSON"
    )

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}

    @staticmethod
    def _canonical_json(payload: Dict[str, Any]) -> bytes:
        """Produce deterministic JSON bytes for hashing."""
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()

    @classmethod
    def create(
        cls,
        payload_type: str,
        payload: Dict[str, Any],
        source_device_id: str,
        secret_key: str,
        target_device_id: Optional[str] = None,
    ) -> "SignedHandoffBundle":
        """Create a signed bundle from a payload.

        Args:
            payload_type: One of handoff_in, commitment, result.
            payload: JSON-serializable payload dict.
            source_device_id: Device creating the bundle.
            secret_key: Shared secret for HMAC signing.
            target_device_id: Optional intended recipient.

        Returns:
            SignedHandoffBundle with computed hash and signature.
        """
        canonical = cls._canonical_json(payload)
        content_hash = hashlib.sha256(canonical).hexdigest()
        signature = hmac.new(secret_key.encode(), canonical, hashlib.sha256).hexdigest()

        return cls(
            payload_type=payload_type,
            payload=payload,
            source_device_id=source_device_id,
            target_device_id=target_device_id,
            content_hash=content_hash,
            signature=signature,
        )

    def verify(self, secret_key: str) -> bool:
        """Verify bundle integrity and authenticity.

        Args:
            secret_key: Shared secret used during creation.

        Returns:
            True if both content hash and signature are valid.
        """
        canonical = self._canonical_json(self.payload)
        expected_hash = hashlib.sha256(canonical).hexdigest()
        if expected_hash != self.content_hash:
            return False

        expected_sig = hmac.new(
            secret_key.encode(), canonical, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected_sig, self.signature)
