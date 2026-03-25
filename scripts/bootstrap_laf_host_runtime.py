#!/usr/bin/env python3
"""
Bootstrap or update the optional Layer Asset Forge host runtime.

This script is designed to be called via Device Node shell_execute:
  python3 scripts/bootstrap_laf_host_runtime.py --package ... [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import shutil
from pathlib import Path

from laf_host_runtime_common import (
    build_install_command,
    build_manual_only_actions,
    build_source_install_actions,
    check_requirement_availability,
    default_runtime_root,
    detect_python_version,
    detect_torch_backend,
    execute_source_install_action,
    normalize_requirements,
    preferred_host_python,
    required_min_python_for_source_specs,
    state_file,
    venv_dir,
    venv_python,
    write_runtime_state,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--runtime-root",
        default=str(default_runtime_root()),
        help="Host-side runtime root directory.",
    )
    parser.add_argument(
        "--package",
        action="append",
        default=[],
        help="Python requirement to install inside the host runtime venv.",
    )
    parser.add_argument(
        "--source-spec",
        action="append",
        default=[],
        help="Source-based runtime spec to install inside the host runtime venv.",
    )
    parser.add_argument(
        "--manual-spec",
        action="append",
        default=[],
        help="Manual-only runtime spec to report but not auto-install.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Return the install plan without mutating the host runtime.",
    )
    parser.add_argument(
        "--upgrade",
        action="store_true",
        help="Pass --upgrade to pip install.",
    )
    return parser.parse_args()


def _build_payload(
    *,
    runtime_root: Path,
    requested_packages: list[str],
    requested_source_specs: list[str],
    requested_manual_specs: list[str],
    dry_run: bool,
    upgrade: bool,
) -> dict:
    python_executable = venv_python(runtime_root)
    all_requirements = [
        *requested_packages,
        *requested_source_specs,
        *requested_manual_specs,
    ]
    requirement_status = check_requirement_availability(python_executable, all_requirements)
    missing_packages = [
        requirement for requirement, available in requirement_status.items() if not available
        if requirement in requested_packages
    ]
    missing_source_specs = [
        requirement for requirement, available in requirement_status.items() if not available
        if requirement in requested_source_specs
    ]
    missing_manual_specs = [
        requirement for requirement, available in requirement_status.items() if not available
        if requirement in requested_manual_specs
    ]
    source_install_actions = build_source_install_actions(
        runtime_root,
        missing_source_specs or requested_source_specs,
        upgrade=upgrade,
    )
    manual_only_actions = build_manual_only_actions(
        missing_manual_specs or requested_manual_specs
    )
    return {
        "runtime_root": str(runtime_root),
        "venv_path": str(venv_dir(runtime_root)),
        "python_executable": str(python_executable),
        "bootstrap_python": preferred_host_python(),
        "venv_python_version": ".".join(map(str, detect_python_version(python_executable) or ())),
        "state_file": str(state_file(runtime_root)),
        "requested_packages": requested_packages,
        "requested_source_specs": requested_source_specs,
        "requested_manual_specs": requested_manual_specs,
        "requirement_status": requirement_status,
        "missing_packages": missing_packages,
        "missing_source_specs": missing_source_specs,
        "missing_manual_specs": missing_manual_specs,
        "command_preview": build_install_command(
            runtime_root,
            missing_packages or requested_packages,
            upgrade=upgrade,
        ),
        "source_install_actions": source_install_actions,
        "manual_only_actions": manual_only_actions,
        "dry_run": dry_run,
        "upgrade": upgrade,
    }


def main() -> int:
    args = parse_args()
    runtime_root = Path(args.runtime_root).expanduser()
    requested_packages = normalize_requirements(args.package)
    requested_source_specs = normalize_requirements(args.source_spec)
    requested_manual_specs = normalize_requirements(args.manual_spec)

    payload = _build_payload(
        runtime_root=runtime_root,
        requested_packages=requested_packages,
        requested_source_specs=requested_source_specs,
        requested_manual_specs=requested_manual_specs,
        dry_run=args.dry_run,
        upgrade=args.upgrade,
    )

    if not payload["missing_packages"] and not payload["missing_source_specs"]:
        payload["status"] = "already_ready"
        payload["returncode"] = 0
        payload["stdout"] = ""
        payload["stderr"] = ""
        payload.update(detect_torch_backend(venv_python(runtime_root)))
        write_runtime_state(runtime_root, payload)
        print(json.dumps(payload))
        return 0

    if args.dry_run:
        payload["status"] = "dry_run"
        payload["returncode"] = 0
        payload["stdout"] = ""
        payload["stderr"] = ""
        print(json.dumps(payload))
        return 0

    runtime_root.mkdir(parents=True, exist_ok=True)
    current_venv_version = detect_python_version(venv_python(runtime_root))
    required_min_python = required_min_python_for_source_specs(requested_source_specs)
    should_recreate_venv = (
        venv_dir(runtime_root).exists()
        and required_min_python is not None
        and current_venv_version is not None
        and current_venv_version < required_min_python
    )
    recreate_reason = ""
    if should_recreate_venv:
        recreate_reason = (
            f"Existing venv python {current_venv_version[0]}.{current_venv_version[1]} "
            f"is below required {required_min_python[0]}.{required_min_python[1]}"
        )
        shutil.rmtree(venv_dir(runtime_root), ignore_errors=True)

    if not venv_dir(runtime_root).exists():
        bootstrap_python = preferred_host_python()
        create_venv = subprocess.run(
            [bootstrap_python, "-m", "venv", str(venv_dir(runtime_root))],
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
        if create_venv.returncode != 0:
            payload["command"] = [bootstrap_python, "-m", "venv", str(venv_dir(runtime_root))]
            payload["command_sequence"] = [payload["command"]]
            payload["stdout"] = create_venv.stdout
            payload["stderr"] = create_venv.stderr
            payload["returncode"] = create_venv.returncode
            payload["status"] = "failed"
            if recreate_reason:
                payload["recreated_venv"] = True
                payload["venv_recreate_reason"] = recreate_reason
            print(json.dumps(payload))
            return create_venv.returncode

        payload = _build_payload(
            runtime_root=runtime_root,
            requested_packages=requested_packages,
            requested_source_specs=requested_source_specs,
            requested_manual_specs=requested_manual_specs,
            dry_run=False,
            upgrade=args.upgrade,
        )

    executed_commands: list[list[str]] = []
    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []
    returncode = 0

    if payload["missing_packages"]:
        command = build_install_command(
            runtime_root,
            payload["missing_packages"],
            upgrade=args.upgrade,
        )
        executed_commands.append(command)
        process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=3600,
            check=False,
        )
        stdout_chunks.append(process.stdout)
        stderr_chunks.append(process.stderr)
        returncode = process.returncode

    if returncode == 0:
        for action in payload["source_install_actions"]:
            result = execute_source_install_action(
                action,
                timeout_seconds=3600,
            )
            executed_commands.extend(
                [
                    list(command)
                    for command in (result.get("command_sequence") or [])
                    if isinstance(command, list) and command
                ]
            )
            stdout_chunks.append(str(result.get("stdout") or ""))
            stderr_chunks.append(str(result.get("stderr") or ""))
            returncode = int(result.get("returncode") or 0)
            if returncode != 0:
                break

    payload = _build_payload(
        runtime_root=runtime_root,
        requested_packages=requested_packages,
        requested_source_specs=requested_source_specs,
        requested_manual_specs=requested_manual_specs,
        dry_run=False,
        upgrade=args.upgrade,
    )
    payload["command"] = executed_commands[0] if executed_commands else []
    payload["command_sequence"] = executed_commands
    payload["stdout"] = "\n".join(chunk for chunk in stdout_chunks if chunk)
    payload["stderr"] = "\n".join(chunk for chunk in stderr_chunks if chunk)
    payload["returncode"] = returncode
    payload["status"] = "installed" if returncode == 0 else "failed"
    if recreate_reason:
        payload["recreated_venv"] = True
        payload["venv_recreate_reason"] = recreate_reason
    payload.update(detect_torch_backend(venv_python(runtime_root)))
    if returncode == 0:
        write_runtime_state(runtime_root, payload)
    print(json.dumps(payload))
    return 0 if returncode == 0 else returncode


if __name__ == "__main__":
    raise SystemExit(main())
