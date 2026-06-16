"""Bounded readers for artifact result payloads."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Optional

from app.services.result_object_contract import json_payload_sha256

from .policy import ArtifactLifecycleCandidate


def result_json_path_for_candidate(
    candidate: ArtifactLifecycleCandidate,
) -> Optional[Path]:
    """Resolve the canonical result.json path for one DB-projected artifact."""
    if candidate.result_json_path and candidate.result_json_path.strip():
        return Path(candidate.result_json_path.strip())
    if candidate.storage_ref and candidate.storage_ref.strip():
        return Path(candidate.storage_ref.strip()) / "result.json"
    return None


def file_sha256(path: Path) -> str:
    """Return the SHA-256 digest for a bounded file path."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def checksum_matches(candidate: ArtifactLifecycleCandidate, path: Optional[Path]) -> bool:
    """Verify result payload checksum when the manifest contains one."""
    checksum = candidate.checksum_sha256
    if not isinstance(checksum, str) or not checksum.strip():
        return True
    if path is None or not path.exists() or not path.is_file():
        return False
    expected = checksum.strip().lower()
    if file_sha256(path) == expected:
        return True
    try:
        return json_payload_sha256(read_result_json(path)) == expected
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return False


def read_result_json(path: Path) -> Dict[str, Any]:
    """Read a canonical result.json payload."""
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload if isinstance(payload, dict) else {"payload": payload}
