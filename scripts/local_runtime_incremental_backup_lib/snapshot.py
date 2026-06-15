#!/usr/bin/env python3
"""Snapshot, pruning, and WAL manifest helpers."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import MODE, TRANSIENT_RSYNC_CODES, WAL_SEGMENT_RE
from .filesystem import (
    base_backup_start_segment,
    base_root,
    dir_size_bytes,
    list_wal_segments,
    read_json,
    rsync_snapshot_base_cmd,
    run_capture,
)


def rsync_snapshot_command(source: Path, target: Path, previous: Path | None) -> list[str]:
    base_cmd = rsync_snapshot_base_cmd()
    if previous and previous.is_dir():
        base_cmd.append(f"--link-dest={previous}")
    base_cmd.extend([f"{source}/", f"{target}/"])
    return base_cmd


def run_rsync_snapshot_attempts(
    cmd: list[str],
    *,
    target: Path,
    timeout_seconds: int,
) -> tuple[bool, list[dict[str, Any]]]:
    results: list[dict[str, Any]] = []
    attempts = 0
    while attempts < 3:
        attempts += 1
        result = run_capture(cmd, timeout=timeout_seconds)
        results.append(
            {
                "command": cmd,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "attempt": attempts,
            }
        )
        if result.returncode == 0:
            return True, results
        if result.returncode not in TRANSIENT_RSYNC_CODES:
            return False, results
        shutil.rmtree(target, ignore_errors=True)
        target.parent.mkdir(parents=True, exist_ok=True)
    return False, results


def rsync_snapshot(source: Path, target: Path, previous: Path | None, timeout_seconds: int) -> list[dict[str, Any]]:
    base_cmd = rsync_snapshot_command(source, target, previous)
    success, results = run_rsync_snapshot_attempts(base_cmd, target=target, timeout_seconds=timeout_seconds)
    if success:
        return results

    last = results[-1] if results else {}
    if previous is not None:
        shutil.rmtree(target, ignore_errors=True)
        fallback_cmd = rsync_snapshot_command(source, target, None)
        fallback_success, fallback_results = run_rsync_snapshot_attempts(
            fallback_cmd,
            target=target,
            timeout_seconds=timeout_seconds,
        )
        results.extend(fallback_results)
        if fallback_success:
            results.append(
                {
                    "command": fallback_cmd,
                    "returncode": 0,
                    "stdout": "",
                    "stderr": "",
                    "attempt": 0,
                    "warning": "link_dest_failed_fell_back_to_full_snapshot",
                    "failed_link_dest": str(previous),
                }
            )
            return results
        last = results[-1] if results else last

    raise SystemExit(f"rsync did not converge after retries: {last.get('stderr')}")


def manifest_created_at(manifest: dict[str, Any]) -> float:
    created_at = str(manifest.get("created_at") or "")
    try:
        return datetime.fromisoformat(created_at.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def incremental_manifests(root: Path) -> list[tuple[Path, dict[str, Any]]]:
    manifests: list[tuple[Path, dict[str, Any]]] = []
    if not root.is_dir():
        return manifests
    for path in root.glob("*/manifest.json"):
        manifest = read_json(path)
        if manifest and manifest.get("mode") == MODE:
            manifests.append((path.parent, manifest))
    manifests.sort(key=lambda item: manifest_created_at(item[1]), reverse=True)
    return manifests


def prune_incremental(
    primary_root: Path,
    keep_count: int,
    protected: Path,
    *,
    wal_root: Path | None = None,
) -> dict[str, Any]:
    candidates = incremental_manifests(primary_root)
    retained = candidates[:keep_count]
    removed: list[str] = []
    for backup_dir, _manifest in candidates[keep_count:]:
        if backup_dir.resolve() == protected.resolve():
            continue
        shutil.rmtree(backup_dir)
        removed.append(str(backup_dir))

    protected_base_ids = {
        str(manifest.get("components", {}).get("postgres", {}).get("base_backup_id") or "")
        for _backup_dir, manifest in retained
    }
    protected_base_ids.discard("")
    removed_bases: list[str] = []
    root = base_root(primary_root, wal_root)
    protected_start_segments: list[str] = []
    if root.is_dir():
        for base_dir in root.iterdir():
            if not base_dir.is_dir():
                continue
            if base_dir.name in protected_base_ids:
                start_segment = base_backup_start_segment(base_dir)
                if start_segment:
                    protected_start_segments.append(start_segment)
                continue
            else:
                shutil.rmtree(base_dir)
                removed_bases.append(str(base_dir))

    removed_wal_segments: list[str] = []
    warnings: list[str] = []
    if protected_start_segments and wal_root and wal_root.is_dir():
        earliest_required_segment = min(protected_start_segments)
        for wal_path in wal_root.iterdir():
            if not wal_path.is_file() or not WAL_SEGMENT_RE.fullmatch(wal_path.name):
                continue
            if wal_path.name < earliest_required_segment:
                wal_path.unlink()
                removed_wal_segments.append(str(wal_path))
    else:
        warnings.append("wal_prune_skipped_no_protected_base_start_segment")

    return {
        "snapshots": removed,
        "base_backups": removed_bases,
        "wal_segments": removed_wal_segments,
        "warnings": warnings,
    }


def wal_manifest_entry_required(segment: str, required_start: str) -> bool:
    if not required_start:
        return True
    name = str(segment)
    if len(name) < 24 or any(ch not in "0123456789ABCDEF" for ch in name[:24]):
        return True
    return name[:24] >= required_start


def refresh_manifest_wal_state(manifest: dict[str, Any], wal_root: Path) -> None:
    postgres = manifest.setdefault("components", {}).setdefault("postgres", {})
    wal_segments = list_wal_segments(wal_root)
    postgres["wal_segments"] = wal_segments
    postgres["wal_segment_count"] = len(wal_segments)
    postgres["wal_archive_bytes"] = dir_size_bytes(wal_root)
    if wal_segments:
        postgres["wal_start_segment"] = wal_segments[0]
        postgres["wal_end_segment"] = wal_segments[-1]
    else:
        postgres["wal_start_segment"] = ""
        postgres["wal_end_segment"] = ""
