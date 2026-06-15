#!/usr/bin/env python3
"""Constants and scalar parsing for incremental runtime backups."""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MODE = "incremental_runtime_backup"
REPO_ROOT = Path(__file__).resolve().parents[1]
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "verify_local_runtime_backup.sh"
BYTES_PER_GB = 1024**3
WAL_ARCHIVE_CONTAINER_DIR = "/var/lib/postgresql/wal_archive"
WAL_SEGMENT_BYTES = 16 * 1024 * 1024
WAL_SEGMENT_RE = re.compile(r"^[0-9A-F]{24}$")
BACKUP_LABEL_START_WAL_RE = re.compile(r"START WAL LOCATION: .*?\(file ([0-9A-F]{24})\)")
MANAGED_ARCHIVE_COMMAND = "/usr/local/bin/mindscape-archive-wal"
TRANSIENT_RSYNC_CODES = {23, 24}
RSYNC_SNAPSHOT_EXCLUDES = [
    "postgres",
    "backups",
    "e2e-traces",
    "ig_thumbnails",
    "ig_debug_*.png",
    "ig_visit_timeout_*.png",
]
MIRROR_SCOPE_POSTGRES = "postgres_chain"
MIRROR_DEFAULT_SCOPES = [MIRROR_SCOPE_POSTGRES, "runtime_metadata", "auth_state"]
MIRROR_SCOPE_DEFINITIONS = {
    MIRROR_SCOPE_POSTGRES: {
        "label": "PostgreSQL base and WAL chain",
        "paths": [],
        "default": True,
        "required": True,
    },
    "runtime_metadata": {
        "label": "Runtime metadata and compatibility state",
        "paths": [
            {"path": "runtime", "kind": "dir"},
            {"path": "runtime_contracts", "kind": "dir"},
            {"path": "runtime_object_catalog", "kind": "dir"},
            {"path": "content_variant_strategy", "kind": "dir"},
            {"path": "postgresql-normalization", "kind": "dir"},
            {"path": "workspaces", "kind": "dir"},
        ],
        "default": True,
        "required": False,
    },
    "auth_state": {
        "label": "Auth and device state",
        "paths": [
            {"path": "ig-browser-profiles", "kind": "dir"},
            {"path": "secrets/device_id", "kind": "file"},
            {"path": "secrets/encryption.key", "kind": "file"},
        ],
        "default": True,
        "required": False,
    },
    "blob_storage": {
        "label": "Blob and user storage",
        "paths": [
            {"path": "uploads", "kind": "dir"},
            {"path": "documents", "kind": "dir"},
            {"path": "user-documents", "kind": "dir"},
            {"path": "secrets/storage", "kind": "dir"},
        ],
        "default": False,
        "required": False,
    },
    "model_cache": {
        "label": "Model caches",
        "paths": [{"path": "secrets/models", "kind": "dir"}],
        "default": False,
        "required": False,
    },
    "workspace_artifacts": {
        "label": "Workspace-generated artifacts",
        "paths": [
            {"path": "secrets/workspaces", "kind": "dir"},
            {"path": "sandboxes", "kind": "dir"},
            {"path": "character_training_validation", "kind": "dir"},
        ],
        "default": False,
        "required": False,
    },
}
os.environ["PATH"] = (
    "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:"
    + os.environ.get("PATH", "")
)


def load_repo_env() -> None:
    env_path = REPO_ROOT / ".env"
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        os.environ.setdefault(key, value.strip().strip('"').strip("'"))


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def parse_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def parse_int(value: Any, default: int, minimum: int = 0) -> int:
    if value is None or value == "":
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, parsed)


def parse_float(value: Any, default: float, minimum: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, parsed)


def parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if value is None:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def archiver_currently_failing(postgres: dict[str, Any]) -> bool:
    failed_count = parse_int(postgres.get("archiver_failed_count"), 0)
    if failed_count <= 0:
        return False
    last_failed = parse_datetime(postgres.get("archiver_last_failed_time"))
    if last_failed is None:
        return True
    last_archived = parse_datetime(postgres.get("archiver_last_archived_time"))
    return last_archived is None or last_archived < last_failed


def parse_scopes(value: Any) -> list[str]:
    if value is None or value == "":
        raw_items = MIRROR_DEFAULT_SCOPES
    elif isinstance(value, list):
        raw_items = [str(item) for item in value]
    else:
        raw_items = [item.strip() for item in str(value).split(",")]

    scopes: list[str] = []
    for item in raw_items:
        if item in MIRROR_SCOPE_DEFINITIONS and item not in scopes:
            scopes.append(item)
    if MIRROR_SCOPE_POSTGRES not in scopes:
        scopes.insert(0, MIRROR_SCOPE_POSTGRES)
    return scopes


load_repo_env()
