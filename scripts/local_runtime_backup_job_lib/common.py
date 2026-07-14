#!/usr/bin/env python3
"""Shared constants and host helpers for local runtime backup jobs."""

from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
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
    return resolve_data_host_dir().parent / "backups" / "local-runtime"
