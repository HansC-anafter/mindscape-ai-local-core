"""Canonical JSON and bounded hashing for durable workflow records."""

from __future__ import annotations

import hashlib
import json
from typing import Any

MAX_INLINE_BYTES = 16_384


class CanonicalPayloadError(ValueError):
    """Raised when a value cannot enter the durable canonical boundary."""


def encode(value: Any, *, max_bytes: int = MAX_INLINE_BYTES) -> bytes:
    try:
        rendered = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CanonicalPayloadError("payload is not canonical JSON") from exc
    if len(rendered) > max_bytes:
        raise CanonicalPayloadError(
            f"canonical payload is {len(rendered)} bytes; maximum is {max_bytes}"
        )
    return rendered


def sha256_hex(value: Any, *, max_bytes: int = MAX_INLINE_BYTES) -> str:
    return hashlib.sha256(encode(value, max_bytes=max_bytes)).hexdigest()


def chained_hash(previous_event_hash: str | None, event_core: dict[str, Any]) -> str:
    previous = bytes.fromhex(previous_event_hash) if previous_event_hash else b""
    return hashlib.sha256(previous + encode(event_core)).hexdigest()
