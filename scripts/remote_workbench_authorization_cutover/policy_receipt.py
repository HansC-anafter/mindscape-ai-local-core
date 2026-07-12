"""Concurrency-safe runtime policy transition ownership receipts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .io import CutoverError, assert_private_file, write_private_json


RECEIPT_NAME = "runtime-policy-transition-receipt.json"
PROJECTION_KEYS = (
    "access_issuer",
    "access_audience",
    "remote_access_state",
    "local_core_super_admins",
)


def _projection(value: Mapping[str, Any], revision: int) -> dict[str, Any]:
    return {
        "revision": revision,
        **{key: value.get(key) for key in PROJECTION_KEYS},
    }


def record_policy_intent(
    directory: Path,
    *,
    original: Mapping[str, Any],
    body: Mapping[str, Any],
) -> None:
    """Append one expected→next full projection before attempting the exact PUT."""

    expected_revision = body.get("expected_revision")
    original_revision = original.get("revision")
    if type(expected_revision) is not int or type(original_revision) is not int:
        raise CutoverError("Policy transition receipt revision is invalid")
    path = directory / RECEIPT_NAME
    if path.exists():
        assert_private_file(path, max_bytes=32_768)
        try:
            receipt = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise CutoverError("Policy transition receipt is malformed") from error
    else:
        receipt = {
            "schema_version": 1,
            "original": _projection(original, original_revision),
            "intended": [],
        }
    if (
        not isinstance(receipt, dict)
        or receipt.get("schema_version") != 1
        or not isinstance(receipt.get("intended"), list)
        or receipt.get("original") != _projection(original, original_revision)
    ):
        raise CutoverError("Policy transition receipt identity changed")
    receipt["intended"].append(
        {
            "expected_revision": expected_revision,
            "next": _projection(body, expected_revision + 1),
        }
    )
    write_private_json(path, receipt)


def current_policy_requires_rollback(
    directory: Path,
    *,
    original: Mapping[str, Any],
    current: Mapping[str, Any],
) -> bool:
    """Allow only original no-op or a projection owned by this exact runner."""

    path = directory / RECEIPT_NAME
    assert_private_file(path, max_bytes=32_768)
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise CutoverError("Policy transition receipt is malformed") from error
    original_revision = original.get("revision")
    current_revision = current.get("revision")
    if type(original_revision) is not int or type(current_revision) is not int:
        raise CutoverError("Policy rollback revision evidence is invalid")
    original_projection = _projection(original, original_revision)
    current_projection = _projection(current, current_revision)
    if not isinstance(receipt, dict) or receipt.get("original") != original_projection:
        raise CutoverError("Policy rollback original receipt does not match")
    if current_projection == original_projection:
        return False
    intended = receipt.get("intended")
    owned = {
        json.dumps(item.get("next"), sort_keys=True, separators=(",", ":"))
        for item in intended or []
        if isinstance(item, dict) and isinstance(item.get("next"), dict)
    }
    encoded = json.dumps(current_projection, sort_keys=True, separators=(",", ":"))
    if encoded not in owned:
        raise CutoverError("Concurrent runtime policy divergence blocks rollback")
    return True
