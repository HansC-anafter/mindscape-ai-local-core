#!/usr/bin/env python3
"""Compatibility facade for local runtime backup job commands."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from local_runtime_backup_job_lib import backup_info as _backup_info
from local_runtime_backup_job_lib import commands as _commands
from local_runtime_backup_job_lib import common as _common
from local_runtime_backup_job_lib import google_drive as _google_drive
from local_runtime_backup_job_lib import parser as _parser
from local_runtime_backup_job_lib import state as _state

REPO_ROOT = Path(__file__).resolve().parents[1]
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "verify_local_runtime_backup.sh"
POLICY_SCRIPT = REPO_ROOT / "scripts" / "local_runtime_backup_policy.py"
INCREMENTAL_SCRIPT = REPO_ROOT / "scripts" / "local_runtime_incremental_backup.py"
GOOGLE_DRIVE_MY_DRIVE_NAMES = _google_drive.GOOGLE_DRIVE_MY_DRIVE_NAMES
GOOGLE_DRIVE_RECOMMENDED_MIRROR_SCOPES = _google_drive.GOOGLE_DRIVE_RECOMMENDED_MIRROR_SCOPES


def _sync_dependency_overrides() -> None:
    _common.REPO_ROOT = globals()["REPO_ROOT"]
    _common.VERIFY_SCRIPT = globals()["VERIFY_SCRIPT"]
    _common.POLICY_SCRIPT = globals()["POLICY_SCRIPT"]
    _common.INCREMENTAL_SCRIPT = globals()["INCREMENTAL_SCRIPT"]

    _commands.REPO_ROOT = globals()["REPO_ROOT"]
    _commands.VERIFY_SCRIPT = globals()["VERIFY_SCRIPT"]
    _commands.POLICY_SCRIPT = globals()["POLICY_SCRIPT"]
    _commands.INCREMENTAL_SCRIPT = globals()["INCREMENTAL_SCRIPT"]
    _commands.resolve_backup_root = globals()["resolve_backup_root"]
    _commands.run_text = globals()["run_text"]
    _commands.utc_now = globals()["utc_now"]
    _commands.latest_backup = globals()["latest_backup"]
    _commands.job_path = globals()["job_path"]
    _commands.job_root = globals()["job_root"]
    _commands.latest_job = globals()["latest_job"]
    _commands.read_json = globals()["read_json"]
    _commands.refresh_job = globals()["refresh_job"]
    _commands.tail_log = globals()["tail_log"]
    _commands.write_json = globals()["write_json"]

    _state.utc_now = globals()["utc_now"]
    _backup_info.resolve_backup_root = globals()["resolve_backup_root"]
    _google_drive.utc_now = globals()["utc_now"]
    _google_drive.write_json = globals()["write_json"]
    _google_drive.GOOGLE_DRIVE_MY_DRIVE_NAMES = globals()["GOOGLE_DRIVE_MY_DRIVE_NAMES"]
    _google_drive.GOOGLE_DRIVE_RECOMMENDED_MIRROR_SCOPES = globals()[
        "GOOGLE_DRIVE_RECOMMENDED_MIRROR_SCOPES"
    ]

    _parser.command_start = command_start
    _parser.command_status = command_status
    _parser.command_latest_backup = command_latest_backup
    _parser.command_dry_run = command_dry_run
    _parser.command_plan = command_plan
    _parser.command_postgres_status = command_postgres_status
    _parser.command_verify = command_verify
    _parser.command_google_drive_status = command_google_drive_status
    _parser.command_prepare_google_drive = command_prepare_google_drive


def load_repo_env() -> None:
    _sync_dependency_overrides()
    return _common.load_repo_env()


def utc_now() -> str:
    return _common.utc_now()


def run_text(cmd: list[str], timeout: int = 30) -> str:
    _sync_dependency_overrides()
    return _common.run_text(cmd, timeout=timeout)


def resolve_data_host_dir() -> Path:
    _sync_dependency_overrides()
    return _common.resolve_data_host_dir()


def resolve_backup_root(output_dir: str | None) -> Path:
    _sync_dependency_overrides()
    return _common.resolve_backup_root(output_dir)


def google_drive_cloudstorage_root() -> Path:
    _sync_dependency_overrides()
    return _google_drive.google_drive_cloudstorage_root()


def google_drive_account_label(mount_path: Path) -> str:
    return _google_drive.google_drive_account_label(mount_path)


def find_google_drive_mounts() -> list[dict[str, Any]]:
    _sync_dependency_overrides()
    return _google_drive.find_google_drive_mounts()


def command_google_drive_status(args: argparse.Namespace) -> dict[str, Any]:
    _sync_dependency_overrides()
    return _google_drive.command_google_drive_status(args)


def _path_inside_any(candidate: Path, roots: list[Path]) -> bool:
    return _google_drive._path_inside_any(candidate, roots)


def command_prepare_google_drive(args: argparse.Namespace) -> dict[str, Any]:
    _sync_dependency_overrides()
    return _google_drive.command_prepare_google_drive(args)


def job_root(backup_root: Path) -> Path:
    return _state.job_root(backup_root)


def job_path(backup_root: Path, job_id: str) -> Path:
    return _state.job_path(backup_root, job_id)


def write_json(path: Path, data: dict[str, Any]) -> None:
    return _state.write_json(path, data)


def read_json(path: Path) -> dict[str, Any]:
    return _state.read_json(path)


def pid_running(pid: int | None) -> bool:
    return _state.pid_running(pid)


def refresh_job(job: dict[str, Any]) -> dict[str, Any]:
    _sync_dependency_overrides()
    return _state.refresh_job(job)


def latest_job(backup_root: Path) -> dict[str, Any] | None:
    _sync_dependency_overrides()
    return _state.latest_job(backup_root)


def tail_log(path: str | None, lines: int) -> list[str]:
    return _state.tail_log(path, lines)


def add_policy_flags(cmd: list[str], args: argparse.Namespace) -> list[str]:
    return _commands.add_policy_flags(cmd, args)


def build_backup_command(args: argparse.Namespace, backup_root: Path, backup_name: str) -> list[str]:
    _sync_dependency_overrides()
    return _commands.build_backup_command(args, backup_root, backup_name)


def command_start(args: argparse.Namespace) -> dict[str, Any]:
    _sync_dependency_overrides()
    return _commands.command_start(args)


def profile_state_summary(backup_dir: Path) -> dict[str, Any] | None:
    return _backup_info.profile_state_summary(backup_dir)


def parse_backup_manifest(manifest_path: Path) -> dict[str, Any] | None:
    return _backup_info.parse_backup_manifest(manifest_path)


def latest_backup(backup_root: Path) -> dict[str, Any] | None:
    return _backup_info.latest_backup(backup_root)


def command_latest_backup(args: argparse.Namespace) -> dict[str, Any]:
    _sync_dependency_overrides()
    return _backup_info.command_latest_backup(args)


def command_status(args: argparse.Namespace) -> dict[str, Any]:
    _sync_dependency_overrides()
    return _commands.command_status(args)


def command_dry_run(args: argparse.Namespace) -> dict[str, Any]:
    _sync_dependency_overrides()
    return _commands.command_dry_run(args)


def command_plan(args: argparse.Namespace) -> dict[str, Any]:
    _sync_dependency_overrides()
    return _commands.command_plan(args)


def command_postgres_status(args: argparse.Namespace) -> dict[str, Any]:
    _sync_dependency_overrides()
    return _commands.command_postgres_status(args)


def command_verify(args: argparse.Namespace) -> dict[str, Any]:
    _sync_dependency_overrides()
    return _commands.command_verify(args)


def build_parser() -> argparse.ArgumentParser:
    _sync_dependency_overrides()
    return _parser.build_parser()


def main() -> int:
    _sync_dependency_overrides()
    return _parser.main()


if __name__ == "__main__":
    raise SystemExit(main())
