#!/usr/bin/env python3
"""Compatibility CLI for the incremental local runtime backup policy."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from local_runtime_incremental_backup import (  # noqa: E402
    BYTES_PER_GB,
    build_plan,
    prune_incremental,
    run_policy,
    verify_incremental_dir,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage the local runtime incremental backup policy")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_policy_options(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument("--output-dir")
        subparser.add_argument("--mirror-root")
        subparser.add_argument("--retention-local-count", type=int)
        subparser.add_argument("--retention-mirror-count", type=int)
        subparser.add_argument("--min-free-gb", type=float)
        subparser.add_argument("--require-mirror")
        subparser.add_argument("--base-interval-hours", type=int)
        subparser.add_argument("--mirror-scopes")
        subparser.add_argument(
            "--postgres-only",
            action="store_true",
            help="Use the explicit local-only PostgreSQL base/WAL recovery-chain scope.",
        )

    plan = subparsers.add_parser("plan")
    add_policy_options(plan)
    plan.add_argument("--json", action="store_true")

    run = subparsers.add_parser("run")
    add_policy_options(run)
    run.add_argument("--name")
    run.add_argument("--timeout-seconds", type=int, default=7200)

    verify = subparsers.add_parser("verify")
    verify.add_argument("backup_dir")
    verify.add_argument("--restore-drill", action="store_true")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "plan":
        payload = build_plan(args)
    elif args.command == "run":
        payload = run_policy(args)
    elif args.command == "verify":
        payload = verify_incremental_dir(Path(args.backup_dir), restore_drill=args.restore_drill)
    else:
        parser.error(f"Unsupported command: {args.command}")

    if args.command == "plan" and not args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
