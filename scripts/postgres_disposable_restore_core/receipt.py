"""Atomic acceptance receipt for a disposable restore."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping


def _checksum(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def write_restore_receipt(path: Path, payload: Mapping[str, Any]) -> dict[str, Any]:
    body = dict(payload)
    body["checksum"] = _checksum(body)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(body, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    return body


def read_restore_receipt(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    checksum = str(payload.pop("checksum", ""))
    if checksum != _checksum(payload):
        raise ValueError("restore_receipt_checksum_invalid")
    payload["checksum"] = checksum
    return payload
