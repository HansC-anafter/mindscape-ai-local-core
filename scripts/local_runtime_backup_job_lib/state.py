#!/usr/bin/env python3
"""Backup job JSON state helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .common import utc_now


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
