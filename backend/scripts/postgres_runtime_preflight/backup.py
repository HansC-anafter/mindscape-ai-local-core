"""Backup verification helpers for PostgreSQL runtime preflight."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


def _parse_int(value: Any, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_backup(
    backup_dir: Path | None,
    *,
    verification_mode: str = "manifest_checksum",
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "source": str(backup_dir) if backup_dir else None,
        "source_available": False,
        "verified": False,
        "verification_mode": verification_mode,
        "errors": [],
        "warnings": [],
    }
    if backup_dir is None:
        result["errors"].append("verified_backup_dir_required")
        return result

    backup_root = backup_dir.expanduser()
    result["source"] = str(backup_root)
    manifest_path = backup_root / "manifest.json"
    result["manifest_path"] = str(manifest_path)
    if not backup_root.is_dir():
        result["errors"].append("backup_dir_not_found")
        return result
    if not manifest_path.is_file():
        result["source_available"] = True
        result["errors"].append("manifest_missing")
        return result

    result["source_available"] = True
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        result["errors"].append(f"manifest_invalid_json: {exc}")
        return result

    if not isinstance(manifest, dict):
        result["errors"].append("manifest_not_object")
        return result

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        result["errors"].append("manifest_artifacts_empty")
        artifacts = []

    checked_artifacts: list[dict[str, Any]] = []
    for artifact in artifacts:
        if not isinstance(artifact, Mapping):
            result["errors"].append("artifact_not_object")
            continue
        rel_path = str(artifact.get("path") or "").strip()
        expected_sha = str(artifact.get("sha256") or "").strip()
        expected_size = _parse_int(artifact.get("bytes"), -1)
        if not rel_path:
            result["errors"].append("artifact_path_missing")
            continue
        artifact_path = backup_root / rel_path
        try:
            artifact_path.resolve().relative_to(backup_root.resolve())
        except Exception:
            result["errors"].append(f"artifact_path_outside_backup:{rel_path}")
            continue
        if not artifact_path.is_file():
            result["errors"].append(f"artifact_missing:{rel_path}")
            continue
        actual_size = artifact_path.stat().st_size
        if actual_size <= 0:
            result["errors"].append(f"artifact_empty:{rel_path}")
        if expected_size != actual_size:
            result["errors"].append(f"artifact_size_mismatch:{rel_path}")
        actual_sha = expected_sha
        sha256_checked = False
        if verification_mode == "manifest_checksum":
            actual_sha = _file_sha256(artifact_path)
            sha256_checked = True
            if not expected_sha or expected_sha != actual_sha:
                result["errors"].append(f"artifact_sha256_mismatch:{rel_path}")
        elif verification_mode == "manifest_size":
            if not expected_sha:
                result["errors"].append(f"artifact_sha256_missing:{rel_path}")
            result["warnings"].append(f"artifact_sha256_not_recomputed:{rel_path}")
        else:
            result["errors"].append(f"unsupported_verification_mode:{verification_mode}")
            continue
        checked_artifacts.append(
            {
                "path": rel_path,
                "bytes": actual_size,
                "sha256": actual_sha,
                "sha256_checked": sha256_checked,
            }
        )

    options = manifest.get("options") if isinstance(manifest.get("options"), dict) else {}
    result.update(
        {
            "schema_version": manifest.get("schema_version"),
            "backup_name": manifest.get("backup_name"),
            "created_at": manifest.get("created_at"),
            "git_commit": manifest.get("git_commit"),
            "options": options,
            "artifact_count": len(checked_artifacts),
            "artifacts": checked_artifacts,
        }
    )
    result["verified"] = not result["errors"]
    return result
