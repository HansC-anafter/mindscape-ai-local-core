#!/usr/bin/env python3
"""Filesystem, path, rsync, and manifest helpers for incremental backups."""

from __future__ import annotations

import fnmatch
import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import (
    BACKUP_LABEL_START_WAL_RE,
    MIRROR_SCOPE_DEFINITIONS,
    MODE,
    REPO_ROOT,
    RSYNC_SNAPSHOT_EXCLUDES,
    TRANSIENT_RSYNC_CODES,
    WAL_SEGMENT_BYTES,
    WAL_SEGMENT_RE,
    parse_bool,
)


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
    return resolve_data_host_dir().parent / "backups" / "local-runtime"


def resolve_mirror_root(mirror_root: str | None) -> Path | None:
    if mirror_root is not None:
        return resolve_path(mirror_root)
    return resolve_path(os.environ.get("LOCAL_CORE_BACKUP_MIRROR_ROOT"))


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


def base_backup_start_segment(base_dir: Path) -> str:
    label = base_dir / "backup_label"
    if not label.is_file():
        return ""
    try:
        text = label.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    match = BACKUP_LABEL_START_WAL_RE.search(text)
    return match.group(1) if match else ""


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


def parse_du_output_bytes(output: str) -> int:
    total = 0
    for line in output.splitlines():
        parts = line.split(None, 1)
        if not parts:
            continue
        try:
            total += int(parts[0]) * 1024
        except ValueError:
            continue
    return total


def disk_usage_many_bytes(paths: list[Path], timeout_seconds: int = 300) -> int:
    existing = [path for path in paths if path.exists()]
    if not existing:
        return 0
    total = 0
    chunk_size = 128
    for index in range(0, len(existing), chunk_size):
        chunk = existing[index : index + chunk_size]
        try:
            result = subprocess.run(
                ["du", "-sk", *[str(path) for path in chunk]],
                cwd=REPO_ROOT,
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout_seconds,
            )
            parsed = parse_du_output_bytes(result.stdout)
            if parsed:
                total += parsed
                continue
        except Exception:
            pass
        total += sum(dir_size_bytes(path) for path in chunk if path.exists())
    return total


def disk_usage_bytes(path: Path, timeout_seconds: int = 300) -> int:
    if not path.exists():
        return 0
    try:
        return disk_usage_many_bytes([path], timeout_seconds=timeout_seconds)
    except Exception:
        return dir_size_bytes(path)


def mixed_path_usage_bytes(paths: list[Path]) -> int:
    total = 0
    dirs: list[Path] = []
    for path in paths:
        try:
            if not path.exists():
                continue
            if path.is_file():
                total += path.stat().st_size
            else:
                dirs.append(path)
        except OSError:
            continue
    return total + disk_usage_many_bytes(dirs)


def rsync_snapshot_base_cmd() -> list[str]:
    cmd = ["rsync", "-a", "--delete"]
    for excluded in RSYNC_SNAPSHOT_EXCLUDES:
        cmd.extend(["--exclude", excluded])
    return cmd


def snapshot_path_excluded(name: str) -> bool:
    return any(fnmatch.fnmatch(name, pattern) for pattern in RSYNC_SNAPSHOT_EXCLUDES)


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


def snapshot_source_size_bytes(source: Path) -> int:
    if not source.exists():
        return 0
    return mixed_path_usage_bytes(
        [item for item in source.iterdir() if not snapshot_path_excluded(item.name)]
    )


def scoped_source_size_bytes(source: Path, scopes: list[str]) -> int:
    return mixed_path_usage_bytes([source / entry["path"] for entry in mirror_scope_entries(scopes)])


def estimate_bytes_from_rsync_result(
    result: subprocess.CompletedProcess[str],
    *,
    fallback_bytes: int,
    failure_label: str,
) -> int:
    output = "\n".join(part for part in (result.stdout, result.stderr) if part)
    transferred = parse_rsync_stat_bytes(output, "Total transferred file size")
    parsed = transferred or parse_rsync_stat_bytes(output, "Total file size")
    if result.returncode == 0:
        return parsed
    if result.returncode in TRANSIENT_RSYNC_CODES:
        return parsed or fallback_bytes
    raise SystemExit(f"{failure_label} failed with exit code {result.returncode}: {result.stderr}")


def use_rsync_dry_run_estimate() -> bool:
    return parse_bool(os.environ.get("LOCAL_CORE_BACKUP_RSYNC_DRY_RUN_ESTIMATE"), False)


def estimate_temp_parent(source: Path, previous: Path | None) -> Path:
    if previous and previous.is_dir():
        try:
            parent = previous.parents[1]
        except IndexError:
            parent = previous.parent
    else:
        parent = source.parent
    parent.mkdir(parents=True, exist_ok=True)
    return parent


def estimate_snapshot_transfer_bytes(source: Path, previous: Path | None, timeout_seconds: int) -> int:
    if not use_rsync_dry_run_estimate():
        return snapshot_source_size_bytes(source)
    with tempfile.TemporaryDirectory(
        prefix="mindscape-runtime-backup-estimate-",
        dir=str(estimate_temp_parent(source, previous)),
    ) as tmp_dir:
        cmd = rsync_snapshot_base_cmd()
        cmd.extend(["--dry-run", "--stats"])
        if previous and previous.is_dir():
            cmd.append(f"--link-dest={previous}")
        cmd.extend([f"{source}/", f"{tmp_dir}/"])
        result = run_capture(cmd, timeout=timeout_seconds)
        if result.returncode != 0 and previous is not None:
            fallback_cmd = rsync_snapshot_base_cmd()
            fallback_cmd.extend(["--dry-run", "--stats", f"{source}/", f"{tmp_dir}/"])
            result = run_capture(fallback_cmd, timeout=timeout_seconds)
    return estimate_bytes_from_rsync_result(
        result,
        fallback_bytes=snapshot_source_size_bytes(source),
        failure_label="rsync dry-run",
    )


def estimate_mirror_snapshot_transfer_bytes(
    source: Path,
    previous: Path | None,
    scopes: list[str],
    timeout_seconds: int,
) -> int:
    if not use_rsync_dry_run_estimate():
        return scoped_source_size_bytes(source, scopes)
    with tempfile.TemporaryDirectory(
        prefix="mindscape-runtime-mirror-estimate-",
        dir=str(estimate_temp_parent(source, previous)),
    ) as tmp_dir:
        cmd = ["rsync", "-a", "--delete", "--delete-excluded", "--dry-run", "--stats"]
        if previous and previous.is_dir():
            cmd.append(f"--link-dest={previous}")
        add_mirror_scope_filters(cmd, scopes)
        cmd.extend([f"{source}/", f"{tmp_dir}/"])
        result = run_capture(cmd, timeout=timeout_seconds)
    return estimate_bytes_from_rsync_result(
        result,
        fallback_bytes=scoped_source_size_bytes(source, scopes),
        failure_label="mirror rsync dry-run",
    )


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
