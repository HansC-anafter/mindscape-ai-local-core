"""Types for pack activation lifecycle state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class PackActivationRecord:
    pack_id: str
    pack_family: str
    enabled: bool
    install_state: str
    migration_state: str
    activation_state: str
    activation_mode: str
    embedding_state: str
    embedding_error: Optional[str]
    embeddings_updated_at: Optional[datetime]
    manifest_hash: Optional[str]
    registered_prefixes: List[str]
    last_error: Optional[str]
    activated_at: Optional[datetime]

    def to_store_payload(self) -> Dict[str, Any]:
        return {
            "pack_id": self.pack_id,
            "pack_family": self.pack_family,
            "enabled": self.enabled,
            "install_state": self.install_state,
            "migration_state": self.migration_state,
            "activation_state": self.activation_state,
            "activation_mode": self.activation_mode,
            "embedding_state": self.embedding_state,
            "embedding_error": self.embedding_error,
            "embeddings_updated_at": self.embeddings_updated_at,
            "manifest_hash": self.manifest_hash,
            "registered_prefixes": self.registered_prefixes,
            "last_error": self.last_error,
            "activated_at": self.activated_at,
        }

    def to_receipt_payload(self) -> Dict[str, Any]:
        """Return the JSON-safe activation projection used by install receipts."""

        payload = self.to_store_payload()
        for field_name in ("embeddings_updated_at", "activated_at"):
            value = payload.get(field_name)
            if isinstance(value, datetime):
                payload[field_name] = value.isoformat()
        return payload
