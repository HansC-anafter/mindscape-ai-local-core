"""Canonical consumer-impact receipt validation."""

from __future__ import annotations

from typing import Any

from .models import AttestationInputError


def validate_hash_receipt(receipt: dict[str, Any], *, label: str) -> dict[str, Any]:
    name = str(receipt.get("name") or "")
    digest = str(receipt.get("sha256") or "")
    size = receipt.get("bytes")
    if not name or len(digest) != 64 or not isinstance(size, int) or size < 0:
        raise AttestationInputError(f"{label} hash receipt is incomplete")
    return {"name": name, "sha256": digest, "bytes": size}
