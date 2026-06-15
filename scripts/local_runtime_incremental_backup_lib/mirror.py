#!/usr/bin/env python3
"""Mirror replication helpers for incremental backups."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import utc_now
from .filesystem import add_mirror_scope_filters, latest_pointer, run_capture, state_root, write_json
from .snapshot import prune_incremental
from .verify import clone_json, verify_incremental_dir


def mirror_manifest_for_root(manifest: dict[str, Any], mirror_backup_dir: Path, mirror_wal_root: Path) -> dict[str, Any]:
    mirrored = clone_json(manifest)
    mirrored["backup_dir"] = str(mirror_backup_dir)
    postgres = mirrored.setdefault("components", {}).setdefault("postgres", {})
    base_id = str(postgres.get("base_backup_id") or "")
    if base_id:
        postgres["base_backup_dir"] = str(mirror_wal_root / "base_backups" / base_id)
    postgres["wal_archive_dir"] = str(mirror_wal_root)
    mirrored.setdefault("mirror", {})["scope_mode"] = "selected_data_scopes"
    return mirrored


def mirror_incremental_artifacts(
    *,
    primary_root: Path,
    mirror_root: Path,
    backup_dir: Path,
    wal_root: Path,
    manifest: dict[str, Any],
    timeout_seconds: int,
    retention_count: int,
    mirror_scopes: list[str],
) -> dict[str, Any]:
    wal_relpath = wal_root.resolve().relative_to(primary_root.resolve())
    mirror_backup_dir = mirror_root / backup_dir.name
    mirror_wal_root = mirror_root / wal_relpath
    mirror_state_root = mirror_root / ".incremental"
    mirror_root.mkdir(parents=True, exist_ok=True)
    mirror_backup_dir.mkdir(parents=True, exist_ok=True)
    mirror_wal_root.mkdir(parents=True, exist_ok=True)

    backup_cmd = ["rsync", "-a", "--delete", "--delete-excluded"]
    previous_snapshot_id = str(
        manifest.get("components", {}).get("files", {}).get("previous_snapshot_id") or ""
    )
    previous_mirror_snapshot = (
        mirror_root / previous_snapshot_id / "app-data" if previous_snapshot_id else None
    )
    if previous_mirror_snapshot and previous_mirror_snapshot.is_dir():
        backup_cmd.append(f"--link-dest={previous_mirror_snapshot}")
    add_mirror_scope_filters(backup_cmd, mirror_scopes)
    backup_cmd.extend([f"{backup_dir / 'app-data'}/", f"{mirror_backup_dir / 'app-data'}/"])

    commands = [
        backup_cmd,
        ["rsync", "-a", "--delete", f"{wal_root}/", f"{mirror_wal_root}/"],
        ["rsync", "-a", "--delete", f"{state_root(primary_root)}/", f"{mirror_state_root}/"],
    ]
    results = []
    for cmd in commands:
        result = run_capture(cmd, timeout=timeout_seconds)
        results.append(
            {
                "command": cmd,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        )
        if result.returncode != 0:
            raise SystemExit(f"Mirror rsync failed with exit code {result.returncode}: {result.stderr}")

    mirrored_manifest = mirror_manifest_for_root(manifest, mirror_backup_dir, mirror_wal_root)
    mirrored_manifest.setdefault("mirror", {})["scopes"] = mirror_scopes
    mirrored_manifest.setdefault("components", {}).setdefault("files", {})["mirror_scopes"] = mirror_scopes
    write_json(mirror_backup_dir / "manifest.json", mirrored_manifest)
    write_json(
        latest_pointer(mirror_root),
        {
            "latest_backup_name": backup_dir.name,
            "latest_backup_dir": str(mirror_backup_dir),
            "updated_at": utc_now(),
        },
    )
    mirror_verify = verify_incremental_dir(mirror_backup_dir)
    mirror_pruned = prune_incremental(
        mirror_root,
        keep_count=retention_count,
        protected=mirror_backup_dir,
        wal_root=mirror_wal_root,
    )
    return {
        "enabled": True,
        "mirror_dir": str(mirror_backup_dir),
        "wal_archive_dir": str(mirror_wal_root),
        "scopes": mirror_scopes,
        "commands": results,
        "verify": mirror_verify,
        "pruned": mirror_pruned,
    }
