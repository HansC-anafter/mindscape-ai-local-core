"""Append-only calibration evidence output."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def evidence_row(payload: dict[str, Any]) -> dict[str, Any]:
    row = dict(payload)
    row["evidence_sha256"] = hashlib.sha256(
        canonical_json(payload).encode("utf-8")
    ).hexdigest()
    return row


class JsonlEvidenceWriter:
    """Create one immutable JSONL file and flush every evidence row."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._stream = path.open("x", encoding="utf-8")

    def append(self, payload: dict[str, Any]) -> dict[str, Any]:
        row = evidence_row(payload)
        self._stream.write(canonical_json(row) + "\n")
        self._stream.flush()
        return row

    def close(self) -> None:
        self._stream.close()


def write_immutable_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write("\n")
