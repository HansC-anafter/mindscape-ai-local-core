#!/usr/bin/env python3
"""
Run the ComfyUI talking-head readiness check via the host-side script and emit JSON.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


def _script_path() -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / "backend"
        / "app"
        / "capabilities"
        / "comfyui_runtime"
        / "scripts"
        / "check_local_comfyui_talking_head_readiness.sh"
    )


def _run_readiness_check() -> tuple[dict, subprocess.CompletedProcess[str]]:
    command = ["bash", str(_script_path()), "--json"]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    readiness: dict = {}
    try:
        readiness = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        readiness = {}
    return readiness, result


def main() -> int:
    readiness, result = _run_readiness_check()
    status = "synced" if result.returncode == 0 else "failed"
    if result.returncode == 2:
        status = "not_ready"
    stdout = str(readiness.get("summary_text") or result.stdout or "")
    print(
        json.dumps(
            {
                "status": status,
                "dry_run": False,
                "restart_recommended": False,
                "command": ["bash", str(_script_path())],
                "stdout": stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
                "readiness": readiness,
            }
        )
    )
    return int(result.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
