"""Status, manifest, Device Node, and Google Drive helpers for backup routes."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from fastapi import HTTPException

from .backup_config import (
    _container_backup_root,
    _host_project_root,
    _normalize_mirror_scopes,
)
from .backup_models import DEFAULT_MIRROR_SCOPES, GoogleDriveRuntimeSyncStatus, LocalRuntimeBackupConfig


def _path_starts_with(path: str, root: str) -> bool:
    if not path or not root:
        return False
    candidate = Path(path).expanduser()
    parent = Path(root).expanduser()
    return candidate.parts[: len(parent.parts)] == parent.parts


async def _google_drive_sync_status(
    config: LocalRuntimeBackupConfig,
    device_available: bool,
) -> GoogleDriveRuntimeSyncStatus:
    status = GoogleDriveRuntimeSyncStatus(
        resource_sync_enabled=config.google_drive_resource_sync_enabled,
        resource_root=config.google_drive_resource_root,
    )
    if not device_available:
        status.warnings.append("Device Node is required to inspect the host Google Drive mount.")
        return status

    try:
        response = await _call_backup_job(["google-drive-status"], timeout_seconds=15)
    except HTTPException as exc:
        status.warnings.append(str(exc.detail))
        return status

    my_drive_path = str(response.get("my_drive_path") or "")
    recommended_scopes = response.get("recommended_mirror_scopes") or DEFAULT_MIRROR_SCOPES
    status.available = bool(response.get("available"))
    status.account_label = str(response.get("account_label") or "")
    status.mount_path = str(response.get("mount_path") or "")
    status.my_drive_path = my_drive_path
    status.recommended_mirror_root = str(response.get("recommended_mirror_root") or "")
    status.recommended_resource_root = str(response.get("recommended_resource_root") or "")
    status.recommended_mirror_scopes = _normalize_mirror_scopes(recommended_scopes)
    status.mirror_root_active = _path_starts_with(config.mirror_root, my_drive_path)
    status.warnings.extend(str(item) for item in response.get("warnings") or [])
    return status


def _profile_state_summary(backup_dir: Path) -> Optional[Dict[str, Any]]:
    report_path = backup_dir / "metadata" / "profile-state-report.json"
    if not report_path.is_file():
        return None
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"valid": False, "error": f"{type(exc).__name__}: {exc}"}

    profiles = report.get("profiles") or []
    invalid = [item for item in profiles if not item.get("valid")]
    return {
        "valid": not invalid,
        "profiles": len(profiles),
        "invalid_profiles": len(invalid),
        "invalid": invalid,
    }


def _parse_backup_manifest(manifest_path: Path) -> Optional[Dict[str, Any]]:
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
    data_host_dir = manifest.get("data_host_dir")
    host_backup_dir = (
        str(Path(str(data_host_dir)) / "backups" / "local-runtime" / backup_name)
        if data_host_dir
        else str(backup_dir)
    )
    created_at = manifest.get("created_at")

    return {
        "backup_name": backup_name,
        "created_at": created_at,
        "path": str(backup_dir),
        "host_backup_dir": host_backup_dir,
        "schema_version": manifest.get("schema_version"),
        "mode": manifest.get("mode") or "db_dump_only",
        "git_commit": manifest.get("git_commit"),
        "options": manifest.get("options") or {},
        "artifact_count": len(artifacts) if artifacts else len(components),
        "total_bytes": total_bytes,
        "base_backup_id": (components.get("postgres") or {}).get("base_backup_id"),
        "file_snapshot_id": backup_name if components.get("files") else "",
        "profile_state": _profile_state_summary(backup_dir),
        "manifest_mtime": manifest_path.stat().st_mtime,
    }


def _latest_backup() -> Optional[Dict[str, Any]]:
    backup_root = _container_backup_root()
    if not backup_root.is_dir():
        return None

    backups: List[Dict[str, Any]] = []
    for manifest_path in backup_root.glob("*/manifest.json"):
        parsed = _parse_backup_manifest(manifest_path)
        if parsed:
            backups.append(parsed)

    if not backups:
        return None

    def sort_key(item: Dict[str, Any]) -> Any:
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


async def _device_node_available() -> bool:
    device_node_url = os.getenv("DEVICE_NODE_URL", "http://host.docker.internal:3100")
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.post(
                f"{device_node_url}/mcp",
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
                headers={"Content-Type": "application/json", "User-Agent": "Mindscape-LocalCore/1.0"},
            )
        return 200 <= response.status_code < 300
    except Exception:
        return False


async def _call_backup_job(args: List[str], timeout_seconds: float = 30.0) -> Dict[str, Any]:
    device_node_url = os.getenv("DEVICE_NODE_URL", "http://host.docker.internal:3100")
    host_project_root = _host_project_root()
    if not host_project_root:
        raise HTTPException(
            status_code=400,
            detail="LOCAL_CORE_PROJECT_ROOT must be set to the host checkout path before running backup controls.",
        )
    mcp_request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "shell_execute",
            "arguments": {
                "command": "python3",
                "args": ["scripts/local_runtime_backup_job.py", *args],
                "cwd": host_project_root,
                "timeout_ms": int(timeout_seconds * 1000),
            },
        },
    }

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds + 5) as client:
            response = await client.post(
                f"{device_node_url}/mcp",
                json=mcp_request,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "Mindscape-LocalCore/1.0",
                    "X-Request-Source": "local-runtime-backup",
                },
            )
    except httpx.ConnectError:
        raise HTTPException(
            status_code=502,
            detail="Device Node not reachable. Start it on host before running backup controls.",
        )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Device Node backup command timed out")

    try:
        result = response.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Invalid Device Node response: {exc}")

    if response.status_code >= 400 or result.get("error"):
        error = result.get("error") or {}
        raise HTTPException(
            status_code=502,
            detail=error.get("message") or f"Device Node returned HTTP {response.status_code}",
        )

    content = result.get("result", {}).get("content") or []
    text = content[0].get("text") if content else "{}"
    try:
        return json.loads(text)
    except Exception:
        return {"raw": text}
