"""
Local runtime backup settings and controls.

The actual backup logic lives in host-side policy scripts. These routes surface
status/configuration to the settings UI and delegate long-running host execution
to Device Node.
"""

from __future__ import annotations

import json
import os
import shlex
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from backend.app.models.system_settings import SettingType, SystemSetting
from .shared import settings_store


router = APIRouter()

BACKUP_CATEGORY = "backup"
KEY_BACKUP_ROOT = "local_runtime_backup.backup_root"
KEY_MIRROR_ROOT = "local_runtime_backup.mirror_root"
KEY_RETENTION_LOCAL_COUNT = "local_runtime_backup.retention_local_count"
KEY_RETENTION_MIRROR_COUNT = "local_runtime_backup.retention_mirror_count"
KEY_MIN_FREE_GB = "local_runtime_backup.min_free_gb"
KEY_REQUIRE_MIRROR = "local_runtime_backup.require_mirror"
KEY_BASE_INTERVAL_HOURS = "local_runtime_backup.base_interval_hours"
KEY_MIRROR_SCOPES = "local_runtime_backup.mirror_scopes"
KEY_GOOGLE_DRIVE_RESOURCE_SYNC_ENABLED = "local_runtime_backup.google_drive_resource_sync_enabled"
KEY_GOOGLE_DRIVE_RESOURCE_ROOT = "local_runtime_backup.google_drive_resource_root"

DEFAULT_MIRROR_SCOPES = ["postgres_chain", "runtime_metadata", "auth_state"]
AVAILABLE_MIRROR_SCOPES = {
    "postgres_chain",
    "runtime_metadata",
    "auth_state",
    "blob_storage",
    "model_cache",
    "workspace_artifacts",
}

LOCALHOST_ADDRS = {"127.0.0.1", "localhost", "::1", "unknown", "testclient"}
DOCKER_LOCAL_PREFIXES = ("172.", "192.168.65.")


class LocalRuntimeBackupConfig(BaseModel):
    backup_root: str = ""
    mirror_root: str = ""
    retention_local_count: int = 7
    retention_mirror_count: int = 3
    min_free_gb: float = 20.0
    require_mirror: bool = False
    base_interval_hours: int = 168
    mirror_scopes: List[str] = Field(default_factory=lambda: list(DEFAULT_MIRROR_SCOPES))
    google_drive_resource_sync_enabled: bool = False
    google_drive_resource_root: str = ""


class GoogleDriveRuntimeSyncStatus(BaseModel):
    available: bool = False
    account_label: str = ""
    mount_path: str = ""
    my_drive_path: str = ""
    recommended_mirror_root: str = ""
    recommended_resource_root: str = ""
    recommended_mirror_scopes: List[str] = Field(default_factory=lambda: list(DEFAULT_MIRROR_SCOPES))
    mirror_root_active: bool = False
    resource_sync_enabled: bool = False
    resource_root: str = ""
    warnings: List[str] = Field(default_factory=list)


class LocalRuntimeBackupStatus(BaseModel):
    config: LocalRuntimeBackupConfig
    backup_root: str
    policy: Dict[str, Any] = Field(default_factory=dict)
    primary_free_bytes: Optional[int] = None
    mirror_free_bytes: Optional[int] = None
    postgres_archive_mode: Optional[str] = None
    postgres_wal_ready_count: Optional[int] = None
    postgres_wal_bytes: Optional[int] = None
    wal_archive_dir: Optional[str] = None
    wal_segment_count: Optional[int] = None
    wal_archive_bytes: Optional[int] = None
    base_backup_id: Optional[str] = None
    base_backup_created_at: Optional[str] = None
    base_backup_age_hours: Optional[float] = None
    base_backup_required: Optional[bool] = None
    latest_file_snapshot_id: Optional[str] = None
    can_run: bool = False
    blocking_reasons: List[str] = Field(default_factory=list)
    script_available: bool
    verify_script_available: bool
    host_project_root: str
    device_node_available: bool
    latest_backup: Optional[Dict[str, Any]] = None
    latest_job: Optional[Dict[str, Any]] = None
    commands: Dict[str, str]
    google_drive_sync: GoogleDriveRuntimeSyncStatus = Field(default_factory=GoogleDriveRuntimeSyncStatus)
    warnings: List[str] = Field(default_factory=list)


class BackupJobRequest(BaseModel):
    backup_root: Optional[str] = None
    mirror_root: Optional[str] = None
    retention_local_count: Optional[int] = None
    retention_mirror_count: Optional[int] = None
    min_free_gb: Optional[float] = None
    require_mirror: Optional[bool] = None
    base_interval_hours: Optional[int] = None
    mirror_scopes: Optional[List[str]] = None


class VerifyBackupRequest(BaseModel):
    backup_dir: Optional[str] = None


class GoogleDrivePrepareRequest(BaseModel):
    mirror_root: Optional[str] = None
    resource_root: Optional[str] = None


def _is_localhost(request: Request) -> bool:
    def is_local_addr(value: str) -> bool:
        addr = value.strip()
        if addr.startswith("[") and addr.endswith("]"):
            addr = addr[1:-1]
        if addr.startswith("::ffff:"):
            addr = addr.removeprefix("::ffff:")
        if addr.count(":") == 1 and "." in addr.split(":", 1)[0]:
            addr = addr.split(":", 1)[0]
        return addr in LOCALHOST_ADDRS or addr.startswith(DOCKER_LOCAL_PREFIXES)

    client_ip = request.client.host if request.client else "unknown"
    if is_local_addr(client_ip):
        return True
    host = request.headers.get("host", "")
    if host.startswith(("localhost:", "127.0.0.1:", "[::1]:")):
        return True
    forwarded_for = request.headers.get("x-forwarded-for", "")
    real_ip = request.headers.get("x-real-ip", "")
    return any(is_local_addr(part) for part in [real_ip, *forwarded_for.split(",")])


def _container_backup_root() -> Path:
    data_dir = Path(os.getenv("DATA_DIR") or "/app/data")
    return Path(os.getenv("LOCAL_CORE_BACKUP_ROOT_CONTAINER") or data_dir / "backups" / "local-runtime")


def _host_project_root() -> str:
    return (
        os.getenv("LOCAL_CORE_PROJECT_ROOT")
        or os.getenv("HOST_PROJECT_PATH")
        or ""
    )


def _script_path(name: str) -> Path:
    return Path("/app/scripts") / name


def _get_bool(key: str, default: bool = False) -> bool:
    value = settings_store.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _get_str(key: str, default: str = "") -> str:
    value = settings_store.get(key, default)
    if value is None:
        return default
    return str(value)


def _get_int(key: str, default: int, minimum: int = 1) -> int:
    value = settings_store.get(key, default)
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, parsed)


def _get_float(key: str, default: float, minimum: float = 0.0) -> float:
    value = settings_store.get(key, default)
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, parsed)


def _normalize_mirror_scopes(value: Any) -> List[str]:
    if value is None or value == "":
        raw_items = DEFAULT_MIRROR_SCOPES
    elif isinstance(value, list):
        raw_items = [str(item) for item in value]
    else:
        raw_items = [item.strip() for item in str(value).split(",")]

    scopes: List[str] = []
    for item in raw_items:
        if item in AVAILABLE_MIRROR_SCOPES and item not in scopes:
            scopes.append(item)
    if "postgres_chain" not in scopes:
        scopes.insert(0, "postgres_chain")
    return scopes


def _get_mirror_scopes() -> List[str]:
    value = settings_store.get(
        KEY_MIRROR_SCOPES,
        os.getenv("LOCAL_CORE_BACKUP_MIRROR_SCOPES", ",".join(DEFAULT_MIRROR_SCOPES)),
    )
    return _normalize_mirror_scopes(value)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, ""))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, ""))
    except (TypeError, ValueError):
        return default


def _load_config() -> LocalRuntimeBackupConfig:
    return LocalRuntimeBackupConfig(
        backup_root=_get_str(KEY_BACKUP_ROOT, os.getenv("LOCAL_CORE_BACKUP_ROOT", "")),
        mirror_root=_get_str(KEY_MIRROR_ROOT, os.getenv("LOCAL_CORE_BACKUP_MIRROR_ROOT", "")),
        retention_local_count=_get_int(
            KEY_RETENTION_LOCAL_COUNT,
            _env_int("LOCAL_CORE_BACKUP_RETENTION_LOCAL_COUNT", 7),
        ),
        retention_mirror_count=_get_int(
            KEY_RETENTION_MIRROR_COUNT,
            _env_int("LOCAL_CORE_BACKUP_RETENTION_MIRROR_COUNT", 3),
        ),
        min_free_gb=_get_float(
            KEY_MIN_FREE_GB,
            _env_float("LOCAL_CORE_BACKUP_MIN_FREE_GB", 20.0),
        ),
        require_mirror=_get_bool(
            KEY_REQUIRE_MIRROR,
            os.getenv("LOCAL_CORE_BACKUP_REQUIRE_MIRROR", "").strip().lower()
            in {"1", "true", "yes", "on"},
        ),
        base_interval_hours=_get_int(
            KEY_BASE_INTERVAL_HOURS,
            _env_int("LOCAL_CORE_BACKUP_BASE_INTERVAL_HOURS", 168),
        ),
        mirror_scopes=_get_mirror_scopes(),
        google_drive_resource_sync_enabled=_get_bool(
            KEY_GOOGLE_DRIVE_RESOURCE_SYNC_ENABLED,
            os.getenv("LOCAL_CORE_GOOGLE_DRIVE_RESOURCE_SYNC_ENABLED", "").strip().lower()
            in {"1", "true", "yes", "on"},
        ),
        google_drive_resource_root=_get_str(
            KEY_GOOGLE_DRIVE_RESOURCE_ROOT,
            os.getenv("LOCAL_CORE_GOOGLE_DRIVE_RESOURCE_ROOT", ""),
        ),
    )


def _save_bool_setting(key: str, value: bool, description: str) -> None:
    settings_store.save_setting(
        SystemSetting(
            key=key,
            value=value,
            value_type=SettingType.BOOLEAN,
            category=BACKUP_CATEGORY,
            description=description,
        )
    )


def _save_string_setting(key: str, value: str, description: str) -> None:
    settings_store.save_setting(
        SystemSetting(
            key=key,
            value=value,
            value_type=SettingType.STRING,
            category=BACKUP_CATEGORY,
            description=description,
        )
    )


def _save_int_setting(key: str, value: int, description: str) -> None:
    settings_store.save_setting(
        SystemSetting(
            key=key,
            value=value,
            value_type=SettingType.INTEGER,
            category=BACKUP_CATEGORY,
            description=description,
        )
    )


def _save_float_setting(key: str, value: float, description: str) -> None:
    settings_store.save_setting(
        SystemSetting(
            key=key,
            value=value,
            value_type=SettingType.FLOAT,
            category=BACKUP_CATEGORY,
            description=description,
        )
    )


def _option_flags(config: LocalRuntimeBackupConfig) -> List[str]:
    flags: List[str] = [
        "--retention-local-count",
        str(config.retention_local_count),
        "--retention-mirror-count",
        str(config.retention_mirror_count),
        "--min-free-gb",
        str(config.min_free_gb),
        "--require-mirror",
        str(config.require_mirror).lower(),
        "--base-interval-hours",
        str(config.base_interval_hours),
        "--mirror-scopes",
        ",".join(_normalize_mirror_scopes(config.mirror_scopes)),
    ]
    if config.backup_root:
        flags.extend(["--output-dir", config.backup_root])
    if config.mirror_root:
        flags.extend(["--mirror-root", config.mirror_root])
    return flags


def _command(parts: List[str]) -> str:
    return " ".join(shlex.quote(part) for part in parts)


def _build_commands(config: LocalRuntimeBackupConfig, latest_backup: Optional[Dict[str, Any]]) -> Dict[str, str]:
    root = _host_project_root()
    if not root:
        hint = "Set LOCAL_CORE_PROJECT_ROOT to the host checkout path."
        return {
            "create": hint,
            "dry_run": hint,
            "verify_latest": hint,
        }
    flags = _option_flags(config)
    base = f"cd {_command([root])}"
    create = f"{base} && {_command(['python3', 'scripts/local_runtime_backup_job.py', 'start', *flags])}"
    dry_run = f"{base} && {_command(['python3', 'scripts/local_runtime_backup_job.py', 'plan', *flags])}"
    verify_target = latest_backup.get("host_backup_dir") if latest_backup else "<backup-dir>"
    verify = f"{base} && {_command(['scripts/verify_local_runtime_backup.sh', str(verify_target)])}"
    return {
        "create": create,
        "dry_run": dry_run,
        "verify_latest": verify,
    }


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


def _merge_request_config(request: BackupJobRequest) -> LocalRuntimeBackupConfig:
    config = _load_config()
    return LocalRuntimeBackupConfig(
        backup_root=config.backup_root if request.backup_root is None else request.backup_root,
        mirror_root=config.mirror_root if request.mirror_root is None else request.mirror_root,
        retention_local_count=(
            config.retention_local_count
            if request.retention_local_count is None
            else request.retention_local_count
        ),
        retention_mirror_count=(
            config.retention_mirror_count
            if request.retention_mirror_count is None
            else request.retention_mirror_count
        ),
        min_free_gb=config.min_free_gb if request.min_free_gb is None else request.min_free_gb,
        require_mirror=config.require_mirror if request.require_mirror is None else request.require_mirror,
        base_interval_hours=(
            config.base_interval_hours
            if request.base_interval_hours is None
            else request.base_interval_hours
        ),
        mirror_scopes=_normalize_mirror_scopes(
            config.mirror_scopes if request.mirror_scopes is None else request.mirror_scopes
        ),
        google_drive_resource_sync_enabled=config.google_drive_resource_sync_enabled,
        google_drive_resource_root=config.google_drive_resource_root,
    )


def _job_args(command: str, config: LocalRuntimeBackupConfig) -> List[str]:
    args = [command]
    args.extend(_option_flags(config))
    return args


@router.get("/backups/local-runtime", response_model=LocalRuntimeBackupStatus)
async def get_local_runtime_backup_status(include_plan: bool = Query(False)):
    config = _load_config()
    latest = _latest_backup()
    warnings: List[str] = []
    backup_root = _container_backup_root()
    backup_root_label = str(Path(config.backup_root).expanduser()) if config.backup_root else str(backup_root)
    policy: Dict[str, Any] = {
        "mode": "incremental_runtime_backup",
        "primary_root": backup_root_label,
        "mirror_root": config.mirror_root,
        "retention_local_count": config.retention_local_count,
        "retention_mirror_count": config.retention_mirror_count,
        "min_free_gb": config.min_free_gb,
        "require_mirror": config.require_mirror,
        "base_interval_hours": config.base_interval_hours,
        "mirror_scopes": _normalize_mirror_scopes(config.mirror_scopes),
    }
    primary_free_bytes: Optional[int] = None
    mirror_free_bytes: Optional[int] = None
    postgres_archive_mode: Optional[str] = None
    postgres_wal_ready_count: Optional[int] = None
    postgres_wal_bytes: Optional[int] = None
    wal_archive_dir: Optional[str] = None
    wal_segment_count: Optional[int] = None
    wal_archive_bytes: Optional[int] = None
    base_backup_id: Optional[str] = None
    base_backup_created_at: Optional[str] = None
    base_backup_age_hours: Optional[float] = None
    base_backup_required: Optional[bool] = None
    latest_file_snapshot_id: Optional[str] = None
    can_run = False
    blocking_reasons: List[str] = []

    if not config.backup_root and not backup_root.exists():
        warnings.append(f"Backup root does not exist yet: {backup_root}")

    device_available = await _device_node_available()
    google_drive_sync = await _google_drive_sync_status(config, device_available)
    latest_job: Optional[Dict[str, Any]] = None
    if device_available:
        try:
            job_response = await _call_backup_job(_job_args("status", config), timeout_seconds=15)
            latest_job = job_response.get("job")
            if latest_job:
                latest_job["log_tail"] = job_response.get("log_tail") or []
        except HTTPException as exc:
            warnings.append(str(exc.detail))

        job_running = bool(latest_job and latest_job.get("state") == "running")
        if job_running:
            blocking_reasons.append("backup_job_running")
        elif config.require_mirror and not config.mirror_root:
            blocking_reasons.append("mirror_required_but_not_configured")
        elif include_plan:
            try:
                plan_response = await _call_backup_job(_job_args("plan", config), timeout_seconds=45)
                if isinstance(plan_response.get("policy"), dict):
                    policy = plan_response["policy"]
                    backup_root_label = str(policy.get("primary_root") or backup_root_label)
                primary_free_bytes = plan_response.get("primary_free_bytes")
                mirror_free_bytes = plan_response.get("mirror_free_bytes")
                postgres_archive_mode = plan_response.get("postgres_archive_mode")
                postgres_wal_ready_count = plan_response.get("postgres_wal_ready_count")
                postgres_wal_bytes = plan_response.get("postgres_wal_bytes")
                wal_archive_dir = plan_response.get("wal_archive_dir")
                wal_segment_count = plan_response.get("wal_segment_count")
                wal_archive_bytes = plan_response.get("wal_archive_bytes")
                base_backup_id = plan_response.get("base_backup_id")
                base_backup_created_at = plan_response.get("base_backup_created_at")
                base_backup_age_hours = plan_response.get("base_backup_age_hours")
                base_backup_required = plan_response.get("base_backup_required")
                latest_file_snapshot_id = plan_response.get("latest_file_snapshot_id")
                can_run = bool(plan_response.get("can_run"))
                blocking_reasons = [str(item) for item in plan_response.get("blocking_reasons") or []]
                warnings.extend(str(item) for item in plan_response.get("warnings") or [])
            except HTTPException as exc:
                warnings.append(str(exc.detail))
        else:
            can_run = True
        try:
            latest_response = await _call_backup_job(_job_args("latest-backup", config), timeout_seconds=15)
            latest = latest_response.get("latest_backup") or latest
        except HTTPException as exc:
            warnings.append(str(exc.detail))
    else:
        blocking_reasons.append("device_node_required")

    script_available = all(
        _script_path(name).is_file()
        for name in [
            "local_runtime_backup_job.py",
            "local_runtime_backup_policy.py",
            "local_runtime_incremental_backup.py",
        ]
    )
    verify_script_available = all(
        _script_path(name).is_file()
        for name in [
            "verify_local_runtime_backup.sh",
            "verify_local_runtime_incremental_backup.py",
        ]
    )
    if not script_available:
        blocking_reasons.append("backup_scripts_unavailable")
    if not verify_script_available:
        blocking_reasons.append("backup_verify_scripts_unavailable")

    return LocalRuntimeBackupStatus(
        config=config,
        backup_root=backup_root_label,
        policy=policy,
        primary_free_bytes=primary_free_bytes,
        mirror_free_bytes=mirror_free_bytes,
        postgres_archive_mode=postgres_archive_mode,
        postgres_wal_ready_count=postgres_wal_ready_count,
        postgres_wal_bytes=postgres_wal_bytes,
        wal_archive_dir=wal_archive_dir,
        wal_segment_count=wal_segment_count,
        wal_archive_bytes=wal_archive_bytes,
        base_backup_id=base_backup_id,
        base_backup_created_at=base_backup_created_at,
        base_backup_age_hours=base_backup_age_hours,
        base_backup_required=base_backup_required,
        latest_file_snapshot_id=latest_file_snapshot_id,
        can_run=can_run and script_available and verify_script_available,
        blocking_reasons=blocking_reasons,
        script_available=script_available,
        verify_script_available=verify_script_available,
        host_project_root=_host_project_root(),
        device_node_available=device_available,
        latest_backup=latest,
        latest_job=latest_job,
        commands=_build_commands(config, latest),
        google_drive_sync=google_drive_sync,
        warnings=warnings,
    )


@router.put("/backups/local-runtime/config", response_model=LocalRuntimeBackupStatus)
async def update_local_runtime_backup_config(config: LocalRuntimeBackupConfig):
    _save_string_setting(
        KEY_BACKUP_ROOT,
        config.backup_root.strip(),
        "Host primary root for verified local runtime backups",
    )
    _save_string_setting(
        KEY_MIRROR_ROOT,
        config.mirror_root.strip(),
        "Host mirror root for verified local runtime backups",
    )
    _save_int_setting(
        KEY_RETENTION_LOCAL_COUNT,
        config.retention_local_count,
        "Number of local runtime backups to retain",
    )
    _save_int_setting(
        KEY_RETENTION_MIRROR_COUNT,
        config.retention_mirror_count,
        "Number of mirrored local runtime backups to retain",
    )
    _save_float_setting(
        KEY_MIN_FREE_GB,
        config.min_free_gb,
        "Minimum free disk space in GB required before starting a backup",
    )
    _save_bool_setting(
        KEY_REQUIRE_MIRROR,
        config.require_mirror,
        "Require a writable mirror root before starting a local runtime backup",
    )
    _save_int_setting(
        KEY_BASE_INTERVAL_HOURS,
        config.base_interval_hours,
        "Maximum age in hours before creating a new physical base backup",
    )
    _save_string_setting(
        KEY_MIRROR_SCOPES,
        ",".join(_normalize_mirror_scopes(config.mirror_scopes)),
        "Comma-separated mirror data scopes for local runtime backup",
    )
    _save_bool_setting(
        KEY_GOOGLE_DRIVE_RESOURCE_SYNC_ENABLED,
        config.google_drive_resource_sync_enabled,
        "Enable Google Drive-backed local resource collaboration",
    )
    _save_string_setting(
        KEY_GOOGLE_DRIVE_RESOURCE_ROOT,
        config.google_drive_resource_root.strip(),
        "Host Google Drive root for local resource collaboration",
    )
    return await get_local_runtime_backup_status()


@router.post("/backups/local-runtime/dry-run")
async def dry_run_local_runtime_backup(request: Request, body: BackupJobRequest = BackupJobRequest()):
    if not _is_localhost(request):
        raise HTTPException(status_code=403, detail="Backup controls are restricted to localhost")
    config = _merge_request_config(body)
    return await _call_backup_job(_job_args("dry-run", config), timeout_seconds=130)


@router.post("/backups/local-runtime/start")
async def start_local_runtime_backup(request: Request, body: BackupJobRequest = BackupJobRequest()):
    if not _is_localhost(request):
        raise HTTPException(status_code=403, detail="Backup controls are restricted to localhost")
    config = _merge_request_config(body)
    return await _call_backup_job(_job_args("start", config), timeout_seconds=15)


@router.get("/backups/local-runtime/jobs/latest")
async def get_latest_local_runtime_backup_job():
    return await _call_backup_job(["status"], timeout_seconds=10)


@router.get("/backups/local-runtime/jobs/{job_id}")
async def get_local_runtime_backup_job(job_id: str):
    return await _call_backup_job(["status", "--job-id", job_id], timeout_seconds=10)


@router.post("/backups/local-runtime/verify")
async def verify_local_runtime_backup(request: Request, body: VerifyBackupRequest = VerifyBackupRequest()):
    if not _is_localhost(request):
        raise HTTPException(status_code=403, detail="Backup controls are restricted to localhost")

    args = ["verify"]
    args.extend(_option_flags(_load_config()))
    if body.backup_dir:
        args.extend(["--backup-dir", body.backup_dir])
    return await _call_backup_job(args, timeout_seconds=1205)


@router.post("/backups/local-runtime/google-drive/prepare")
async def prepare_google_drive_runtime_sync(
    request: Request,
    body: GoogleDrivePrepareRequest = GoogleDrivePrepareRequest(),
):
    if not _is_localhost(request):
        raise HTTPException(status_code=403, detail="Google Drive sync controls are restricted to localhost")

    config = _load_config()
    mirror_root = (body.mirror_root if body.mirror_root is not None else config.mirror_root).strip()
    resource_root = (
        body.resource_root
        if body.resource_root is not None
        else config.google_drive_resource_root
    ).strip()
    args = ["prepare-google-drive"]
    if mirror_root:
        args.extend(["--mirror-root", mirror_root])
    if resource_root:
        args.extend(["--resource-root", resource_root])
    return await _call_backup_job(args, timeout_seconds=30)
