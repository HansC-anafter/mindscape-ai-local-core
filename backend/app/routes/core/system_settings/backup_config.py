"""Configuration, settings persistence, and command builders for backup routes."""

from __future__ import annotations

import os
import shlex
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.app.models.system_settings import SettingType, SystemSetting

from .backup_models import (
    BACKUP_CATEGORY,
    DEFAULT_MIRROR_SCOPES,
    AVAILABLE_MIRROR_SCOPES,
    KEY_BACKUP_ROOT,
    KEY_BASE_INTERVAL_HOURS,
    KEY_GOOGLE_DRIVE_RESOURCE_ROOT,
    KEY_GOOGLE_DRIVE_RESOURCE_SYNC_ENABLED,
    KEY_MIN_FREE_GB,
    KEY_MIRROR_ROOT,
    KEY_MIRROR_SCOPES,
    KEY_REQUIRE_MIRROR,
    KEY_RETENTION_LOCAL_COUNT,
    KEY_RETENTION_MIRROR_COUNT,
    BackupJobRequest,
    LocalRuntimeBackupConfig,
)
from .shared import settings_store


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
