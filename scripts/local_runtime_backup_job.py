#!/usr/bin/env python3
"""Host-side job wrapper for local runtime backup scripts.

This wrapper is intentionally small: the backup implementation remains in the
policy and verification scripts. The wrapper starts long-running backups in the
background and records job state for the UI.
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
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "verify_local_runtime_backup.sh"
POLICY_SCRIPT = REPO_ROOT / "scripts" / "local_runtime_backup_policy.py"
INCREMENTAL_SCRIPT = REPO_ROOT / "scripts" / "local_runtime_incremental_backup.py"
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
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


load_repo_env()


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


GOOGLE_DRIVE_MY_DRIVE_NAMES = ("我的雲端硬碟", "My Drive")
GOOGLE_DRIVE_RECOMMENDED_MIRROR_SCOPES = [
    "postgres_chain",
    "runtime_metadata",
    "auth_state",
]


def google_drive_cloudstorage_root() -> Path:
    override = os.environ.get("GOOGLE_DRIVE_CLOUDSTORAGE_ROOT")
    if override:
        return Path(override).expanduser()
    return Path.home() / "Library" / "CloudStorage"


def google_drive_account_label(mount_path: Path) -> str:
    name = mount_path.name
    return name.removeprefix("GoogleDrive-") or name


def find_google_drive_mounts() -> list[dict[str, Any]]:
    cloud_root = google_drive_cloudstorage_root()
    mounts: list[dict[str, Any]] = []
    if not cloud_root.is_dir():
        return mounts

    for mount_path in sorted(cloud_root.glob("GoogleDrive-*")):
        if not mount_path.is_dir():
            continue
        my_drive_path = None
        for drive_name in GOOGLE_DRIVE_MY_DRIVE_NAMES:
            candidate = mount_path / drive_name
            if candidate.is_dir():
                my_drive_path = candidate
                break
        if my_drive_path is None:
            continue
        mindscape_root = my_drive_path / "Mindscape"
        mounts.append(
            {
                "account_label": google_drive_account_label(mount_path),
                "mount_path": str(mount_path),
                "my_drive_path": str(my_drive_path),
                "recommended_mirror_root": str(mindscape_root / "local-core-runtime-backups"),
                "recommended_resource_root": str(mindscape_root / "local-core-resource-collaboration"),
            }
        )
    return mounts


def command_google_drive_status(_args: argparse.Namespace) -> dict[str, Any]:
    mounts = find_google_drive_mounts()
    selected = mounts[0] if mounts else {}
    warnings: list[str] = []
    if not mounts:
        warnings.append("Google Drive CloudStorage mount was not found on this host.")
    return {
        "available": bool(mounts),
        "mounts": mounts,
        "account_label": selected.get("account_label", ""),
        "mount_path": selected.get("mount_path", ""),
        "my_drive_path": selected.get("my_drive_path", ""),
        "recommended_mirror_root": selected.get("recommended_mirror_root", ""),
        "recommended_resource_root": selected.get("recommended_resource_root", ""),
        "recommended_mirror_scopes": GOOGLE_DRIVE_RECOMMENDED_MIRROR_SCOPES,
        "warnings": warnings,
    }


def _path_inside_any(candidate: Path, roots: list[Path]) -> bool:
    expanded = candidate.expanduser()
    candidate_parts = expanded.parts
    for root in roots:
        root_parts = root.expanduser().parts
        if candidate_parts[: len(root_parts)] == root_parts:
            return True
    return False


def command_prepare_google_drive(args: argparse.Namespace) -> dict[str, Any]:
    status = command_google_drive_status(args)
    if not status["available"]:
        return {**status, "success": False, "prepared": False}

    my_drive_roots = [Path(str(item["my_drive_path"])) for item in status["mounts"]]
    mirror_root = Path(args.mirror_root or status["recommended_mirror_root"]).expanduser()
    resource_root = Path(args.resource_root or status["recommended_resource_root"]).expanduser()
    warnings = list(status.get("warnings") or [])

    for label, target in [("mirror_root", mirror_root), ("resource_root", resource_root)]:
        if not _path_inside_any(target, my_drive_roots):
            return {
                **status,
                "success": False,
                "prepared": False,
                "error": f"{label} must be inside the detected Google Drive My Drive mount.",
                "mirror_root": str(mirror_root),
                "resource_root": str(resource_root),
            }

    mirror_root.mkdir(parents=True, exist_ok=True)
    resource_root.mkdir(parents=True, exist_ok=True)
    for child in ["manifests", "incoming", "outgoing", "resource-index"]:
        (resource_root / child).mkdir(parents=True, exist_ok=True)

    policy = {
        "schema_version": 1,
        "purpose": "mindscape-local-core-google-drive-sync",
        "created_at": utc_now(),
        "mirror_root": str(mirror_root),
        "resource_root": str(resource_root),
        "recommended_mirror_scopes": GOOGLE_DRIVE_RECOMMENDED_MIRROR_SCOPES,
        "do_not_sync_live_roots": [
            "/Volumes/*",
            "live runtime databases",
            "model caches",
            "node_modules",
            "virtual environments",
            "temporary workspaces",
        ],
    }
    write_json(resource_root / ".mindscape-sync-policy.json", policy)
    readme = resource_root / "README.md"
    if not readme.exists():
        readme.write_text(
            "\n".join(
                [
                    "# Mindscape Local-Core Google Drive Collaboration",
                    "",
                    "Use this folder for small resource manifests, indexes, and exchange bundles.",
                    "Do not place live runtime databases, model caches, dependency folders, or full external drives here.",
                    "",
                    "Runtime backup archives belong in the sibling local-core-runtime-backups folder.",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

    return {
        **status,
        "success": True,
        "prepared": True,
        "mirror_root": str(mirror_root),
        "resource_root": str(resource_root),
        "policy_path": str(resource_root / ".mindscape-sync-policy.json"),
        "warnings": warnings,
    }


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


def profile_state_summary(backup_dir: Path) -> dict[str, Any] | None:
    report_path = backup_dir / "metadata" / "profile-state-report.json"
    if not report_path.is_file():
        return None
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"valid": False, "error": f"{type(exc).__name__}: {exc}"}

    profiles = report.get("profiles") or []
    invalid = [item for item in profiles if item and not item.get("valid")]
    return {
        "valid": not invalid,
        "profiles": len(profiles),
        "invalid_profiles": len(invalid),
        "invalid": invalid,
    }


def parse_backup_manifest(manifest_path: Path) -> dict[str, Any] | None:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    backup_dir = manifest_path.parent
    artifacts = manifest.get("artifacts") or []
    components = manifest.get("components") or {}
    total_bytes = (
        sum(int(item.get("bytes") or 0) for item in artifacts if isinstance(item, dict))
        if artifacts
        else int(manifest.get("total_bytes") or 0)
    )
    backup_name = str(manifest.get("backup_name") or backup_dir.name)
    return {
        "backup_name": backup_name,
        "created_at": manifest.get("created_at"),
        "path": str(backup_dir),
        "host_backup_dir": str(backup_dir),
        "schema_version": manifest.get("schema_version"),
        "mode": manifest.get("mode") or "db_dump_only",
        "git_commit": manifest.get("git_commit"),
        "options": manifest.get("options") or {},
        "artifact_count": len(artifacts) if artifacts else len(components),
        "total_bytes": total_bytes,
        "base_backup_id": (components.get("postgres") or {}).get("base_backup_id"),
        "file_snapshot_id": backup_name if components.get("files") else "",
        "profile_state": profile_state_summary(backup_dir),
        "manifest_mtime": manifest_path.stat().st_mtime,
    }


def latest_backup(backup_root: Path) -> dict[str, Any] | None:
    if not backup_root.is_dir():
        return None
    backups: list[dict[str, Any]] = []
    for manifest_path in backup_root.glob("*/manifest.json"):
        parsed = parse_backup_manifest(manifest_path)
        if parsed:
            backups.append(parsed)
    if not backups:
        return None

    def sort_key(item: dict[str, Any]) -> Any:
        created_at = item.get("created_at")
        if isinstance(created_at, str):
            try:
                return datetime.fromisoformat(created_at.replace("Z", "+00:00")).timestamp()
            except ValueError:
                pass
        return item.get("manifest_mtime") or 0

    latest = max(backups, key=sort_key)
    latest.pop("manifest_mtime", None)
    return latest


def command_latest_backup(args: argparse.Namespace) -> dict[str, Any]:
    backup_root = resolve_backup_root(args.output_dir)
    return {
        "backup_root": str(backup_root),
        "latest_backup": latest_backup(backup_root),
    }


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage local runtime backup jobs")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument("--output-dir")
        subparser.add_argument("--mirror-root")
        subparser.add_argument("--retention-local-count", type=int)
        subparser.add_argument("--retention-mirror-count", type=int)
        subparser.add_argument("--min-free-gb", type=float)
        subparser.add_argument("--require-mirror")
        subparser.add_argument("--base-interval-hours", type=int)
        subparser.add_argument("--mirror-scopes")

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

    latest = subparsers.add_parser("latest-backup")
    add_common(latest)

    dry_run = subparsers.add_parser("dry-run")
    add_common(dry_run)
    add_options(dry_run)

    plan = subparsers.add_parser("plan")
    add_common(plan)

    postgres_status = subparsers.add_parser("postgres-status")
    add_common(postgres_status)

    verify = subparsers.add_parser("verify")
    add_common(verify)
    verify.add_argument("--backup-dir")
    verify.add_argument("--timeout-seconds", type=int, default=1200)

    google_drive_status = subparsers.add_parser("google-drive-status")
    add_common(google_drive_status)

    prepare_google_drive = subparsers.add_parser("prepare-google-drive")
    prepare_google_drive.add_argument("--mirror-root")
    prepare_google_drive.add_argument("--resource-root")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.command == "start":
            payload = command_start(args)
        elif args.command == "status":
            payload = command_status(args)
        elif args.command == "latest-backup":
            payload = command_latest_backup(args)
        elif args.command == "dry-run":
            payload = command_dry_run(args)
        elif args.command == "plan":
            payload = command_plan(args)
        elif args.command == "postgres-status":
            payload = command_postgres_status(args)
        elif args.command == "verify":
            payload = command_verify(args)
        elif args.command == "google-drive-status":
            payload = command_google_drive_status(args)
        elif args.command == "prepare-google-drive":
            payload = command_prepare_google_drive(args)
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
