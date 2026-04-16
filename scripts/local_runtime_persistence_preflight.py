#!/usr/bin/env python3
"""
Read-only preflight for the local runtime persistence migration.

What it does:
- inspects live backend/runner mounts and envs
- snapshots current drain-gate state from Postgres + Redis
- probes the live LAF runtime readiness API
- evaluates source/target host paths and free-space surface
- optionally writes a timestamped manifest + backup plan under workspace data/

What it does NOT do:
- no container recreate
- no rsync/copy
- no backup execution
- no data mutation outside an optional local manifest directory
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import textwrap
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BACKUP_ROOT = PROJECT_ROOT / "data" / "backups" / "local-runtime-persistence"
DEFAULT_RUNTIME_ROOT_HOST = Path(
    "/Volumes/OWC Ultra 4T/mindscape-ai-local-core-runtime/data/secrets"
)
DEFAULT_TARGETS = {
    "workspaces": DEFAULT_RUNTIME_ROOT_HOST / "workspaces",
    "storage": DEFAULT_RUNTIME_ROOT_HOST / "storage",
    "models": DEFAULT_RUNTIME_ROOT_HOST / "models",
}
DEFAULT_SOURCES = {
    "secrets": DEFAULT_RUNTIME_ROOT_HOST,
    "storage": Path.home() / ".mindscape" / "storage",
    "models": Path.home() / ".mindscape" / "models",
}
DEFAULT_CONTAINERS = {
    "backend": "mindscape-ai-local-core-backend",
    "runner_default": "mindscape-ai-local-core-runner-default",
    "runner_browser": "mindscape-ai-local-core-runner-browser",
    "runner_vision": "mindscape-ai-local-core-runner-vision",
    "postgres": "mindscape-ai-local-core-postgres",
    "redis": "mindscape-ai-local-core-redis",
}
EXPECTED_CONTAINER_ENVS = {
    "WORKSPACE_STORAGE_ROOT": "/root/.mindscape/workspaces",
    "MINDSCAPE_MODEL_ROOT": "/root/.mindscape/models",
    "LOCAL_STORAGE_PATH": "/root/.mindscape/storage/layer_asset_forge",
}
EXPECTED_MOUNT_TARGETS = {
    "/root/.mindscape": str(DEFAULT_RUNTIME_ROOT_HOST),
    "/root/.mindscape/storage": str(DEFAULT_TARGETS["storage"]),
    "/root/.mindscape/models": str(DEFAULT_TARGETS["models"]),
}
LAF_RUNTIME_PLAN_URL = "http://127.0.0.1:8200/api/v1/capabilities/layer_asset_forge/runtime/plan"


@dataclass
class CommandResult:
    argv: list[str]
    returncode: int
    stdout: str
    stderr: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 when cutover blockers are present.",
    )
    parser.add_argument(
        "--write-manifest",
        action="store_true",
        help="Write a timestamped preflight manifest and backup-plan script under data/backups.",
    )
    parser.add_argument(
        "--backup-root",
        default=str(DEFAULT_BACKUP_ROOT),
        help="Workspace-local directory for preflight manifests.",
    )
    parser.add_argument(
        "--backend-url",
        default=LAF_RUNTIME_PLAN_URL,
        help="Live LAF runtime-plan endpoint to probe.",
    )
    parser.add_argument(
        "--backend-timeout-seconds",
        type=float,
        default=20.0,
        help="Timeout for the live LAF runtime-plan probe.",
    )
    return parser.parse_args()


def run(argv: Iterable[str], *, timeout: int = 30) -> CommandResult:
    command = [str(item) for item in argv]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return CommandResult(
        argv=command,
        returncode=completed.returncode,
        stdout=(completed.stdout or "").strip(),
        stderr=(completed.stderr or "").strip(),
    )


def docker_inspect(container: str, template: str) -> Any:
    result = run(["docker", "inspect", container, "--format", template])
    if result.returncode != 0:
        raise RuntimeError(result.stderr or f"docker inspect failed for {container}")
    return json.loads(result.stdout or "null")


def parse_env(env_list: list[str] | None) -> dict[str, str]:
    env_map: dict[str, str] = {}
    for item in env_list or []:
        if "=" not in str(item):
            continue
        key, value = str(item).split("=", 1)
        env_map[key] = value
    return env_map


def nearest_existing_parent(path: Path) -> Path:
    current = Path(path)
    while not current.exists() and current != current.parent:
        current = current.parent
    return current


def disk_usage_for(path: Path) -> dict[str, Any]:
    probe_root = nearest_existing_parent(path)
    usage = shutil.disk_usage(probe_root)
    return {
        "probe_root": str(probe_root),
        "free_bytes": usage.free,
        "total_bytes": usage.total,
        "used_bytes": usage.used,
    }


def host_path_snapshot(label: str, path: Path) -> dict[str, Any]:
    resolved = nearest_existing_parent(path) if not path.exists() else path
    snapshot = {
        "label": label,
        "path": str(path),
        "exists": path.exists(),
        "is_dir": path.is_dir(),
        "disk_usage": disk_usage_for(path),
    }
    try:
        snapshot["realpath"] = str(path.expanduser().resolve())
    except Exception:
        snapshot["realpath"] = str(resolved)
    return snapshot


def collect_container_state(container: str) -> dict[str, Any]:
    mounts = docker_inspect(container, "{{json .Mounts}}")
    envs = parse_env(docker_inspect(container, "{{json .Config.Env}}"))
    mount_map = {
        str(mount.get("Destination")): str(mount.get("Source"))
        for mount in mounts or []
        if isinstance(mount, dict)
    }
    return {
        "container": container,
        "env": envs,
        "mounts": mount_map,
    }


def postgres_query(sql: str, *, user: str, database: str) -> CommandResult:
    return run(
        [
            "docker",
            "exec",
            DEFAULT_CONTAINERS["postgres"],
            "psql",
            "-U",
            user,
            "-d",
            database,
            "-At",
            "-F",
            "|",
            "-c",
            sql,
        ],
        timeout=30,
    )


def redis_zcard(key: str) -> CommandResult:
    return run(
        [
            "docker",
            "exec",
            DEFAULT_CONTAINERS["redis"],
            "redis-cli",
            "ZCARD",
            key,
        ],
        timeout=15,
    )


def collect_drain_gate(backend_env: dict[str, str]) -> dict[str, Any]:
    pg_user = backend_env.get("POSTGRES_CORE_USER", "mindscape")
    pg_db = backend_env.get("POSTGRES_CORE_DB", "mindscape_core")

    task_counts_result = postgres_query(
        "SELECT status, COUNT(*) FROM tasks GROUP BY status ORDER BY status;",
        user=pg_user,
        database=pg_db,
    )
    heartbeat_result = postgres_query(
        textwrap.dedent(
            """
            SELECT runner_id, profile_code, inflight, heartbeat_at
            FROM runner_heartbeats
            WHERE heartbeat_at >= NOW() - interval '2 minutes'
            ORDER BY heartbeat_at DESC;
            """
        ).strip(),
        user=pg_user,
        database=pg_db,
    )

    task_counts: dict[str, int] = {}
    if task_counts_result.returncode == 0:
        for line in task_counts_result.stdout.splitlines():
            parts = [part.strip() for part in line.split("|")]
            if len(parts) != 2:
                continue
            try:
                task_counts[parts[0]] = int(parts[1])
            except ValueError:
                continue

    active_heartbeats: list[dict[str, Any]] = []
    if heartbeat_result.returncode == 0:
        for line in heartbeat_result.stdout.splitlines():
            parts = [part.strip() for part in line.split("|")]
            if len(parts) != 4:
                continue
            try:
                inflight = int(parts[2])
            except ValueError:
                inflight = parts[2]
            active_heartbeats.append(
                {
                    "runner_id": parts[0],
                    "profile_code": parts[1],
                    "inflight": inflight,
                    "heartbeat_at": parts[3],
                }
            )

    processing_counts = {}
    for profile in ("default_local", "browser_local", "vision_local"):
        key = f"mindscape:queue:processing:{profile}"
        result = redis_zcard(key)
        try:
            processing_counts[profile] = int(result.stdout.strip()) if result.returncode == 0 else None
        except ValueError:
            processing_counts[profile] = None

    running_tasks = task_counts.get("running", 0)
    inflight_nonzero = [item for item in active_heartbeats if int(item.get("inflight") or 0) > 0]
    processing_nonzero = {
        profile: count for profile, count in processing_counts.items() if isinstance(count, int) and count > 0
    }
    cutover_ready = running_tasks == 0 and not inflight_nonzero and not processing_nonzero

    return {
        "task_counts": task_counts,
        "active_heartbeats": active_heartbeats,
        "processing_counts": processing_counts,
        "cutover_ready": cutover_ready,
        "raw_commands": {
            "task_counts": task_counts_result.__dict__,
            "active_heartbeats": heartbeat_result.__dict__,
        },
    }


def probe_laf_runtime_plan(url: str, *, timeout_seconds: float) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8")
        payload = json.loads(body)
        return {
            "ok": True,
            "url": url,
            "status": payload.get("status"),
            "readiness_state": payload.get("readiness_state"),
            "runtime_root": payload.get("runtime_root"),
            "model_root": payload.get("model_root"),
            "bridge_state": payload.get("bridge_state"),
            "install_target": payload.get("install_target"),
            "isolation_mode": payload.get("isolation_mode"),
        }
    except urllib.error.URLError as exc:
        return {"ok": False, "url": url, "error": str(exc)}
    except Exception as exc:
        return {"ok": False, "url": url, "error": str(exc)}


def build_backup_plan(timestamp: str, backup_root: Path) -> dict[str, Any]:
    manifest_dir = backup_root / timestamp
    postgres_backup = manifest_dir / "postgres" / "mindscape_core_pre_migration.sql"
    fs_backup_root = manifest_dir / "runtime-fs"
    commands = [
        f"mkdir -p {manifest_dir / 'postgres'} {fs_backup_root}",
        f"docker compose exec -T postgres pg_dump -U mindscape -d mindscape_core > {postgres_backup}",
        f'rsync -aH "{DEFAULT_SOURCES["secrets"]}/" "{fs_backup_root / "secrets_pre_migration"}/"',
        f'rsync -aH "{DEFAULT_SOURCES["storage"]}/" "{fs_backup_root / "storage_pre_migration"}/"',
        f'rsync -aH "{DEFAULT_SOURCES["models"]}/" "{fs_backup_root / "models_pre_migration"}/"',
    ]
    return {
        "backup_root": str(backup_root),
        "manifest_dir": str(manifest_dir),
        "commands": commands,
        "paths": {
            "postgres_backup": str(postgres_backup),
            "filesystem_backup_root": str(fs_backup_root),
        },
    }


def collect_report(args: argparse.Namespace) -> dict[str, Any]:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backend_state = collect_container_state(DEFAULT_CONTAINERS["backend"])
    runner_states = {
        name: collect_container_state(container)
        for name, container in DEFAULT_CONTAINERS.items()
        if name.startswith("runner_")
    }

    env_checks = []
    for lane_name, state in {"backend": backend_state, **runner_states}.items():
        for key, expected in EXPECTED_CONTAINER_ENVS.items():
            actual = state["env"].get(key)
            env_checks.append(
                {
                    "lane": lane_name,
                    "key": key,
                    "expected": expected,
                    "actual": actual,
                    "ok": actual == expected,
                }
            )

    mount_checks = []
    for lane_name, state in {"backend": backend_state, **runner_states}.items():
        for destination, expected_source in EXPECTED_MOUNT_TARGETS.items():
            actual = state["mounts"].get(destination)
            mount_checks.append(
                {
                    "lane": lane_name,
                    "destination": destination,
                    "expected_source": expected_source,
                    "actual_source": actual,
                    "ok": actual == expected_source,
                }
            )

    path_snapshot = {
        "sources": {
            label: host_path_snapshot(label, path)
            for label, path in DEFAULT_SOURCES.items()
        },
        "targets": {
            label: host_path_snapshot(label, path)
            for label, path in DEFAULT_TARGETS.items()
        },
    }

    drain_gate = collect_drain_gate(backend_state["env"])
    runtime_probe = probe_laf_runtime_plan(
        args.backend_url,
        timeout_seconds=args.backend_timeout_seconds,
    )
    backup_plan = build_backup_plan(timestamp, Path(args.backup_root).expanduser())

    blockers: list[str] = []
    actions: list[str] = []

    for label, snapshot in path_snapshot["sources"].items():
        if not snapshot["exists"]:
            blockers.append(f"source path missing: {label} -> {snapshot['path']}")

    for label, snapshot in path_snapshot["targets"].items():
        if not snapshot["exists"]:
            actions.append(f"create target directory before cutover: {label} -> {snapshot['path']}")

    for check in env_checks:
        if not check["ok"]:
            blockers.append(
                f"{check['lane']} env drift: {check['key']} expected {check['expected']} got {check['actual']}"
            )

    for check in mount_checks:
        if not check["ok"]:
            blockers.append(
                f"{check['lane']} mount drift: {check['destination']} expected {check['expected_source']} got {check['actual_source']}"
            )

    if not drain_gate["cutover_ready"]:
        blockers.append("drain gate not ready: running/inflight/processing is non-zero")

    if not runtime_probe.get("ok"):
        blockers.append(f"LAF runtime probe failed: {runtime_probe.get('error')}")

    target_storage_usage = path_snapshot["targets"]["storage"]["disk_usage"]
    target_models_usage = path_snapshot["targets"]["models"]["disk_usage"]
    if int(target_storage_usage["free_bytes"]) <= 0:
        blockers.append("target storage root reports zero free bytes")
    if int(target_models_usage["free_bytes"]) <= 0:
        blockers.append("target models root reports zero free bytes")

    return {
        "generated_at": timestamp,
        "backend": backend_state,
        "runners": runner_states,
        "env_checks": env_checks,
        "mount_checks": mount_checks,
        "path_snapshot": path_snapshot,
        "drain_gate": drain_gate,
        "laf_runtime_probe": runtime_probe,
        "backup_plan": backup_plan,
        "actions": sorted(set(actions)),
        "blockers": blockers,
        "cutover_ready": not blockers,
    }


def write_manifest(report: dict[str, Any], backup_root: Path) -> Path:
    manifest_dir = Path(report["backup_plan"]["manifest_dir"])
    manifest_dir.mkdir(parents=True, exist_ok=True)
    json_path = manifest_dir / "preflight.json"
    md_path = manifest_dir / "preflight.md"
    sh_path = manifest_dir / "backup-plan.sh"

    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "# Local Runtime Persistence Preflight",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Cutover ready: `{str(report['cutover_ready']).lower()}`",
        "",
        "## Blockers",
    ]
    if report["blockers"]:
        lines.extend([f"- {item}" for item in report["blockers"]])
    else:
        lines.append("- None")
    lines.extend(["", "## Actions"])
    if report["actions"]:
        lines.extend([f"- {item}" for item in report["actions"]])
    else:
        lines.append("- None")
    lines.extend(["", "## Backup Plan"])
    lines.extend([f"- `{command}`" for command in report["backup_plan"]["commands"]])
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    sh_lines = ["#!/usr/bin/env bash", "set -euo pipefail", ""]
    sh_lines.extend(report["backup_plan"]["commands"])
    sh_path.write_text("\n".join(sh_lines) + "\n", encoding="utf-8")
    sh_path.chmod(0o755)
    return manifest_dir


def print_human(report: dict[str, Any]) -> None:
    print("=" * 72)
    print("Local Runtime Persistence Preflight")
    print("=" * 72)
    print(f"Generated at : {report['generated_at']}")
    print(f"Cutover ready: {str(report['cutover_ready']).lower()}")
    print()
    print("Blockers:")
    if report["blockers"]:
        for item in report["blockers"]:
            print(f"  - {item}")
    else:
        print("  - none")
    print()
    print("Actions:")
    if report["actions"]:
        for item in report["actions"]:
            print(f"  - {item}")
    else:
        print("  - none")
    print()
    print("Drain Gate Snapshot:")
    print(f"  - task counts: {report['drain_gate']['task_counts']}")
    print(f"  - processing: {report['drain_gate']['processing_counts']}")
    print(f"  - active heartbeats: {len(report['drain_gate']['active_heartbeats'])}")
    print()
    print("LAF Runtime Probe:")
    probe = report["laf_runtime_probe"]
    if probe.get("ok"):
        print(
            "  - "
            f"readiness={probe.get('readiness_state')} "
            f"bridge={probe.get('bridge_state')} "
            f"runtime_root={probe.get('runtime_root')} "
            f"model_root={probe.get('model_root')}"
        )
    else:
        print(f"  - error: {probe.get('error')}")
    print()
    print("Backup Plan Root:")
    print(f"  - {report['backup_plan']['manifest_dir']}")


def main() -> int:
    args = parse_args()
    report = collect_report(args)
    manifest_dir: Path | None = None
    if args.write_manifest:
        manifest_dir = write_manifest(report, Path(args.backup_root).expanduser())
        report["manifest_dir"] = str(manifest_dir)

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_human(report)
        if manifest_dir is not None:
            print()
            print(f"Manifest written to: {manifest_dir}")

    if args.strict and not report["cutover_ready"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
