"""Scope and source-chain validation for disposable restores."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import tempfile
from typing import Any


WAL_SEGMENT = re.compile(r"^[0-9A-F]{24}$")


@dataclass(frozen=True)
class RestoreScope:
    project: str
    compose_file: Path
    backup_dir: Path
    receipt_dir: Path
    data_dir: Path | None = None


@dataclass(frozen=True)
class RestoreSource:
    scope: RestoreScope
    manifest: dict[str, Any]
    base_dir: Path
    wal_dir: Path
    recovery_target_time: str
    required_wal_segments: tuple[str, ...]


def _resolve_recorded_or_relocated(
    recorded: object,
    relocated: Path,
) -> Path:
    candidate = Path(str(recorded or "")).expanduser()
    if candidate.is_dir():
        return candidate.resolve()
    return relocated.resolve()


def _parse_target_time(value: object) -> str:
    raw = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("restore_recovery_target_time_invalid") from exc
    if parsed.tzinfo is None:
        raise ValueError("restore_recovery_target_timezone_required")
    return raw


def validate_restore_scope(
    scope: RestoreScope,
    *,
    allow_existing_data: bool = False,
) -> RestoreSource:
    project = scope.project.strip()
    if not project.endswith("-restore-drill"):
        raise ValueError("restore_project_label_required")
    compose_file = scope.compose_file.resolve()
    if compose_file.name != "docker-compose.yml":
        raise ValueError("root_compose_entrypoint_required")
    backup_dir = scope.backup_dir.resolve()
    receipt_dir = scope.receipt_dir.resolve()
    data_dir = scope.data_dir.resolve() if scope.data_dir is not None else None
    forbidden = {
        Path("/var/lib/postgresql/data"),
        Path("/app/data"),
        Path.home() / ".mindscape" / "storage",
    }
    if backup_dir in forbidden or receipt_dir in forbidden:
        raise ValueError("production_path_forbidden")
    if data_dir is not None:
        temporary_roots = {
            Path("/private/tmp").resolve(),
            Path("/tmp").resolve(),
            Path(tempfile.gettempdir()).resolve(),
        }
        if data_dir in temporary_roots or not any(
            data_dir.is_relative_to(root) for root in temporary_roots
        ):
            raise ValueError("restore_data_directory_must_be_system_temporary")
        if data_dir.name != project:
            raise ValueError("restore_data_directory_must_match_project")
        if (
            data_dir.exists()
            and any(data_dir.iterdir())
            and not allow_existing_data
        ):
            raise ValueError("restore_data_directory_not_empty_cleanup_first")
        data_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = backup_dir / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError("restore_manifest_invalid") from exc
    if manifest.get("mode") != "incremental_runtime_backup":
        raise ValueError("incremental_restore_source_required")
    postgres = (manifest.get("components") or {}).get("postgres") or {}
    base_id = str(postgres.get("base_backup_id") or "").strip()
    if not base_id or "/" in base_id or ".." in base_id:
        raise ValueError("restore_base_backup_id_invalid")
    wal_dir = _resolve_recorded_or_relocated(
        postgres.get("wal_archive_dir"),
        backup_dir.parent / "postgres-wal-archive",
    )
    base_dir = _resolve_recorded_or_relocated(
        postgres.get("base_backup_dir"),
        wal_dir / "base_backups" / base_id,
    )
    try:
        wal_dir.relative_to(backup_dir.parent)
    except ValueError as exc:
        raise ValueError("restore_wal_directory_outside_backup_root") from exc
    try:
        base_dir.relative_to(wal_dir / "base_backups")
    except ValueError as exc:
        raise ValueError("restore_base_directory_outside_wal_root") from exc
    if not (base_dir / "PG_VERSION").is_file():
        raise ValueError("restore_base_pg_version_missing")
    if (base_dir / "PG_VERSION").read_text(encoding="utf-8").strip() != "16":
        raise ValueError("restore_postgres_16_required")
    if not (base_dir / "backup_label").is_file():
        raise ValueError("restore_backup_label_missing")
    if not wal_dir.is_dir():
        raise ValueError("restore_wal_directory_missing")
    required = tuple(
        segment
        for segment in (str(item) for item in postgres.get("wal_segments") or [])
        if WAL_SEGMENT.fullmatch(segment)
    )
    if not required:
        raise ValueError("restore_required_wal_segments_missing")
    missing = [segment for segment in required if not (wal_dir / segment).is_file()]
    if missing:
        raise ValueError(f"restore_wal_segment_missing:{missing[0]}")
    target_time = _parse_target_time(
        postgres.get("recovery_target_time") or manifest.get("created_at")
    )
    normalized_scope = RestoreScope(
        project=project,
        compose_file=compose_file,
        backup_dir=backup_dir,
        receipt_dir=receipt_dir,
        data_dir=data_dir,
    )
    receipt_dir.mkdir(parents=True, exist_ok=True)
    return RestoreSource(
        scope=normalized_scope,
        manifest=manifest,
        base_dir=base_dir,
        wal_dir=wal_dir,
        recovery_target_time=target_time,
        required_wal_segments=required,
    )
