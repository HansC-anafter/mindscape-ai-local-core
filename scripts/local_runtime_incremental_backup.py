#!/usr/bin/env python3
"""Incremental local runtime backup policy and execution."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
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
MANAGED_ARCHIVE_COMMAND = "/usr/local/bin/mindscape-archive-wal"
TRANSIENT_RSYNC_CODES = {23, 24}
RSYNC_SNAPSHOT_EXCLUDES = ["postgres", "backups", "e2e-traces", "ig_thumbnails"]
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


load_repo_env()


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


def run_text(cmd: list[str], timeout: int | None = None) -> str:
    result = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )
    return "\n".join(part for part in (result.stdout, result.stderr) if part)


def run_capture(cmd: list[str], timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def resolve_path(raw: str | None, *, base: Path | None = None) -> Path | None:
    if not raw or not str(raw).strip():
        return None
    path = Path(str(raw).strip()).expanduser()
    if not path.is_absolute() and base is not None:
        path = base / path
    return path


def resolve_data_host_dir() -> Path:
    if os.environ.get("LOCAL_CORE_DATA_HOST_DIR"):
        return Path(os.environ["LOCAL_CORE_DATA_HOST_DIR"]).expanduser()
    try:
        container_id = run_text(["docker", "compose", "ps", "-q", "backend"], timeout=20).strip()
        if container_id:
            source = run_text(
                [
                    "docker",
                    "inspect",
                    "--format",
                    '{{range .Mounts}}{{if eq .Destination "/app/data"}}{{.Source}}{{end}}{{end}}',
                    container_id,
                ],
                timeout=20,
            ).strip()
            if source:
                return Path(source)
    except Exception:
        pass
    return REPO_ROOT / "data"


def resolve_primary_root(output_dir: str | None) -> Path:
    requested = resolve_path(output_dir)
    if requested:
        return requested
    env_root = resolve_path(os.environ.get("LOCAL_CORE_BACKUP_ROOT"))
    if env_root:
        return env_root
    return resolve_data_host_dir() / "backups" / "local-runtime"


def resolve_mirror_root(mirror_root: str | None) -> Path | None:
    return resolve_path(mirror_root or os.environ.get("LOCAL_CORE_BACKUP_MIRROR_ROOT"))


def resolve_wal_archive_root(primary_root: Path) -> Path:
    env_root = resolve_path(os.environ.get("LOCAL_CORE_POSTGRES_WAL_ARCHIVE_HOST_DIR"), base=REPO_ROOT)
    return env_root or primary_root / "postgres-wal-archive"


def disk_free_bytes(path: Path) -> int:
    target = path
    while not target.exists() and target.parent != target:
        target = target.parent
    return int(shutil.disk_usage(target).free)


def path_contains(parent: Path, child: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def state_root(primary_root: Path) -> Path:
    return primary_root / ".incremental"


def base_root(primary_root: Path, wal_root: Path | None = None) -> Path:
    return (wal_root or resolve_wal_archive_root(primary_root)) / "base_backups"


def metadata_root(primary_root: Path) -> Path:
    return state_root(primary_root) / "metadata"


def latest_pointer(primary_root: Path) -> Path:
    return metadata_root(primary_root) / "latest.json"


def base_manifest_path(base_dir: Path) -> Path:
    return base_dir / "base-manifest.json"


def list_wal_segments(wal_root: Path) -> list[str]:
    if not wal_root.is_dir():
        return []
    segments = []
    for path in wal_root.iterdir():
        name = path.name
        if path.is_file() and len(name) >= 24 and all(ch in "0123456789ABCDEF" for ch in name[:24]):
            segments.append(name)
    return sorted(segments)


def wal_archive_segment_size_mismatches(wal_root: Path) -> list[dict[str, Any]]:
    if not wal_root.is_dir():
        return []
    mismatches: list[dict[str, Any]] = []
    for path in wal_root.iterdir():
        if not path.is_file() or not WAL_SEGMENT_RE.fullmatch(path.name):
            continue
        try:
            size = path.stat().st_size
        except OSError:
            size = -1
        if size != WAL_SEGMENT_BYTES:
            mismatches.append(
                {
                    "name": path.name,
                    "bytes": size,
                    "expected_bytes": WAL_SEGMENT_BYTES,
                }
            )
    return sorted(mismatches, key=lambda item: str(item["name"]))


def dir_size_bytes(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    for item in path.rglob("*"):
        if item.is_file():
            try:
                total += item.stat().st_size
            except OSError:
                continue
    return total


def rsync_snapshot_base_cmd() -> list[str]:
    cmd = ["rsync", "-aH", "--delete"]
    for excluded in RSYNC_SNAPSHOT_EXCLUDES:
        cmd.extend(["--exclude", excluded])
    return cmd


def mirror_scope_entries(scopes: list[str]) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    seen = set()
    for scope in scopes:
        for entry in MIRROR_SCOPE_DEFINITIONS.get(scope, {}).get("paths", []):
            key = (str(entry["path"]), str(entry["kind"]))
            if key in seen:
                continue
            seen.add(key)
            entries.append({"path": str(entry["path"]).strip("/"), "kind": str(entry["kind"])})
    return entries


def add_include_ancestors(cmd: list[str], relpath: str) -> None:
    current = ""
    parts = [part for part in relpath.split("/") if part]
    for part in parts[:-1]:
        current = f"{current}/{part}" if current else part
        cmd.extend(["--include", f"/{current}/"])


def add_mirror_scope_filters(cmd: list[str], scopes: list[str]) -> None:
    for entry in mirror_scope_entries(scopes):
        path = entry["path"]
        add_include_ancestors(cmd, path)
        if entry["kind"] == "dir":
            cmd.extend(["--include", f"/{path}/***"])
        else:
            cmd.extend(["--include", f"/{path}"])
    cmd.extend(["--exclude", "/***"])


def parse_rsync_stat_bytes(output: str, label: str) -> int:
    pattern = re.compile(rf"^{re.escape(label)}:\s+([0-9,]+)\s+B$", re.MULTILINE)
    match = pattern.search(output)
    if not match:
        return 0
    return int(match.group(1).replace(",", ""))


def estimate_snapshot_transfer_bytes(source: Path, previous: Path | None, timeout_seconds: int) -> int:
    with tempfile.TemporaryDirectory(prefix="mindscape-runtime-backup-estimate-") as tmp_dir:
        cmd = rsync_snapshot_base_cmd()
        cmd.extend(["--dry-run", "--stats"])
        if previous and previous.is_dir():
            cmd.append(f"--link-dest={previous}")
        cmd.extend([f"{source}/", f"{tmp_dir}/"])
        result = run_capture(cmd, timeout=timeout_seconds)
    if result.returncode != 0:
        raise SystemExit(f"rsync dry-run failed with exit code {result.returncode}: {result.stderr}")
    output = "\n".join(part for part in (result.stdout, result.stderr) if part)
    transferred = parse_rsync_stat_bytes(output, "Total transferred file size")
    return transferred or parse_rsync_stat_bytes(output, "Total file size")


def estimate_mirror_snapshot_transfer_bytes(
    source: Path,
    previous: Path | None,
    scopes: list[str],
    timeout_seconds: int,
) -> int:
    with tempfile.TemporaryDirectory(prefix="mindscape-runtime-mirror-estimate-") as tmp_dir:
        cmd = ["rsync", "-aH", "--delete", "--delete-excluded", "--dry-run", "--stats"]
        if previous and previous.is_dir():
            cmd.append(f"--link-dest={previous}")
        add_mirror_scope_filters(cmd, scopes)
        cmd.extend([f"{source}/", f"{tmp_dir}/"])
        result = run_capture(cmd, timeout=timeout_seconds)
    if result.returncode != 0:
        raise SystemExit(f"mirror rsync dry-run failed with exit code {result.returncode}: {result.stderr}")
    output = "\n".join(part for part in (result.stdout, result.stderr) if part)
    transferred = parse_rsync_stat_bytes(output, "Total transferred file size")
    return transferred or parse_rsync_stat_bytes(output, "Total file size")


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


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def postgres_status() -> dict[str, Any]:
    archive_mode = "unknown"
    archive_command = ""
    ready_count = 0
    wal_bytes = 0
    archiver = {
        "archived_count": 0,
        "last_archived_wal": "",
        "last_archived_time": "",
        "failed_count": 0,
        "last_failed_wal": "",
        "last_failed_time": "",
        "stats_reset": "",
    }
    try:
        archive_mode = run_text(
            [
                "docker",
                "exec",
                "mindscape-ai-local-core-postgres",
                "psql",
                "-U",
                "mindscape",
                "-d",
                "mindscape_core",
                "-Atc",
                "show archive_mode",
            ],
            timeout=20,
        ).strip()
        archive_command = run_text(
            [
                "docker",
                "exec",
                "mindscape-ai-local-core-postgres",
                "psql",
                "-U",
                "mindscape",
                "-d",
                "mindscape_core",
                "-Atc",
                "show archive_command",
            ],
            timeout=20,
        ).strip()
        raw_archiver = run_text(
            [
                "docker",
                "exec",
                "mindscape-ai-local-core-postgres",
                "psql",
                "-U",
                "mindscape",
                "-d",
                "mindscape_core",
                "-Atc",
                (
                    "SELECT archived_count::bigint, COALESCE(last_archived_wal, ''), "
                    "COALESCE(last_archived_time::text, ''), failed_count::bigint, "
                    "COALESCE(last_failed_wal, ''), COALESCE(last_failed_time::text, ''), "
                    "COALESCE(stats_reset::text, '') FROM pg_stat_archiver"
                ),
            ],
            timeout=20,
        ).strip()
        parts = raw_archiver.split("|")
        if len(parts) >= 7:
            archiver = {
                "archived_count": parse_int(parts[0], 0),
                "last_archived_wal": parts[1],
                "last_archived_time": parts[2],
                "failed_count": parse_int(parts[3], 0),
                "last_failed_wal": parts[4],
                "last_failed_time": parts[5],
                "stats_reset": parts[6],
            }
        ready_count = int(
            run_text(
                [
                    "docker",
                    "exec",
                    "mindscape-ai-local-core-postgres",
                    "sh",
                    "-c",
                    "find /var/lib/postgresql/data/pgdata/pg_wal/archive_status -maxdepth 1 -name '*.ready' -type f | wc -l",
                ],
                timeout=60,
            ).strip()
            or "0"
        )
        wal_kib = int(
            run_text(
                [
                    "docker",
                    "exec",
                    "mindscape-ai-local-core-postgres",
                    "sh",
                    "-c",
                    "du -sk /var/lib/postgresql/data/pgdata/pg_wal 2>/dev/null | awk '{print $1}'",
                ],
                timeout=120,
            ).strip()
            or "0"
        )
        wal_bytes = wal_kib * 1024
    except Exception as exc:
        return {
            "archive_mode": archive_mode,
            "archive_command": archive_command,
            "wal_ready_count": ready_count,
            "wal_bytes": wal_bytes,
            "archiver_archived_count": archiver["archived_count"],
            "archiver_last_archived_wal": archiver["last_archived_wal"],
            "archiver_last_archived_time": archiver["last_archived_time"],
            "archiver_failed_count": archiver["failed_count"],
            "archiver_last_failed_wal": archiver["last_failed_wal"],
            "archiver_last_failed_time": archiver["last_failed_time"],
            "archiver_stats_reset": archiver["stats_reset"],
            "error": f"{type(exc).__name__}: {exc}",
        }
    return {
        "archive_mode": archive_mode,
        "archive_command": archive_command,
        "wal_ready_count": ready_count,
        "wal_bytes": wal_bytes,
        "archiver_archived_count": archiver["archived_count"],
        "archiver_last_archived_wal": archiver["last_archived_wal"],
        "archiver_last_archived_time": archiver["last_archived_time"],
        "archiver_failed_count": archiver["failed_count"],
        "archiver_last_failed_wal": archiver["last_failed_wal"],
        "archiver_last_failed_time": archiver["last_failed_time"],
        "archiver_stats_reset": archiver["stats_reset"],
    }


def build_config(args: argparse.Namespace) -> dict[str, Any]:
    primary_root = resolve_primary_root(getattr(args, "output_dir", None))
    mirror_root = resolve_mirror_root(getattr(args, "mirror_root", None))
    min_free_gb = parse_float(
        getattr(args, "min_free_gb", None) or os.environ.get("LOCAL_CORE_BACKUP_MIN_FREE_GB"),
        20.0,
    )
    require_mirror = parse_bool(
        getattr(args, "require_mirror", None),
        parse_bool(os.environ.get("LOCAL_CORE_BACKUP_REQUIRE_MIRROR"), False),
    )
    local_retention = parse_int(
        getattr(args, "retention_local_count", None)
        or os.environ.get("LOCAL_CORE_BACKUP_RETENTION_LOCAL_COUNT"),
        default=7,
        minimum=1,
    )
    mirror_retention = parse_int(
        getattr(args, "retention_mirror_count", None)
        or os.environ.get("LOCAL_CORE_BACKUP_RETENTION_MIRROR_COUNT"),
        default=3,
        minimum=1,
    )
    base_interval_hours = parse_int(
        getattr(args, "base_interval_hours", None)
        or os.environ.get("LOCAL_CORE_BACKUP_BASE_INTERVAL_HOURS"),
        default=168,
        minimum=1,
    )
    mirror_scopes = parse_scopes(
        getattr(args, "mirror_scopes", None) or os.environ.get("LOCAL_CORE_BACKUP_MIRROR_SCOPES")
    )
    return {
        "primary_root": primary_root,
        "mirror_root": mirror_root,
        "min_free_gb": min_free_gb,
        "require_mirror": require_mirror,
        "retention_local_count": local_retention,
        "retention_mirror_count": mirror_retention,
        "base_interval_hours": base_interval_hours,
        "mirror_scopes": mirror_scopes,
        "wal_archive_root": resolve_wal_archive_root(primary_root),
    }


def build_plan(args: argparse.Namespace) -> dict[str, Any]:
    config = build_config(args)
    primary_root = config["primary_root"]
    mirror_root = config["mirror_root"]
    wal_root = config["wal_archive_root"]
    min_free_bytes = int(config["min_free_gb"] * BYTES_PER_GB)
    warnings: list[str] = []
    blocking_reasons: list[str] = []

    primary_free = disk_free_bytes(primary_root)
    mirror_free = disk_free_bytes(mirror_root) if mirror_root else None
    if primary_free < min_free_bytes:
        blocking_reasons.append("primary_backup_root_below_min_free_space")
    if config["require_mirror"] and mirror_root is None:
        blocking_reasons.append("mirror_required_but_not_configured")
    if mirror_root and mirror_free is not None and mirror_free < min_free_bytes:
        blocking_reasons.append("mirror_backup_root_below_min_free_space")
    if config["retention_mirror_count"] > config["retention_local_count"]:
        blocking_reasons.append("mirror_retention_exceeds_local_retention")
    if not command_exists("rsync"):
        blocking_reasons.append("rsync_not_available")

    if not path_contains(primary_root, wal_root):
        blocking_reasons.append("wal_archive_outside_backup_root")

    pg = postgres_status()
    archive_mode = str(pg.get("archive_mode") or "unknown")
    archive_command = str(pg.get("archive_command") or "")
    if archive_mode != "on":
        blocking_reasons.append("postgres_archive_required")
    if MANAGED_ARCHIVE_COMMAND not in archive_command:
        blocking_reasons.append("postgres_archive_command_not_managed")
    if archiver_currently_failing(pg):
        blocking_reasons.append("postgres_archiver_currently_failing")
    elif parse_int(pg.get("archiver_failed_count"), 0) > 0:
        warnings.append("postgres_archiver_historical_failures_present")
    if pg.get("error"):
        warnings.append(str(pg["error"]))

    latest_base_manifest = latest_base(primary_root)
    latest_snapshot = latest_incremental_manifest(primary_root)
    base_age = age_hours(str(latest_base_manifest.get("created_at"))) if latest_base_manifest else None
    base_required = latest_base_manifest is None or (
        base_age is not None and base_age >= config["base_interval_hours"]
    )
    wal_segments = list_wal_segments(wal_root)
    wal_size_mismatches = wal_archive_segment_size_mismatches(wal_root)
    if wal_size_mismatches:
        blocking_reasons.append("wal_archive_segment_size_mismatch")
        sample = ",".join(str(item["name"]) for item in wal_size_mismatches[:10])
        warnings.append(f"wal_archive_segment_size_mismatch:{sample}")

    policy = {
        "mode": MODE,
        "primary_root": str(primary_root),
        "mirror_root": str(mirror_root) if mirror_root else "",
        "retention_local_count": config["retention_local_count"],
        "retention_mirror_count": config["retention_mirror_count"],
        "min_free_gb": config["min_free_gb"],
        "require_mirror": config["require_mirror"],
        "base_interval_hours": config["base_interval_hours"],
        "mirror_scopes": config["mirror_scopes"],
        "mirror_scope_definitions": MIRROR_SCOPE_DEFINITIONS,
        "wal_archive_root": str(wal_root),
    }

    return {
        "policy": policy,
        "primary_free_bytes": primary_free,
        "mirror_free_bytes": mirror_free,
        "min_free_bytes": min_free_bytes,
        "postgres_archive_mode": archive_mode,
        "postgres_archive_command": archive_command,
        "postgres_wal_ready_count": pg.get("wal_ready_count", 0),
        "postgres_wal_bytes": pg.get("wal_bytes", 0),
        "postgres_archiver_archived_count": pg.get("archiver_archived_count", 0),
        "postgres_archiver_last_archived_wal": pg.get("archiver_last_archived_wal", ""),
        "postgres_archiver_last_archived_time": pg.get("archiver_last_archived_time", ""),
        "postgres_archiver_failed_count": pg.get("archiver_failed_count", 0),
        "postgres_archiver_last_failed_wal": pg.get("archiver_last_failed_wal", ""),
        "postgres_archiver_last_failed_time": pg.get("archiver_last_failed_time", ""),
        "postgres_archiver_stats_reset": pg.get("archiver_stats_reset", ""),
        "wal_archive_dir": str(wal_root),
        "wal_segment_count": len(wal_segments),
        "wal_segment_size_mismatches": wal_size_mismatches,
        "wal_archive_bytes": dir_size_bytes(wal_root),
        "base_backup_id": latest_base_manifest.get("base_backup_id") if latest_base_manifest else "",
        "base_backup_created_at": latest_base_manifest.get("created_at") if latest_base_manifest else "",
        "base_backup_age_hours": base_age,
        "base_backup_required": base_required,
        "latest_file_snapshot_id": latest_snapshot.get("backup_name") if latest_snapshot else "",
        "can_run": not blocking_reasons,
        "blocking_reasons": blocking_reasons,
        "warnings": warnings,
    }


def safe_name(value: str) -> str:
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
    return "".join(ch if ch in allowed else "_" for ch in value)


def run_pg_basebackup(base_id: str, wal_root: Path, timeout_seconds: int) -> dict[str, Any]:
    container_base = f"{WAL_ARCHIVE_CONTAINER_DIR}/base_backups/{base_id}"
    command = (
        "set -e; "
        f"rm -rf {container_base}.partial {container_base}; "
        f"mkdir -p {container_base}.partial; "
        f"pg_basebackup -U \"${{POSTGRES_USER:-mindscape}}\" -D {container_base}.partial -Fp -Xs -P; "
        f"mv {container_base}.partial {container_base}"
    )
    cmd = ["docker", "exec", "mindscape-ai-local-core-postgres", "sh", "-lc", command]
    output = run_text(cmd, timeout=timeout_seconds)
    host_base_dir = wal_root / "base_backups" / base_id
    manifest = {
        "base_backup_id": base_id,
        "created_at": utc_now(),
        "host_base_dir": str(host_base_dir),
        "container_base_dir": container_base,
        "command": cmd,
        "output": output,
        "bytes": dir_size_bytes(host_base_dir),
    }
    write_json(base_manifest_path(host_base_dir), manifest)
    return manifest


def switch_wal() -> None:
    run_text(
        [
            "docker",
            "exec",
            "mindscape-ai-local-core-postgres",
            "psql",
            "-U",
            "mindscape",
            "-d",
            "mindscape_core",
            "-Atc",
            "select pg_switch_wal()",
        ],
        timeout=30,
    )


def rsync_snapshot(source: Path, target: Path, previous: Path | None, timeout_seconds: int) -> list[dict[str, Any]]:
    base_cmd = rsync_snapshot_base_cmd()
    if previous and previous.is_dir():
        base_cmd.append(f"--link-dest={previous}")
    base_cmd.extend([f"{source}/", f"{target}/"])

    results: list[dict[str, Any]] = []
    attempts = 0
    while attempts < 3:
        attempts += 1
        result = run_capture(base_cmd, timeout=timeout_seconds)
        results.append(
            {
                "command": base_cmd,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "attempt": attempts,
            }
        )
        if result.returncode == 0:
            if attempts == 1:
                continue
            return results
        if result.returncode not in TRANSIENT_RSYNC_CODES:
            raise SystemExit(f"rsync failed with exit code {result.returncode}: {result.stderr}")
    last = results[-1]
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
    if root.is_dir():
        for base_dir in root.iterdir():
            if base_dir.is_dir() and base_dir.name not in protected_base_ids:
                shutil.rmtree(base_dir)
                removed_bases.append(str(base_dir))

    return {
        "snapshots": removed,
        "base_backups": removed_bases,
        "wal_segments": [],
        "warnings": ["wal_prune_skipped_dependency_window_not_proven"],
    }


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
    missing = []
    for segment in postgres.get("wal_segments") or []:
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
        "restore_drill": restore,
    }


def clone_json(data: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(data))


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

    backup_cmd = ["rsync", "-aH", "--delete", "--delete-excluded"]
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
        ["rsync", "-aH", "--delete", f"{wal_root}/", f"{mirror_wal_root}/"],
        ["rsync", "-aH", "--delete", f"{state_root(primary_root)}/", f"{mirror_state_root}/"],
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


def build_previous_snapshot(primary_root: Path) -> tuple[dict[str, Any] | None, Path | None]:
    previous_manifest = latest_incremental_manifest(primary_root)
    if not previous_manifest:
        return None, None
    previous_backup_dir = Path(str(previous_manifest.get("backup_dir") or ""))
    previous_rel = str(previous_manifest.get("components", {}).get("files", {}).get("snapshot_relpath") or "app-data")
    return previous_manifest, previous_backup_dir / previous_rel


def previous_mirror_snapshot(mirror_root: Path | None, previous_manifest: dict[str, Any] | None) -> Path | None:
    if not mirror_root or not previous_manifest:
        return None
    previous_snapshot_id = str(previous_manifest.get("backup_name") or "")
    if not previous_snapshot_id:
        return None
    candidate = mirror_root / previous_snapshot_id / "app-data"
    return candidate if candidate.is_dir() else None


def capacity_preflight(
    *,
    plan: dict[str, Any],
    config: dict[str, Any],
    previous_manifest: dict[str, Any] | None,
    previous_snapshot: Path | None,
    timeout_seconds: int,
) -> dict[str, Any]:
    primary_root = config["primary_root"]
    mirror_root = config["mirror_root"]
    wal_root = config["wal_archive_root"]
    min_free_bytes = int(config["min_free_gb"] * BYTES_PER_GB)
    snapshot_transfer_bytes = estimate_snapshot_transfer_bytes(
        resolve_data_host_dir(),
        previous_snapshot,
        timeout_seconds,
    )
    mirror_snapshot_transfer_bytes = 0
    if mirror_root:
        mirror_snapshot_transfer_bytes = estimate_mirror_snapshot_transfer_bytes(
            resolve_data_host_dir(),
            previous_mirror_snapshot(mirror_root, previous_manifest),
            config["mirror_scopes"],
            timeout_seconds,
        )
    postgres_base_estimate_bytes = (
        dir_size_bytes(resolve_data_host_dir() / "postgres") if plan["base_backup_required"] else 0
    )
    wal_estimate_bytes = dir_size_bytes(wal_root)
    primary_estimated_required_bytes = snapshot_transfer_bytes + postgres_base_estimate_bytes + wal_estimate_bytes
    mirror_estimated_required_bytes = mirror_snapshot_transfer_bytes + postgres_base_estimate_bytes + wal_estimate_bytes
    primary_free = disk_free_bytes(primary_root)
    mirror_free = disk_free_bytes(mirror_root) if mirror_root else None

    blocking_reasons = []
    if primary_free < primary_estimated_required_bytes + min_free_bytes:
        blocking_reasons.append("primary_backup_root_below_estimated_required_space")
    if mirror_root and mirror_free is not None and mirror_free < mirror_estimated_required_bytes + min_free_bytes:
        blocking_reasons.append("mirror_backup_root_below_estimated_required_space")
    return {
        "snapshot_transfer_bytes": snapshot_transfer_bytes,
        "mirror_snapshot_transfer_bytes": mirror_snapshot_transfer_bytes,
        "postgres_base_estimate_bytes": postgres_base_estimate_bytes,
        "wal_estimate_bytes": wal_estimate_bytes,
        "estimated_required_bytes": primary_estimated_required_bytes,
        "primary_estimated_required_bytes": primary_estimated_required_bytes,
        "mirror_estimated_required_bytes": mirror_estimated_required_bytes,
        "min_free_bytes": min_free_bytes,
        "primary_free_bytes": primary_free,
        "mirror_free_bytes": mirror_free,
        "mirror_scopes": config["mirror_scopes"],
        "blocking_reasons": blocking_reasons,
    }


def run_policy(args: argparse.Namespace) -> dict[str, Any]:
    plan = build_plan(args)
    if not plan["can_run"]:
        raise SystemExit("Backup policy preflight failed: " + ", ".join(plan["blocking_reasons"]))

    config = build_config(args)
    primary_root = config["primary_root"]
    mirror_root = config["mirror_root"]
    wal_root = config["wal_archive_root"]
    timeout_seconds = int(getattr(args, "timeout_seconds", 7200) or 7200)
    backup_name = safe_name(getattr(args, "name", None) or f"mindscape_local_runtime_{utc_stamp()}")
    backup_dir = primary_root / backup_name
    partial_dir = primary_root / f".{backup_name}.partial"
    if backup_dir.exists():
        raise SystemExit(f"Backup already exists: {backup_dir}")
    if partial_dir.exists():
        shutil.rmtree(partial_dir)

    previous_manifest, previous_snapshot = build_previous_snapshot(primary_root)
    capacity = capacity_preflight(
        plan=plan,
        config=config,
        previous_manifest=previous_manifest,
        previous_snapshot=previous_snapshot,
        timeout_seconds=timeout_seconds,
    )
    if capacity["blocking_reasons"]:
        raise SystemExit("Backup capacity preflight failed: " + ", ".join(capacity["blocking_reasons"]))

    partial_dir.mkdir(parents=True, exist_ok=True)

    before_wal = list_wal_segments(wal_root)
    active_base = latest_base(primary_root)
    if plan["base_backup_required"]:
        base_id = f"base_{utc_stamp()}"
        active_base = run_pg_basebackup(base_id, wal_root, timeout_seconds)
    if not active_base:
        raise SystemExit("No verified base backup is available")

    switch_wal()
    after_wal = list_wal_segments(wal_root)
    new_wal = [name for name in after_wal if name not in before_wal]

    snapshot_dir = partial_dir / "app-data"
    rsync_results = rsync_snapshot(resolve_data_host_dir(), snapshot_dir, previous_snapshot, timeout_seconds)

    created_at = utc_now()
    base_dir = Path(str(active_base["host_base_dir"]))
    manifest = {
        "schema_version": "2.0",
        "mode": MODE,
        "backup_name": backup_name,
        "created_at": created_at,
        "backup_dir": str(backup_dir),
        "components": {
            "postgres": {
                "base_backup_id": active_base["base_backup_id"],
                "base_backup_dir": str(base_dir),
                "container_base_dir": active_base.get("container_base_dir"),
                "base_backup_created_at": active_base.get("created_at"),
                "base_backup_required": plan["base_backup_required"],
                "wal_archive_dir": str(wal_root),
                "wal_start_segment": new_wal[0] if new_wal else (after_wal[0] if after_wal else ""),
                "wal_end_segment": new_wal[-1] if new_wal else (after_wal[-1] if after_wal else ""),
                "wal_segments": after_wal,
                "new_wal_segments": new_wal,
                "wal_segment_count": len(after_wal),
                "wal_archive_bytes": dir_size_bytes(wal_root),
                "archive_mode": plan["postgres_archive_mode"],
            },
            "files": {
                "snapshot_relpath": "app-data",
                "previous_snapshot_id": previous_manifest.get("backup_name") if previous_manifest else "",
                "source_host_dir": str(resolve_data_host_dir()),
                "bytes": dir_size_bytes(snapshot_dir),
                "estimated_transfer_bytes": capacity["snapshot_transfer_bytes"],
                "rsync_results": rsync_results,
            },
        },
        "total_bytes": dir_size_bytes(snapshot_dir) + dir_size_bytes(base_dir),
        "capacity_preflight": capacity,
        "mirror": {
            "scope_mode": "selected_data_scopes",
            "scopes": config["mirror_scopes"],
            "scope_definitions": MIRROR_SCOPE_DEFINITIONS,
        },
        "verification": {"primary": "pending", "mirror": "pending"},
    }
    write_json(partial_dir / "manifest.json", manifest)
    partial_dir.rename(backup_dir)
    manifest["backup_dir"] = str(backup_dir)
    write_json(backup_dir / "manifest.json", manifest)

    primary_verify = verify_incremental_dir(backup_dir)
    manifest["verification"]["primary"] = "passed"
    write_json(backup_dir / "manifest.json", manifest)
    write_json(
        latest_pointer(primary_root),
        {
            "latest_backup_name": backup_name,
            "latest_backup_dir": str(backup_dir),
            "updated_at": utc_now(),
        },
    )

    local_pruned = prune_incremental(primary_root, config["retention_local_count"], backup_dir, wal_root=wal_root)
    mirror_result: dict[str, Any] = {"enabled": False}
    if mirror_root is not None:
        mirror_result = mirror_incremental_artifacts(
            primary_root=primary_root,
            mirror_root=mirror_root,
            backup_dir=backup_dir,
            wal_root=wal_root,
            manifest=manifest,
            timeout_seconds=timeout_seconds,
            retention_count=config["retention_mirror_count"],
            mirror_scopes=config["mirror_scopes"],
        )
        manifest["verification"]["mirror"] = "passed"
        write_json(backup_dir / "manifest.json", manifest)

    return {
        "success": True,
        "created_at": created_at,
        "backup_name": backup_name,
        "backup_dir": str(backup_dir),
        "mirror_dir": mirror_result.get("mirror_dir", ""),
        "policy": plan["policy"],
        "manifest": manifest,
        "verify": primary_verify,
        "mirror": mirror_result,
        "pruned": {"local": local_pruned, "mirror": mirror_result.get("pruned", [])},
    }
