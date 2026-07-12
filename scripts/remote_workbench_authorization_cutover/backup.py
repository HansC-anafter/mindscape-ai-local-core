"""Exact fresh database-only backup gate for Phase06 cutover."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .io import CommandExecutor, CutoverError


BACKUP_MAX_AGE_SECONDS = 900
REQUIRED_DATABASE_ARTIFACTS = {
    "postgres/mindscape_core.dump",
    "postgres/mindscape_core.dump.list",
    "postgres/mindscape_vectors.dump",
    "postgres/mindscape_vectors.dump.list",
    "postgres/globals.sql",
}
EXACT_BACKUP_OPTIONS = {
    "include_e2e_traces": False,
    "include_logs": False,
    "include_thumbnails": False,
    "skip_db": False,
    "skip_files": True,
}


class BackupGate:
    """Create or accept only a current DB-only backup from canonical scripts."""

    def __init__(self, *, repo_root: Path, executor: CommandExecutor) -> None:
        self.repo_root = repo_root.resolve()
        self.executor = executor

    def _database_now(self) -> datetime:
        raw = self.executor.run(
            [
                "docker",
                "exec",
                "mindscape-ai-local-core-postgres",
                "psql",
                "-XqAt",
                "-U",
                "mindscape",
                "-d",
                "mindscape_core",
                "-c",
                "SELECT to_char(clock_timestamp() AT TIME ZONE 'UTC', "
                "'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"');",
            ],
            timeout_seconds=20.0,
        ).strip()
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError as error:
            raise CutoverError("Current PostgreSQL clock evidence is malformed") from error
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _load_manifest(backup_dir: Path) -> dict[str, Any]:
        manifest_path = backup_dir / "manifest.json"
        if manifest_path.is_symlink() or not manifest_path.is_file():
            raise CutoverError("Backup manifest is unavailable")
        if manifest_path.stat().st_size > 1_048_576:
            raise CutoverError("Backup manifest exceeds its byte budget")
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise CutoverError("Backup manifest is malformed") from error
        if not isinstance(payload, dict):
            raise CutoverError("Backup manifest must be an object")
        return payload

    def _validate_phase06_manifest(self, backup_dir: Path) -> None:
        manifest = self._load_manifest(backup_dir)
        if manifest.get("schema_version") != "1.0":
            raise CutoverError("Backup schema is not the Phase06 legacy backup schema")
        if Path(str(manifest.get("repo_root") or "")).resolve() != self.repo_root:
            raise CutoverError("Backup was not created from the canonical Local repository")
        if manifest.get("options") != EXACT_BACKUP_OPTIONS:
            raise CutoverError("Backup must be an exact DB-only --skip-files backup")
        artifacts = manifest.get("artifacts")
        if not isinstance(artifacts, list):
            raise CutoverError("Backup artifact inventory is malformed")
        paths = {
            item.get("path")
            for item in artifacts
            if isinstance(item, dict)
            and type(item.get("bytes")) is int
            and item.get("bytes") > 0
            and isinstance(item.get("sha256"), str)
            and len(item.get("sha256")) == 64
        }
        if not REQUIRED_DATABASE_ARTIFACTS.issubset(paths):
            raise CutoverError("Backup does not cover both current PostgreSQL databases")
        raw_created_at = manifest.get("created_at")
        if not isinstance(raw_created_at, str):
            raise CutoverError("Backup created_at evidence is missing")
        try:
            created_at = datetime.fromisoformat(raw_created_at.replace("Z", "+00:00"))
        except ValueError as error:
            raise CutoverError("Backup created_at evidence is malformed") from error
        database_now = self._database_now()
        age = (database_now - created_at.astimezone(timezone.utc)).total_seconds()
        if age < -60 or age > BACKUP_MAX_AGE_SECONDS:
            raise CutoverError("Backup does not provide fresh current-database coverage")

    def _verify(self, backup_dir: Path) -> Path:
        if backup_dir.is_symlink() or not backup_dir.is_dir():
            raise CutoverError("Verified backup path must be a real directory")
        verify_script = self.repo_root / "scripts/verify_local_runtime_backup.sh"
        self.executor.run(
            [str(verify_script), str(backup_dir)],
            timeout_seconds=300.0,
        )
        self._validate_phase06_manifest(backup_dir)
        return backup_dir

    def verify_or_create(self) -> Path:
        """Always create one exact fresh backup with the canonical script."""

        output_value = os.getenv("REMOTE_WORKBENCH_BACKUP_OUTPUT_DIR")
        if not output_value:
            raise CutoverError("Set REMOTE_WORKBENCH_BACKUP_OUTPUT_DIR")
        output_dir = Path(output_value).expanduser()
        if output_dir.is_symlink():
            raise CutoverError("Backup output directory must not be symbolic")
        output_dir = output_dir.resolve()
        name = "remote-workbench-access-policy-" + datetime.now(timezone.utc).strftime(
            "%Y%m%dT%H%M%SZ"
        )
        backup_dir = output_dir / name
        self.executor.run(
            [
                str(self.repo_root / "scripts/backup_local_runtime.sh"),
                "--output-dir",
                str(output_dir),
                "--name",
                name,
                "--skip-files",
            ],
            timeout_seconds=1_800.0,
        )
        return self._verify(backup_dir)
