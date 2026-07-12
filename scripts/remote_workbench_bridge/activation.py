"""Source identity and launchd activation checks for the bridge supervisor."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import plistlib
import re
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


LABEL = "ai.mindscape.remote-workbench-bridge"
BRIDGE_PATH = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
PLIST_KEYS = {
    "EnvironmentVariables",
    "KeepAlive",
    "Label",
    "ProgramArguments",
    "RunAtLoad",
    "StandardErrorPath",
    "StandardOutPath",
    "ThrottleInterval",
    "WorkingDirectory",
}
ENVIRONMENT_KEYS = {
    "DOCKER_HOST",
    "HOME",
    "PATH",
    "PYTHONDONTWRITEBYTECODE",
    "PYTHONUNBUFFERED",
    "REMOTE_WORKBENCH_BRIDGE_BUILD_ID",
    "REMOTE_WORKBENCH_BRIDGE_STATE_DIR",
    "REMOTE_WORKBENCH_PROJECT_ROOT",
}
SOURCE_PATHS = (
    "scripts/config/ai.mindscape.remote-workbench-bridge.plist",
    "scripts/install-remote-workbench-bridge-macos.sh",
    "scripts/remote_workbench_bridge/__init__.py",
    "scripts/remote_workbench_bridge/activation.py",
    "scripts/remote_workbench_bridge/probes.py",
    "scripts/remote_workbench_bridge/settings.py",
    "scripts/remote_workbench_bridge/state_store.py",
    "scripts/remote_workbench_bridge/supervisor.py",
    "scripts/remote_workbench_bridge_monitor.py",
    "scripts/remote_workbench_remote_ingress_lock.py",
    "scripts/start_remote_workbench_tunnel.sh",
)
KNOWN_STATES = {
    "degraded_origin",
    "degraded_remote",
    "maintenance",
    "ready",
    "recovering_tunnel",
    "waiting_docker",
}


class ActivationError(RuntimeError):
    """Raised when installed or live launchd state is not current."""


def source_build_id(project_root: Path) -> str:
    """Return a deterministic digest over the complete bridge source seam."""

    digest = hashlib.sha256()
    for relative in SOURCE_PATHS:
        path = project_root / relative
        try:
            body = path.read_bytes()
        except OSError as error:
            raise ActivationError(f"activation_source_unavailable:{relative}") from error
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(body)
        digest.update(b"\0")
    return digest.hexdigest()


def _load_plist(path: Path) -> dict[str, Any]:
    try:
        metadata = path.lstat()
    except OSError as error:
        raise ActivationError("installed_plist_unavailable") from error
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o600
    ):
        raise ActivationError("installed_plist_not_regular")
    try:
        payload = plistlib.loads(path.read_bytes())
    except (OSError, plistlib.InvalidFileException) as error:
        raise ActivationError("installed_plist_malformed") from error
    if not isinstance(payload, dict):
        raise ActivationError("installed_plist_malformed")
    return payload


def _scalar(launchd_output: str, key: str) -> str:
    match = re.search(rf"^\s*{re.escape(key)} = (.+?)\s*$", launchd_output, re.MULTILINE)
    if match is None:
        raise ActivationError(f"launchd_{key.replace(' ', '_')}_missing")
    return match.group(1)


def _arguments(launchd_output: str) -> list[str]:
    lines = launchd_output.splitlines()
    for index, line in enumerate(lines):
        if line.strip() != "arguments = {":
            continue
        result = []
        for candidate in lines[index + 1 :]:
            value = candidate.strip()
            if value == "}":
                return result
            if value:
                result.append(value)
        break
    raise ActivationError("launchd_arguments_missing")


def _read_status(path: Path) -> dict[str, Any]:
    try:
        metadata = path.lstat()
        raw = path.read_bytes()
    except OSError as error:
        raise ActivationError("supervisor_status_unavailable") from error
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or len(raw) > 65_536
    ):
        raise ActivationError("supervisor_status_not_secure")
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ActivationError("supervisor_status_malformed") from error
    if not isinstance(payload, dict):
        raise ActivationError("supervisor_status_malformed")
    return payload


def verify_activation(
    *,
    project_root: Path,
    python_bin: Path,
    installed_plist: Path,
    launchd_output: str,
    status_path: Path,
    now: datetime | None = None,
    stale_seconds: float = 60.0,
) -> dict[str, Any]:
    """Verify current source, installed plist, live argv, PID, and fresh status."""

    project_root = project_root.resolve()
    if not python_bin.is_absolute():
        raise ActivationError("python_bin_not_absolute")
    python_bin = Path(os.path.abspath(python_bin))
    monitor_path = project_root / "scripts/remote_workbench_bridge_monitor.py"
    current_build = source_build_id(project_root)
    expected_argv = [str(python_bin), str(monitor_path)]
    plist = _load_plist(installed_plist)
    environment = plist.get("EnvironmentVariables")
    home = environment.get("HOME") if isinstance(environment, dict) else None
    if (
        set(plist) != PLIST_KEYS
        or installed_plist.name != f"{LABEL}.plist"
        or plist.get("Label") != LABEL
        or plist.get("ProgramArguments") != expected_argv
        or plist.get("WorkingDirectory") != str(project_root)
        or plist.get("RunAtLoad") is not True
        or plist.get("KeepAlive") != {"SuccessfulExit": False}
        or plist.get("ThrottleInterval") != 10
        or plist.get("StandardOutPath")
        != str(project_root / "logs/remote-workbench-bridge.log")
        or plist.get("StandardErrorPath")
        != str(project_root / "logs/remote-workbench-bridge.error.log")
        or not isinstance(environment, dict)
        or set(environment) != ENVIRONMENT_KEYS
        or not isinstance(home, str)
        or not Path(home).is_absolute()
        or environment.get("PATH") != BRIDGE_PATH
        or environment.get("PYTHONDONTWRITEBYTECODE") != "1"
        or environment.get("PYTHONUNBUFFERED") != "1"
        or environment.get("DOCKER_HOST") != f"unix://{home}/.docker/run/docker.sock"
        or environment.get("REMOTE_WORKBENCH_BRIDGE_BUILD_ID") != current_build
        or environment.get("REMOTE_WORKBENCH_PROJECT_ROOT") != str(project_root)
        or environment.get("REMOTE_WORKBENCH_BRIDGE_STATE_DIR")
        != str(status_path.parent)
    ):
        raise ActivationError("installed_plist_contract_mismatch")
    if _scalar(launchd_output, "state") != "running":
        raise ActivationError("launchd_state_mismatch")
    if Path(_scalar(launchd_output, "program")) != python_bin:
        raise ActivationError("launchd_program_mismatch")
    if _arguments(launchd_output) != expected_argv:
        raise ActivationError("launchd_arguments_mismatch")
    if re.search(
        rf"^\s*REMOTE_WORKBENCH_BRIDGE_BUILD_ID => {current_build}\s*$",
        launchd_output,
        re.MULTILINE,
    ) is None:
        raise ActivationError("launchd_build_id_mismatch")
    try:
        pid = int(_scalar(launchd_output, "pid"))
    except ValueError as error:
        raise ActivationError("launchd_pid_malformed") from error
    if pid <= 0:
        raise ActivationError("launchd_pid_malformed")
    status = _read_status(status_path)
    live_build = status.get("supervisor_build_id")
    if live_build != current_build or status.get("supervisor_pid") != pid:
        raise ActivationError("supervisor_status_identity_mismatch")
    checked_at = status.get("checked_at")
    try:
        checked = datetime.fromisoformat(str(checked_at).replace("Z", "+00:00"))
        reference = now or datetime.now(timezone.utc)
        age = (reference.astimezone(timezone.utc) - checked).total_seconds()
    except (TypeError, ValueError) as error:
        raise ActivationError("supervisor_status_timestamp_malformed") from error
    if not 0 <= age <= stale_seconds:
        raise ActivationError("supervisor_status_stale")
    state = status.get("state")
    maintenance = status.get("maintenance")
    if state not in KNOWN_STATES or not isinstance(maintenance, dict):
        raise ActivationError("supervisor_status_state_malformed")
    maintenance_enabled = maintenance.get("enabled") is True
    if (state == "maintenance") != maintenance_enabled:
        raise ActivationError("supervisor_status_maintenance_mismatch")
    return {
        "activation_conformant": True,
        "argv": expected_argv,
        "checked_at": checked_at,
        "current_build_id": current_build,
        "launchd_running": True,
        "live_build_id": live_build,
        "maintenance": maintenance_enabled,
        "pid": pid,
        "state": state,
        "status_fresh": True,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    actions = parser.add_subparsers(dest="action", required=True)
    build = actions.add_parser("build-id")
    build.add_argument("--project-root", type=Path, required=True)
    verify = actions.add_parser("verify")
    verify.add_argument("--project-root", type=Path, required=True)
    verify.add_argument("--python-bin", type=Path, required=True)
    verify.add_argument("--installed-plist", type=Path, required=True)
    verify.add_argument("--launchd-output", type=Path, required=True)
    verify.add_argument("--status-path", type=Path, required=True)
    verify.add_argument("--stale-seconds", type=float, default=60.0)
    verify.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        if args.action == "build-id":
            print(source_build_id(args.project_root.resolve()))
            return 0
        launchd_output = args.launchd_output.read_text(encoding="utf-8")
        payload = verify_activation(
            project_root=args.project_root,
            python_bin=args.python_bin,
            installed_plist=args.installed_plist,
            launchd_output=launchd_output,
            status_path=args.status_path,
            stale_seconds=args.stale_seconds,
        )
    except (ActivationError, OSError) as error:
        print(str(error), file=os.sys.stderr)
        return 1
    if args.json:
        print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
