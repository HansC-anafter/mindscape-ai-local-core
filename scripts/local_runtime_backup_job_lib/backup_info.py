#!/usr/bin/env python3
"""Backup manifest summary helpers."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .common import resolve_backup_root


def profile_state_summary(backup_dir: Path) -> dict[str, Any] | None:
    report_path = backup_dir / "metadata" / "profile-state-report.json"
    if not report_path.is_file():
        return None
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"valid": False, "error": f"{type(exc).__name__}: {exc}"}

    profiles = report.get("profiles") or []
    invalid = [item for item in profiles if item and not item.get("valid")]
    return {
        "valid": not invalid,
        "profiles": len(profiles),
        "invalid_profiles": len(invalid),
        "invalid": invalid,
    }


def parse_backup_manifest(manifest_path: Path) -> dict[str, Any] | None:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    backup_dir = manifest_path.parent
    artifacts = manifest.get("artifacts") or []
    components = manifest.get("components") or {}
    total_bytes = (
        sum(int(item.get("bytes") or 0) for item in artifacts if isinstance(item, dict))
        if artifacts
        else int(manifest.get("total_bytes") or 0)
    )
    backup_name = str(manifest.get("backup_name") or backup_dir.name)
    return {
        "backup_name": backup_name,
        "created_at": manifest.get("created_at"),
        "path": str(backup_dir),
        "host_backup_dir": str(backup_dir),
        "schema_version": manifest.get("schema_version"),
        "mode": manifest.get("mode") or "db_dump_only",
        "git_commit": manifest.get("git_commit"),
        "options": manifest.get("options") or {},
        "artifact_count": len(artifacts) if artifacts else len(components),
        "total_bytes": total_bytes,
        "base_backup_id": (components.get("postgres") or {}).get("base_backup_id"),
        "file_snapshot_id": backup_name if components.get("files") else "",
        "profile_state": profile_state_summary(backup_dir),
        "manifest_mtime": manifest_path.stat().st_mtime,
    }


def latest_backup(backup_root: Path) -> dict[str, Any] | None:
    if not backup_root.is_dir():
        return None
    backups: list[dict[str, Any]] = []
    for manifest_path in backup_root.glob("*/manifest.json"):
        parsed = parse_backup_manifest(manifest_path)
        if parsed:
            backups.append(parsed)
    if not backups:
        return None

    def sort_key(item: dict[str, Any]) -> Any:
        created_at = item.get("created_at")
        if isinstance(created_at, str):
            try:
                return datetime.fromisoformat(created_at.replace("Z", "+00:00")).timestamp()
            except ValueError:
                pass
        return item.get("manifest_mtime") or 0

    latest = max(backups, key=sort_key)
    latest.pop("manifest_mtime", None)
    return latest


def command_latest_backup(args: argparse.Namespace) -> dict[str, Any]:
    backup_root = resolve_backup_root(args.output_dir)
    return {
        "backup_root": str(backup_root),
        "latest_backup": latest_backup(backup_root),
    }
