#!/usr/bin/env python3
"""
Check readiness of the optional Layer Asset Forge host runtime.

The script prints a single JSON object so it can be called through Device Node's
shell_execute tool and consumed by backend services.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from laf_host_runtime_common import (
    check_requirement_availability,
    default_runtime_root,
    detect_torch_backend,
    normalize_requirements,
    preferred_host_python,
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
        help="Python requirement to probe inside the host runtime venv.",
    )
    parser.add_argument(
        "--source-spec",
        action="append",
        default=[],
        help="Source-based runtime spec to probe inside the host runtime venv.",
    )
    parser.add_argument(
        "--manual-spec",
        action="append",
        default=[],
        help="Manual-only runtime spec to probe inside the host runtime venv.",
    )
    parser.add_argument(
        "--write-state",
        action="store_true",
        help="Persist the readiness payload to runtime_state.json.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    runtime_root = Path(args.runtime_root).expanduser()
    requirements = normalize_requirements(
        [*args.package, *args.source_spec, *args.manual_spec]
    )
    python_executable = venv_python(runtime_root)

    requirement_status = check_requirement_availability(python_executable, requirements)
    missing_packages = [
        requirement for requirement, available in requirement_status.items() if not available
    ]

    venv_exists = venv_dir(runtime_root).exists()
    if requirements and not missing_packages and python_executable.exists():
        readiness_state = "ready"
    elif venv_exists or python_executable.exists():
        readiness_state = "partial"
    else:
        readiness_state = "blocked"

    payload = {
        "status": "ok",
        "readiness_state": readiness_state,
        "runtime_root": str(runtime_root),
        "venv_path": str(venv_dir(runtime_root)),
        "python_executable": str(python_executable),
        "bootstrap_python": preferred_host_python(),
        "venv_exists": venv_exists,
        "python_exists": python_executable.exists(),
        "requested_packages": requirements,
        "requirement_status": requirement_status,
        "missing_packages": missing_packages,
        "requested_source_specs": normalize_requirements(args.source_spec),
        "requested_manual_specs": normalize_requirements(args.manual_spec),
    }
    payload.update(detect_torch_backend(python_executable))
    payload["state_file"] = str(state_file(runtime_root))
    if args.write_state:
        write_runtime_state(runtime_root, payload)
    print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
