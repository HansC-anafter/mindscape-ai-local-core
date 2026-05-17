"""Signed opaque cursor helpers for keyset pagination."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any


class CursorError(ValueError):
    """Raised when a read-model cursor cannot be trusted or used."""


@dataclass(frozen=True)
class CursorEnvelope:
    v: int
    read_model_id: str
    contract_version: int
    sort_id: str
    filter_hash: str
    issued_at: int
    expires_at: int
    last_values: dict[str, Any]
    signature: str


def _json_dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def filter_hash(filters: dict[str, Any]) -> str:
    encoded = _json_dumps(filters)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _sign(payload: dict[str, Any], secret: str) -> str:
    body = _json_dumps(payload).encode("utf-8")
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def _pack(payload: dict[str, Any]) -> str:
    encoded = _json_dumps(payload).encode("utf-8")
    return base64.urlsafe_b64encode(encoded).decode("ascii").rstrip("=")


def _unpack(token: str) -> dict[str, Any]:
    padding = "=" * (-len(token) % 4)
    try:
        decoded = base64.urlsafe_b64decode(f"{token}{padding}".encode("ascii"))
        payload = json.loads(decoded.decode("utf-8"))
    except Exception as exc:
        raise CursorError("cursor_decode_failed") from exc
    if not isinstance(payload, dict):
        raise CursorError("cursor_payload_invalid")
    return payload


def encode_cursor(
    *,
    read_model_id: str,
    contract_version: int,
    sort_id: str,
    filters: dict[str, Any],
    last_values: dict[str, Any],
    ttl_seconds: int,
    secret: str,
    now: int | None = None,
) -> str:
    issued_at = int(now if now is not None else time.time())
    payload = {
        "v": 1,
        "read_model_id": read_model_id,
        "contract_version": int(contract_version),
        "sort_id": sort_id,
        "filter_hash": filter_hash(filters),
        "issued_at": issued_at,
        "expires_at": issued_at + int(ttl_seconds),
        "last_values": last_values,
    }
    payload["signature"] = _sign(payload, secret)
    return _pack(payload)


def decode_cursor(
    token: str,
    *,
    read_model_id: str,
    contract_version: int,
    sort_id: str,
    filters: dict[str, Any],
    secret: str,
    now: int | None = None,
) -> CursorEnvelope:
    payload = _unpack(token)
    signature = payload.get("signature")
    unsigned = {key: value for key, value in payload.items() if key != "signature"}
    if not isinstance(signature, str) or not hmac.compare_digest(
        signature,
        _sign(unsigned, secret),
    ):
        raise CursorError("cursor_signature_invalid")
    if payload.get("v") != 1:
        raise CursorError("cursor_version_invalid")
    if payload.get("read_model_id") != read_model_id:
        raise CursorError("cursor_read_model_mismatch")
    if payload.get("contract_version") != contract_version:
        raise CursorError("cursor_contract_version_mismatch")
    if payload.get("sort_id") != sort_id:
        raise CursorError("cursor_sort_mismatch")
    if payload.get("filter_hash") != filter_hash(filters):
        raise CursorError("cursor_filter_mismatch")
    current_time = int(now if now is not None else time.time())
    if type(payload.get("expires_at")) is not int or payload["expires_at"] < current_time:
        raise CursorError("cursor_expired")
    last_values = payload.get("last_values")
    if not isinstance(last_values, dict):
        raise CursorError("cursor_last_values_invalid")
    return CursorEnvelope(
        v=payload["v"],
        read_model_id=payload["read_model_id"],
        contract_version=payload["contract_version"],
        sort_id=payload["sort_id"],
        filter_hash=payload["filter_hash"],
        issued_at=payload["issued_at"],
        expires_at=payload["expires_at"],
        last_values=last_values,
        signature=signature,
    )
