#!/usr/bin/env python3
"""Google Drive discovery and collaboration folder preparation."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

from .common import utc_now
from .state import write_json


GOOGLE_DRIVE_MY_DRIVE_NAMES = ("我的雲端硬碟", "My Drive")
GOOGLE_DRIVE_RECOMMENDED_MIRROR_SCOPES = [
    "postgres_chain",
    "runtime_metadata",
    "auth_state",
]


def google_drive_cloudstorage_root() -> Path:
    override = os.environ.get("GOOGLE_DRIVE_CLOUDSTORAGE_ROOT")
    if override:
        return Path(override).expanduser()
    return Path.home() / "Library" / "CloudStorage"


def google_drive_account_label(mount_path: Path) -> str:
    name = mount_path.name
    return name.removeprefix("GoogleDrive-") or name


def find_google_drive_mounts() -> list[dict[str, Any]]:
    cloud_root = google_drive_cloudstorage_root()
    mounts: list[dict[str, Any]] = []
    if not cloud_root.is_dir():
        return mounts

    for mount_path in sorted(cloud_root.glob("GoogleDrive-*")):
        if not mount_path.is_dir():
            continue
        my_drive_path = None
        for drive_name in GOOGLE_DRIVE_MY_DRIVE_NAMES:
            candidate = mount_path / drive_name
            if candidate.is_dir():
                my_drive_path = candidate
                break
        if my_drive_path is None:
            continue
        mindscape_root = my_drive_path / "Mindscape"
        mounts.append(
            {
                "account_label": google_drive_account_label(mount_path),
                "mount_path": str(mount_path),
                "my_drive_path": str(my_drive_path),
                "recommended_mirror_root": str(mindscape_root / "local-core-runtime-backups"),
                "recommended_resource_root": str(mindscape_root / "local-core-resource-collaboration"),
            }
        )
    return mounts


def command_google_drive_status(_args: argparse.Namespace) -> dict[str, Any]:
    mounts = find_google_drive_mounts()
    selected = mounts[0] if mounts else {}
    warnings: list[str] = []
    if not mounts:
        warnings.append("Google Drive CloudStorage mount was not found on this host.")
    return {
        "available": bool(mounts),
        "mounts": mounts,
        "account_label": selected.get("account_label", ""),
        "mount_path": selected.get("mount_path", ""),
        "my_drive_path": selected.get("my_drive_path", ""),
        "recommended_mirror_root": selected.get("recommended_mirror_root", ""),
        "recommended_resource_root": selected.get("recommended_resource_root", ""),
        "recommended_mirror_scopes": GOOGLE_DRIVE_RECOMMENDED_MIRROR_SCOPES,
        "warnings": warnings,
    }


def _path_inside_any(candidate: Path, roots: list[Path]) -> bool:
    expanded = candidate.expanduser()
    candidate_parts = expanded.parts
    for root in roots:
        root_parts = root.expanduser().parts
        if candidate_parts[: len(root_parts)] == root_parts:
            return True
    return False


def command_prepare_google_drive(args: argparse.Namespace) -> dict[str, Any]:
    status = command_google_drive_status(args)
    if not status["available"]:
        return {**status, "success": False, "prepared": False}

    my_drive_roots = [Path(str(item["my_drive_path"])) for item in status["mounts"]]
    mirror_root = Path(args.mirror_root or status["recommended_mirror_root"]).expanduser()
    resource_root = Path(args.resource_root or status["recommended_resource_root"]).expanduser()
    warnings = list(status.get("warnings") or [])

    for label, target in [("mirror_root", mirror_root), ("resource_root", resource_root)]:
        if not _path_inside_any(target, my_drive_roots):
            return {
                **status,
                "success": False,
                "prepared": False,
                "error": f"{label} must be inside the detected Google Drive My Drive mount.",
                "mirror_root": str(mirror_root),
                "resource_root": str(resource_root),
            }

    mirror_root.mkdir(parents=True, exist_ok=True)
    resource_root.mkdir(parents=True, exist_ok=True)
    for child in ["manifests", "incoming", "outgoing", "resource-index"]:
        (resource_root / child).mkdir(parents=True, exist_ok=True)

    policy = {
        "schema_version": 1,
        "purpose": "mindscape-local-core-google-drive-sync",
        "created_at": utc_now(),
        "mirror_root": str(mirror_root),
        "resource_root": str(resource_root),
        "recommended_mirror_scopes": GOOGLE_DRIVE_RECOMMENDED_MIRROR_SCOPES,
        "do_not_sync_live_roots": [
            "/Volumes/*",
            "live runtime databases",
            "model caches",
            "node_modules",
            "virtual environments",
            "temporary workspaces",
        ],
    }
    write_json(resource_root / ".mindscape-sync-policy.json", policy)
    readme = resource_root / "README.md"
    if not readme.exists():
        readme.write_text(
            "\n".join(
                [
                    "# Mindscape Local-Core Google Drive Collaboration",
                    "",
                    "Use this folder for small resource manifests, indexes, and exchange bundles.",
                    "Do not place live runtime databases, model caches, dependency folders, or full external drives here.",
                    "",
                    "Runtime backup archives belong in the sibling local-core-runtime-backups folder.",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

    return {
        **status,
        "success": True,
        "prepared": True,
        "mirror_root": str(mirror_root),
        "resource_root": str(resource_root),
        "policy_path": str(resource_root / ".mindscape-sync-policy.json"),
        "warnings": warnings,
    }
