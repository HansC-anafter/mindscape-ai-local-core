#!/usr/bin/env python3
"""
Bootstrap or update the optional ComfyUI talking-head host runtime.

This script is designed to be called via Device Node shell_execute.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Return the install command without mutating the host runtime.",
    )
    parser.add_argument(
        "--upgrade",
        action="store_true",
        help="Accepted for API parity; currently forwarded as metadata only.",
    )
    return parser.parse_args()


def _script_path() -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / "backend"
        / "app"
        / "capabilities"
        / "comfyui_runtime"
        / "scripts"
        / "bootstrap_local_comfyui_talking_head_runtime.sh"
    )


def _readiness_script_path() -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / "backend"
        / "app"
        / "capabilities"
        / "comfyui_runtime"
        / "scripts"
        / "check_local_comfyui_talking_head_readiness.sh"
    )


def _run_post_install_readiness(
    *,
    attempts: int = 5,
    delay_seconds: float = 2.0,
) -> tuple[dict, subprocess.CompletedProcess[str] | None]:
    command = ["bash", str(_readiness_script_path()), "--json"]
    last_result: subprocess.CompletedProcess[str] | None = None
    last_payload: dict = {}
    for attempt in range(attempts):
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        last_result = result
        try:
            last_payload = json.loads(result.stdout or "{}")
        except json.JSONDecodeError:
            last_payload = {}
        if result.returncode in {0, 2}:
            return last_payload, result
        if attempt < attempts - 1:
            time.sleep(delay_seconds)
    return last_payload, last_result


def main() -> int:
    args = parse_args()
    command = ["bash", str(_script_path()), "all"]

    if args.dry_run:
        print(
            json.dumps(
                {
                    "status": "dry_run",
                    "dry_run": True,
                    "restart_recommended": False,
                    "command": command,
                    "stdout": "",
                    "stderr": "",
                    "returncode": 0,
                    "upgrade": args.upgrade,
                }
            )
        )
        return 0

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=1800,
        check=False,
    )
    status = "installed" if result.returncode == 0 else "failed"
    if result.returncode == 2:
        status = "source_install_required"
    readiness: dict = {}
    readiness_result: subprocess.CompletedProcess[str] | None = None
    if result.returncode in {0, 2}:
        readiness, readiness_result = _run_post_install_readiness()
        if result.returncode == 0 and readiness and not bool(readiness.get("ready")):
            status = "installed_not_ready"

    restart_recommended = result.returncode == 0 and status == "installed"
    stdout_parts = [part for part in [result.stdout, readiness.get("summary_text", "")] if part]
    stderr_parts = [part for part in [result.stderr] if part]
    if readiness_result and readiness_result.returncode not in {0, 2} and readiness_result.stderr:
        stderr_parts.append(readiness_result.stderr)
    print(
        json.dumps(
            {
                "status": status,
                "dry_run": False,
                "restart_recommended": restart_recommended,
                "command": command,
                "stdout": "\n\n".join(stdout_parts),
                "stderr": "\n\n".join(stderr_parts),
                "returncode": result.returncode,
                "upgrade": args.upgrade,
                "readiness": readiness,
            }
        )
    )
    return int(result.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
