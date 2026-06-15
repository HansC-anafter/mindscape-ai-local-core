#!/usr/bin/env python3
"""Command implementations for local runtime backup jobs."""

from __future__ import annotations

import argparse
import json
import secrets
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .backup_info import latest_backup
from .common import (
    INCREMENTAL_SCRIPT,
    POLICY_SCRIPT,
    REPO_ROOT,
    VERIFY_SCRIPT,
    resolve_backup_root,
    run_text,
    utc_now,
)
from .state import job_path, job_root, latest_job, read_json, refresh_job, tail_log, write_json


def add_policy_flags(cmd: list[str], args: argparse.Namespace) -> list[str]:
    if getattr(args, "output_dir", None) and "--output-dir" not in cmd:
        cmd.extend(["--output-dir", str(args.output_dir)])
    if getattr(args, "mirror_root", None) is not None:
        cmd.extend(["--mirror-root", str(args.mirror_root)])
    if getattr(args, "retention_local_count", None) is not None:
        cmd.extend(["--retention-local-count", str(args.retention_local_count)])
    if getattr(args, "retention_mirror_count", None) is not None:
        cmd.extend(["--retention-mirror-count", str(args.retention_mirror_count)])
    if getattr(args, "min_free_gb", None) is not None:
        cmd.extend(["--min-free-gb", str(args.min_free_gb)])
    if getattr(args, "require_mirror", None) is not None:
        cmd.extend(["--require-mirror", str(args.require_mirror).lower()])
    if getattr(args, "base_interval_hours", None) is not None:
        cmd.extend(["--base-interval-hours", str(args.base_interval_hours)])
    if getattr(args, "mirror_scopes", None):
        cmd.extend(["--mirror-scopes", str(args.mirror_scopes)])
    return cmd


def build_backup_command(args: argparse.Namespace, backup_root: Path, backup_name: str) -> list[str]:
    return add_policy_flags([
        "python3",
        str(POLICY_SCRIPT),
        "run",
        "--name",
        backup_name,
    ], args)


def command_start(args: argparse.Namespace) -> dict[str, Any]:
    if not POLICY_SCRIPT.is_file():
        raise SystemExit(f"Backup policy script not found: {POLICY_SCRIPT}")
    if not INCREMENTAL_SCRIPT.is_file():
        raise SystemExit(f"Incremental backup script not found: {INCREMENTAL_SCRIPT}")

    backup_root = resolve_backup_root(args.output_dir)
    existing = latest_job(backup_root)
    if existing and existing.get("state") == "running":
        raise SystemExit(f"Backup job already running: {existing.get('job_id')}")

    backup_root.mkdir(parents=True, exist_ok=True)
    job_id = f"backup_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{secrets.token_hex(3)}"
    backup_name = args.name or f"mindscape_local_runtime_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    logs_dir = job_root(backup_root)
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / f"{job_id}.log"
    cmd = build_backup_command(args, backup_root, backup_name)

    with log_path.open("ab") as log_handle:
        process = subprocess.Popen(
            cmd,
            cwd=REPO_ROOT,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    job = {
        "job_id": job_id,
        "state": "running",
        "pid": process.pid,
        "started_at": utc_now(),
        "backup_name": backup_name,
        "backup_root": str(backup_root),
        "backup_dir": str(backup_root / backup_name),
        "log_path": str(log_path),
        "command": cmd,
        "options": {
            "mode": "incremental_runtime_backup",
            "mirror_root": str(args.mirror_root or ""),
            "retention_local_count": args.retention_local_count,
            "retention_mirror_count": args.retention_mirror_count,
            "min_free_gb": args.min_free_gb,
            "require_mirror": args.require_mirror,
            "base_interval_hours": args.base_interval_hours,
            "mirror_scopes": args.mirror_scopes,
        },
    }
    write_json(job_path(backup_root, job_id), job)
    return {**job, "log_tail": []}


def command_status(args: argparse.Namespace) -> dict[str, Any]:
    backup_root = resolve_backup_root(args.output_dir)
    if args.job_id:
        path = job_path(backup_root, args.job_id)
        if not path.is_file():
            raise SystemExit(f"Backup job not found: {args.job_id}")
        job = refresh_job(read_json(path))
    else:
        job = latest_job(backup_root)

    if not job:
        return {"job": None, "backup_root": str(backup_root)}

    return {
        "job": job,
        "backup_root": str(backup_root),
        "log_tail": tail_log(job.get("log_path"), args.log_lines),
    }


def command_dry_run(args: argparse.Namespace) -> dict[str, Any]:
    backup_root = resolve_backup_root(args.output_dir)
    cmd = add_policy_flags(
        ["python3", str(POLICY_SCRIPT), "plan", "--output-dir", str(backup_root), "--json"],
        args,
    )

    result = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=120,
    )
    return {
        "success": result.returncode == 0,
        "returncode": result.returncode,
        "backup_root": str(backup_root),
        "stdout": result.stdout,
        "stderr": result.stderr,
        "command": cmd,
    }


def command_plan(args: argparse.Namespace) -> dict[str, Any]:
    backup_root = resolve_backup_root(args.output_dir)
    cmd = add_policy_flags(
        ["python3", str(POLICY_SCRIPT), "plan", "--output-dir", str(backup_root), "--json"],
        args,
    )
    result = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=120,
    )
    payload: dict[str, Any]
    try:
        payload = json.loads(result.stdout or "{}")
    except Exception:
        payload = {}
    payload.update(
        {
            "success": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "command": cmd,
        }
    )
    return payload


def command_postgres_status(_args: argparse.Namespace) -> dict[str, Any]:
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
    archiver = {
        "archived_count": 0,
        "last_archived_wal": "",
        "last_archived_time": "",
        "failed_count": 0,
        "last_failed_wal": "",
        "last_failed_time": "",
        "stats_reset": "",
    }
    parts = raw_archiver.split("|")
    if len(parts) >= 7:
        archiver = {
            "archived_count": int(parts[0] or "0"),
            "last_archived_wal": parts[1],
            "last_archived_time": parts[2],
            "failed_count": int(parts[3] or "0"),
            "last_failed_wal": parts[4],
            "last_failed_time": parts[5],
            "stats_reset": parts[6],
        }
    ready_count = run_text(
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
    wal_kib = run_text(
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
    return {
        "archive_mode": archive_mode,
        "archive_command": archive_command,
        "wal_ready_count": int(ready_count or "0"),
        "wal_bytes": int(wal_kib or "0") * 1024,
        "archiver_archived_count": archiver["archived_count"],
        "archiver_last_archived_wal": archiver["last_archived_wal"],
        "archiver_last_archived_time": archiver["last_archived_time"],
        "archiver_failed_count": archiver["failed_count"],
        "archiver_last_failed_wal": archiver["last_failed_wal"],
        "archiver_last_failed_time": archiver["last_failed_time"],
        "archiver_stats_reset": archiver["stats_reset"],
    }


def command_verify(args: argparse.Namespace) -> dict[str, Any]:
    backup_root = resolve_backup_root(args.output_dir)
    backup_dir = Path(args.backup_dir).expanduser() if args.backup_dir else None
    if backup_dir is None:
        manifests = sorted(
            backup_root.glob("*/manifest.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if not manifests:
            raise SystemExit(f"No backup manifest found under {backup_root}")
        backup_dir = manifests[0].parent

    result = subprocess.run(
        ["bash", str(VERIFY_SCRIPT), str(backup_dir)],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=args.timeout_seconds,
    )
    return {
        "success": result.returncode == 0,
        "returncode": result.returncode,
        "backup_dir": str(backup_dir),
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
