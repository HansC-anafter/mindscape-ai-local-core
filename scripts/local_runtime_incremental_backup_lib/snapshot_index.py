#!/usr/bin/env python3
"""Discover usable incremental snapshots and PostgreSQL base backups."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import MODE
from .filesystem import base_root, latest_pointer, read_json


def latest_incremental_manifest(primary_root: Path) -> dict[str, Any] | None:
    pointer = latest_pointer(primary_root)
    if pointer.is_file():
        data = read_json(pointer)
        if data and data.get("latest_backup_dir"):
            manifest = read_json(Path(str(data["latest_backup_dir"])) / "manifest.json")
            if manifest and manifest.get("mode") == MODE:
                return manifest

    candidates: list[tuple[float, dict[str, Any]]] = []
    if primary_root.is_dir():
        for path in primary_root.glob("*/manifest.json"):
            manifest = read_json(path)
            if not manifest or manifest.get("mode") != MODE:
                continue
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            candidates.append((mtime, manifest))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def latest_runtime_snapshot(
    primary_root: Path,
) -> tuple[dict[str, Any] | None, Path | None]:
    """Return the newest usable file snapshot from its actual manifest location.

    PostgreSQL-only manifests deliberately contain an empty ``app-data``
    directory and must never become an rsync link-dest. Historical backup
    directories may be relocated without rewriting immutable manifests, so
    the recorded ``backup_dir`` is not an authoritative local path here.
    """

    candidates: list[tuple[float, dict[str, Any], Path]] = []
    if not primary_root.is_dir():
        return None, None
    for manifest_path in primary_root.glob("*/manifest.json"):
        manifest = read_json(manifest_path)
        if not manifest or manifest.get("mode") != MODE:
            continue
        files = (manifest.get("components") or {}).get("files") or {}
        if files.get("scope_mode") != "runtime_snapshot":
            continue
        snapshot_relpath = str(files.get("snapshot_relpath") or "app-data")
        snapshot_path = manifest_path.parent / snapshot_relpath
        if not snapshot_path.is_dir():
            continue
        try:
            mtime = manifest_path.stat().st_mtime
        except OSError:
            continue
        candidates.append((mtime, manifest, snapshot_path))
    if not candidates:
        return None, None
    candidates.sort(key=lambda item: item[0], reverse=True)
    _, manifest, snapshot_path = candidates[0]
    return manifest, snapshot_path


def latest_base(primary_root: Path) -> dict[str, Any] | None:
    candidates: list[tuple[str, dict[str, Any]]] = []
    root = base_root(primary_root)
    if not root.is_dir():
        return None
    for manifest_path in root.glob("*/base-manifest.json"):
        manifest = read_json(manifest_path)
        if not manifest:
            continue
        created_at = str(manifest.get("created_at") or "")
        candidates.append((created_at, manifest))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def age_hours(created_at: str | None) -> float | None:
    if not created_at:
        return None
    try:
        created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    delta = datetime.now(timezone.utc) - created
    return max(0.0, delta.total_seconds() / 3600)
