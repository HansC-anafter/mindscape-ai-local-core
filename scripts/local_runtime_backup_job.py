#!/usr/bin/env python3
"""Host-side job wrapper for local runtime backup scripts.

This wrapper is intentionally small: the backup implementation remains in
backup_local_runtime.sh and verify_local_runtime_backup.sh. The wrapper only
starts long-running backups in the background and records job state for the UI.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKUP_SCRIPT = REPO_ROOT / "scripts" / "backup_local_runtime.sh"
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "verify_local_runtime_backup.sh"
os.environ["PATH"] = (
    "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:"
    + os.environ.get("PATH", "")
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run_text(cmd: list[str], timeout: int = 30) -> str:
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


def resolve_backup_root(output_dir: str | None) -> Path:
    if output_dir:
        return Path(output_dir).expanduser()
    if os.environ.get("LOCAL_CORE_BACKUP_ROOT"):
        return Path(os.environ["LOCAL_CORE_BACKUP_ROOT"]).expanduser()
    return resolve_data_host_dir() / "backups" / "local-runtime"


def job_root(backup_root: Path) -> Path:
    return backup_root / ".jobs"


def job_path(backup_root: Path, job_id: str) -> Path:
    return job_root(backup_root) / f"{job_id}.json"


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def pid_running(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def refresh_job(job: dict[str, Any]) -> dict[str, Any]:
    if job.get("state") != "running":
        return job

    pid = int(job.get("pid") or 0)
    backup_root = Path(str(job["backup_root"]))
    backup_name = str(job["backup_name"])
    final_dir = backup_root / backup_name
    partial_dir = backup_root / f".{backup_name}.partial"

    if pid_running(pid):
        return job

    updated = dict(job)
    updated["completed_at"] = updated.get("completed_at") or utc_now()
    if (final_dir / "manifest.json").is_file():
        updated["state"] = "succeeded"
        updated["backup_dir"] = str(final_dir)
    else:
        updated["state"] = "failed"
        updated["error"] = (
            "Backup process exited without producing manifest.json"
            + (f"; partial directory remains: {partial_dir}" if partial_dir.exists() else "")
        )
    write_json(job_path(backup_root, str(job["job_id"])), updated)
    return updated


def latest_job(backup_root: Path) -> dict[str, Any] | None:
    root = job_root(backup_root)
    if not root.is_dir():
        return None
    candidates = sorted(root.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    for path in candidates:
        try:
            return refresh_job(read_json(path))
        except Exception:
            continue
    return None


def tail_log(path: str | None, lines: int) -> list[str]:
    if not path:
        return []
    log_path = Path(path)
    if not log_path.is_file():
        return []
    content = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    return content[-lines:]


def build_backup_command(args: argparse.Namespace, backup_root: Path, backup_name: str) -> list[str]:
    cmd = ["bash", str(BACKUP_SCRIPT), "--output-dir", str(backup_root), "--name", backup_name]
    if args.include_logs:
        cmd.append("--include-logs")
    if args.include_thumbnails:
        cmd.append("--include-thumbnails")
    if args.include_e2e_traces:
        cmd.append("--include-e2e-traces")
    return cmd


def command_start(args: argparse.Namespace) -> dict[str, Any]:
    if not BACKUP_SCRIPT.is_file():
        raise SystemExit(f"Backup script not found: {BACKUP_SCRIPT}")

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
            "include_logs": bool(args.include_logs),
            "include_thumbnails": bool(args.include_thumbnails),
            "include_e2e_traces": bool(args.include_e2e_traces),
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
    cmd = ["bash", str(BACKUP_SCRIPT), "--output-dir", str(backup_root), "--dry-run"]
    if args.include_logs:
        cmd.append("--include-logs")
    if args.include_thumbnails:
        cmd.append("--include-thumbnails")
    if args.include_e2e_traces:
        cmd.append("--include-e2e-traces")

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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage local runtime backup jobs")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument("--output-dir")

    def add_options(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument("--include-logs", action="store_true")
        subparser.add_argument("--include-thumbnails", action="store_true")
        subparser.add_argument("--include-e2e-traces", action="store_true")

    start = subparsers.add_parser("start")
    add_common(start)
    add_options(start)
    start.add_argument("--name")

    status = subparsers.add_parser("status")
    add_common(status)
    status.add_argument("--job-id")
    status.add_argument("--log-lines", type=int, default=80)

    dry_run = subparsers.add_parser("dry-run")
    add_common(dry_run)
    add_options(dry_run)

    verify = subparsers.add_parser("verify")
    add_common(verify)
    verify.add_argument("--backup-dir")
    verify.add_argument("--timeout-seconds", type=int, default=1200)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.command == "start":
            payload = command_start(args)
        elif args.command == "status":
            payload = command_status(args)
        elif args.command == "dry-run":
            payload = command_dry_run(args)
        elif args.command == "verify":
            payload = command_verify(args)
        else:
            parser.error(f"Unsupported command: {args.command}")
    except subprocess.CalledProcessError as exc:
        payload = {
            "success": False,
            "error": str(exc),
            "stdout": exc.stdout,
            "stderr": exc.stderr,
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 1

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
