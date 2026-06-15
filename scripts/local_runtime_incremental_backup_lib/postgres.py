#!/usr/bin/env python3
"""PostgreSQL archive and base-backup helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import WAL_ARCHIVE_CONTAINER_DIR, parse_int, utc_now
from .filesystem import (
    base_backup_start_segment,
    base_manifest_path,
    disk_usage_bytes,
    run_text,
    write_json,
)


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


def run_pg_basebackup(base_id: str, wal_root: Path, timeout_seconds: int) -> dict[str, Any]:
    container_base = f"{WAL_ARCHIVE_CONTAINER_DIR}/base_backups/{base_id}"
    command = (
        "set -e; "
        f"rm -rf {container_base}.partial {container_base}; "
        f"mkdir -p {container_base}.partial; "
        f"pg_basebackup -U \"${{POSTGRES_USER:-mindscape}}\" -D {container_base}.partial -Fp -Xs -P -c fast; "
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
        "start_wal_segment": base_backup_start_segment(host_base_dir),
        "command": cmd,
        "output": output,
        "bytes": disk_usage_bytes(host_base_dir),
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
