"""Archive identity and checksum-not-signature evidence for install jobs."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict


INTEGRITY_SCHEMA = "mindscape.capability_install_integrity.v1"
TRUST_MODE = "checksum_verified_not_signed"


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_file_upload_archive(job: Dict[str, Any]) -> Dict[str, Any]:
    if job.get("source_kind") != "file_upload":
        return {"status": "not_applicable"}
    source = dict(job.get("source_payload") or {})
    expected = str(source.get("archive_sha256") or "").strip().lower()
    if not expected:
        return {"status": "legacy_job_without_archive_sha256"}
    path = Path(str(source.get("mindpack_path") or ""))
    if not path.is_file():
        raise ValueError("install_archive_missing_before_execution")
    actual = sha256_file(path)
    if actual != expected:
        raise ValueError("install_archive_sha256_mismatch")
    return {"status": "verified", "archive_sha256": actual}


def attach_install_integrity_evidence(
    *,
    job: Dict[str, Any],
    result_payload: Dict[str, Any],
) -> Dict[str, Any]:
    if job.get("source_kind") != "file_upload":
        return result_payload
    source = dict(job.get("source_payload") or {})
    activation = dict(result_payload.get("activation") or {})
    archive_sha256 = str(source.get("archive_sha256") or "").strip().lower()
    source_commit = str(source.get("source_commit") or "").strip()
    manifest_hash = str(activation.get("manifest_hash") or "").strip()
    evidence = {
        "schema_version": INTEGRITY_SCHEMA,
        "trust_mode": TRUST_MODE,
        "archive_sha256": archive_sha256,
        "archive_verified_before_execution": bool(archive_sha256),
        "manifest_hash": manifest_hash,
        "source_commit": source_commit,
        "signature_status": "not_available",
        "integrity_status": (
            "verified"
            if archive_sha256 and manifest_hash and source_commit
            else "incomplete_evidence"
        ),
    }
    return {**result_payload, "install_integrity": evidence}


__all__ = [
    "INTEGRITY_SCHEMA",
    "TRUST_MODE",
    "attach_install_integrity_evidence",
    "sha256_bytes",
    "sha256_file",
    "verify_file_upload_archive",
]
