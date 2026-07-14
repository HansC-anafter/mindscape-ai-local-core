#!/usr/bin/env python3
"""PostgreSQL archive and base-backup helpers."""

from __future__ import annotations

import subprocess
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
    partial_base = f"{container_base}.partial"
    lock_dir = f"{WAL_ARCHIVE_CONTAINER_DIR}/.pg_basebackup.lock.d"
    client_pid_file = f"{lock_dir}/client.pid"
    command = (
        "set -eu; "
        f"mkdir {lock_dir} 2>/dev/null || "
        "{ echo 'postgres_basebackup_already_running' >&2; exit 73; }; "
        f"printf '%s\\n' \"$$\" > {lock_dir}/owner.pid; "
        f"cleanup_backup_lock() {{ rm -f {lock_dir}/owner.pid {client_pid_file}; rmdir {lock_dir} 2>/dev/null || true; }}; "
        "trap cleanup_backup_lock EXIT INT TERM HUP; "
        f"rm -rf {partial_base} {container_base}; "
        f"mkdir -p {partial_base}; "
        f"pg_basebackup -U \"${{POSTGRES_USER:-mindscape}}\" -D {partial_base} -Fp -Xs -P -c fast & "
        "backup_client_pid=$!; "
        f"printf '%s\\n' \"$backup_client_pid\" > {client_pid_file}; "
        "if wait \"$backup_client_pid\"; then backup_client_status=0; "
        "else backup_client_status=$?; fi; "
        f"rm -f {client_pid_file}; "
        f"if test \"$backup_client_status\" -ne 0; then rm -rf {partial_base}; exit \"$backup_client_status\"; fi; "
        f"mv {partial_base} {container_base}"
    )
    cmd = ["docker", "exec", "mindscape-ai-local-core-postgres", "sh", "-lc", command]
    try:
        output = run_text(cmd, timeout=timeout_seconds)
    except (KeyboardInterrupt, subprocess.TimeoutExpired):
        _terminate_marked_basebackup_client(client_pid_file, partial_base)
        raise
    except subprocess.CalledProcessError as exc:
        detail = "\n".join(
            part.strip()
            for part in (exc.stdout or "", exc.stderr or "")
            if part and part.strip()
        )
        raise RuntimeError(
            f"pg_basebackup exited with status {exc.returncode}: "
            f"{detail or 'no stdout/stderr captured'}"
        ) from exc
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


def _terminate_marked_basebackup_client(client_pid_file: str, partial_base: str) -> None:
    """Terminate only the client PID written by this backup invocation.

    PostgreSQL exposes a server-side base-backup backend with a similar process
    name.  PID discovery from process listings can therefore terminate the
    database itself.  Cleanup is deliberately marker-bound and validates the
    marked process command before sending any signal.
    """

    lock_dir = client_pid_file.rsplit("/", 1)[0]
    cleanup = (
        "set -eu; "
        "marker_wait=0; "
        f"while test ! -r {client_pid_file} && test -d {lock_dir} "
        "&& test \"$marker_wait\" -lt 5; do "
        "sleep 1; marker_wait=$((marker_wait + 1)); done; "
        f"if test ! -r {client_pid_file}; then "
        f"test ! -d {lock_dir} && {{ rm -rf {partial_base}; exit 0; }}; "
        "exit 67; fi; "
        f"backup_client_pid=$(cat {client_pid_file}); "
        "case \"$backup_client_pid\" in ''|*[!0-9]*) exit 64;; esac; "
        "test -r \"/proc/$backup_client_pid/cmdline\"; "
        "backup_client_cmd=$(tr '\\000' ' ' < \"/proc/$backup_client_pid/cmdline\"); "
        "case \"$backup_client_cmd\" in pg_basebackup\\ *|*/pg_basebackup\\ *) ;; *) exit 65;; esac; "
        "kill -TERM \"$backup_client_pid\"; "
        "attempt=0; "
        "while kill -0 \"$backup_client_pid\" 2>/dev/null && test \"$attempt\" -lt 10; do "
        "sleep 1; attempt=$((attempt + 1)); "
        "done; "
        "if kill -0 \"$backup_client_pid\" 2>/dev/null; then "
        "backup_client_cmd=$(tr '\\000' ' ' < \"/proc/$backup_client_pid/cmdline\"); "
        "case \"$backup_client_cmd\" in pg_basebackup\\ *|*/pg_basebackup\\ *) "
        "kill -KILL \"$backup_client_pid\";; *) exit 66;; esac; "
        "fi; "
        f"rm -rf {partial_base}"
    )
    run_text(
        [
            "docker",
            "exec",
            "mindscape-ai-local-core-postgres",
            "sh",
            "-lc",
            cleanup,
        ],
        timeout=20,
    )


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
