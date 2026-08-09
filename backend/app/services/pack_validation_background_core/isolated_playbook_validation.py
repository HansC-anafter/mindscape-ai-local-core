"""Run installed-playbook validation outside the serving process module cache."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from backend.app.services.install_result import InstallResult


_RESULT_PREFIX = "__MINDSCAPE_PACK_VALIDATION_RESULT__="


def _validation_timeout_seconds(manifest: dict[str, Any]) -> int:
    playbook_count = len(manifest.get("playbooks") or [])
    return min(600, max(90, playbook_count * 8))


def _validation_environment(local_core_root: Path) -> dict[str, str]:
    repository_root = Path(__file__).resolve().parents[4]
    python_paths = [
        str(repository_root),
        str(repository_root / "backend"),
        str(local_core_root),
        str(local_core_root / "backend"),
    ]
    existing_pythonpath = os.environ.get("PYTHONPATH", "").strip()
    if existing_pythonpath:
        python_paths.append(existing_pythonpath)
    return {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(python_paths),
    }


def validate_installed_playbooks_isolated(
    *,
    pack_id: str,
    manifest: dict[str, Any],
    local_core_root: Path,
    capabilities_dir: Path,
    specs_dir: Path,
) -> InstallResult:
    """Validate fresh installed files without consuming stale runtime modules."""

    request = {
        "pack_id": pack_id,
        "manifest": manifest,
        "local_core_root": str(local_core_root),
        "capabilities_dir": str(capabilities_dir),
        "specs_dir": str(specs_dir),
    }
    result = InstallResult(capability_code=pack_id)
    try:
        process = subprocess.run(
            [sys.executable, "-m", __name__],
            cwd=str(local_core_root),
            env=_validation_environment(local_core_root),
            input=json.dumps(request),
            capture_output=True,
            text=True,
            timeout=_validation_timeout_seconds(manifest),
        )
    except subprocess.TimeoutExpired:
        result.add_error(f"Isolated playbook validation timed out for {pack_id}")
        return result
    except Exception as exc:
        result.add_error(f"Isolated playbook validation failed to start: {exc}")
        return result

    payload_line = next(
        (
            line[len(_RESULT_PREFIX) :]
            for line in reversed(process.stdout.splitlines())
            if line.startswith(_RESULT_PREFIX)
        ),
        None,
    )
    if payload_line is None:
        detail = (process.stderr or process.stdout or "no worker output").strip()
        result.add_error(
            "Isolated playbook validation returned no receipt: "
            f"{detail[-1000:]}"
        )
        return result

    try:
        worker_result = InstallResult.from_dict(json.loads(payload_line))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        result.add_error(f"Isolated playbook validation returned an invalid receipt: {exc}")
        return result

    if process.returncode != 0 and not worker_result.errors:
        worker_result.add_error(
            f"Isolated playbook validation exited with status {process.returncode}"
        )
    return worker_result


def _run_worker(request: dict[str, Any]) -> InstallResult:
    from backend.app.services.playbook_installer import PlaybookInstaller
    from backend.app.services.post_install_modules.playbook_validator import (
        PlaybookValidator,
    )

    local_core_root = Path(request["local_core_root"])
    capabilities_dir = Path(request["capabilities_dir"])
    specs_dir = Path(request["specs_dir"])
    pack_id = str(request["pack_id"])
    manifest = request["manifest"]

    installer = PlaybookInstaller(
        local_core_root=local_core_root,
        capabilities_dir=capabilities_dir,
        specs_dir=specs_dir,
    )
    validator = PlaybookValidator(
        local_core_root=local_core_root,
        capabilities_dir=capabilities_dir,
        validate_tools_direct_call_func=installer._validate_tools_direct_call,
    )
    result = InstallResult(capability_code=pack_id)
    validator.validate_installed_playbooks(pack_id, manifest, result)
    return result


def _main() -> int:
    try:
        request = json.load(sys.stdin)
        result = _run_worker(request)
        exit_code = 0
    except Exception as exc:
        pack_id = None
        try:
            pack_id = request.get("pack_id")
        except Exception:
            pass
        result = InstallResult(capability_code=pack_id)
        result.add_error(f"Isolated playbook validation worker crashed: {exc}")
        exit_code = 1
    print(f"{_RESULT_PREFIX}{json.dumps(result.to_dict(), sort_keys=True)}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(_main())
