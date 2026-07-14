#!/usr/bin/env python3
"""Incremental backup manifest verification helpers."""

from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Any

from .config import MODE, RSYNC_SNAPSHOT_EXCLUDES
from .filesystem import read_json, run_capture
from .snapshot import wal_manifest_entry_required


def verify_incremental_dir(backup_dir: Path, *, restore_drill: bool = False) -> dict[str, Any]:
    manifest_path = backup_dir / "manifest.json"
    manifest = read_json(manifest_path)
    if not manifest:
        raise SystemExit(f"Invalid or missing manifest: {manifest_path}")
    if manifest.get("mode") != MODE:
        raise SystemExit(f"Backup manifest mode is not {MODE}: {backup_dir}")

    components = manifest.get("components") or {}
    files = components.get("files") or {}
    postgres = components.get("postgres") or {}
    snapshot_dir = backup_dir / str(files.get("snapshot_relpath") or "app-data")
    if not snapshot_dir.is_dir():
        raise SystemExit(f"File snapshot directory not found: {snapshot_dir}")
    for excluded in RSYNC_SNAPSHOT_EXCLUDES:
        if (snapshot_dir / excluded).exists():
            raise SystemExit(f"Excluded directory found in snapshot: {excluded}")

    base_dir = Path(str(postgres.get("base_backup_dir") or ""))
    if not base_dir.is_dir():
        raise SystemExit(f"Base backup directory not found: {base_dir}")
    if not (base_dir / "PG_VERSION").is_file():
        raise SystemExit(f"Base backup PG_VERSION not found: {base_dir}")

    wal_root = Path(str(postgres.get("wal_archive_dir") or ""))
    if not wal_root.is_dir():
        raise SystemExit(f"WAL archive directory not found: {wal_root}")
    required_start = str(postgres.get("base_backup_start_wal_segment") or "")
    missing = []
    for segment in postgres.get("wal_segments") or []:
        if not wal_manifest_entry_required(str(segment), required_start):
            continue
        if not (wal_root / str(segment)).is_file():
            missing.append(str(segment))
    if missing:
        raise SystemExit("Missing WAL segments: " + ", ".join(missing))

    restore = {"requested": restore_drill, "status": "not_requested"}
    if restore_drill:
        container_base_dir = str(postgres.get("container_base_dir") or "")
        if not container_base_dir:
            raise SystemExit("Restore drill requires postgres.container_base_dir in manifest")
        quoted_base_dir = shlex.quote(container_base_dir)
        command = (
            "if command -v pg_controldata >/dev/null 2>&1; then "
            f"pg_controldata {quoted_base_dir}; "
            "else "
            f"/usr/lib/postgresql/${{PG_MAJOR:-16}}/bin/pg_controldata {quoted_base_dir}; "
            "fi"
        )
        result = run_capture(
            ["docker", "exec", "mindscape-ai-local-core-postgres", "sh", "-lc", command],
            timeout=120,
        )
        if result.returncode != 0:
            raise SystemExit(f"pg_controldata restore drill failed: {result.stderr}")
        restore = {
            "requested": True,
            "status": "controlfile_pass",
            "reason": "base backup control file and WAL dependencies are present",
            "stdout": result.stdout,
            "stderr": result.stderr,
        }

    return {
        "success": True,
        "backup_dir": str(backup_dir),
        "mode": MODE,
        "scope_mode": str(files.get("scope_mode") or "runtime_snapshot"),
        "restore_drill": restore,
    }


def clone_json(data: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(data))
