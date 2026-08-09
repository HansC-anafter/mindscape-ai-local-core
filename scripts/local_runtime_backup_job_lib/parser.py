#!/usr/bin/env python3
"""Argument parser and CLI dispatch for local runtime backup jobs."""

from __future__ import annotations

import argparse
import json
import subprocess

from .backup_info import command_latest_backup
from .commands import (
    command_dry_run,
    command_plan,
    command_postgres_status,
    command_start,
    command_status,
    command_verify,
    command_verify_prune,
)
from .google_drive import command_google_drive_status, command_prepare_google_drive


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage local runtime backup jobs")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument("--output-dir")
        subparser.add_argument("--mirror-root")
        subparser.add_argument("--retention-local-count", type=int)
        subparser.add_argument("--retention-mirror-count", type=int)
        subparser.add_argument("--min-free-gb", type=float)
        subparser.add_argument("--require-mirror")
        subparser.add_argument("--base-interval-hours", type=int)
        subparser.add_argument("--mirror-scopes")

    def add_options(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument("--include-logs", action="store_true")
        subparser.add_argument("--include-thumbnails", action="store_true")
        subparser.add_argument("--include-e2e-traces", action="store_true")

    start = subparsers.add_parser("start")
    add_common(start)
    add_options(start)
    start.add_argument("--name")

    status = subparsers.add_parser("status")
    add_common(status)
    status.add_argument("--job-id")
    status.add_argument("--log-lines", type=int, default=80)

    latest = subparsers.add_parser("latest-backup")
    add_common(latest)

    dry_run = subparsers.add_parser("dry-run")
    add_common(dry_run)
    add_options(dry_run)

    plan = subparsers.add_parser("plan")
    add_common(plan)

    postgres_status = subparsers.add_parser("postgres-status")
    add_common(postgres_status)

    verify = subparsers.add_parser("verify")
    add_common(verify)
    verify.add_argument("--backup-dir")
    verify.add_argument("--timeout-seconds", type=int, default=1200)

    verify_prune = subparsers.add_parser("verify-prune")
    add_common(verify_prune)
    verify_prune.add_argument("--backup-dir")
    verify_prune.add_argument("--timeout-seconds", type=int, default=1200)

    google_drive_status = subparsers.add_parser("google-drive-status")
    add_common(google_drive_status)

    prepare_google_drive = subparsers.add_parser("prepare-google-drive")
    prepare_google_drive.add_argument("--mirror-root")
    prepare_google_drive.add_argument("--resource-root")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.command == "start":
            payload = command_start(args)
        elif args.command == "status":
            payload = command_status(args)
        elif args.command == "latest-backup":
            payload = command_latest_backup(args)
        elif args.command == "dry-run":
            payload = command_dry_run(args)
        elif args.command == "plan":
            payload = command_plan(args)
        elif args.command == "postgres-status":
            payload = command_postgres_status(args)
        elif args.command == "verify":
            payload = command_verify(args)
        elif args.command == "verify-prune":
            payload = command_verify_prune(args)
        elif args.command == "google-drive-status":
            payload = command_google_drive_status(args)
        elif args.command == "prepare-google-drive":
            payload = command_prepare_google_drive(args)
        else:
            parser.error(f"Unsupported command: {args.command}")
    except subprocess.CalledProcessError as exc:
        payload = {
            "success": False,
            "error": str(exc),
            "stdout": exc.stdout,
            "stderr": exc.stderr,
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 1

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0
