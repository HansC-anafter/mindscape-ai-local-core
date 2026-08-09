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
    build_config,
    build_plan,
    dir_size_bytes,
    list_wal_segments,
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

    verify_prune = subparsers.add_parser("verify-prune")
    add_policy_options(verify_prune)
    verify_prune.add_argument("--backup-dir")

    return parser


def verify_and_prune(args: argparse.Namespace) -> dict:
    """Verify the retained recovery chain before pruning obsolete snapshots/WAL."""

    config = build_config(args)
    primary_root = config["primary_root"]
    wal_root = config["wal_archive_root"]
    if args.backup_dir:
        protected = Path(args.backup_dir).expanduser().resolve()
    else:
        manifests = sorted(
            primary_root.glob("*/manifest.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if not manifests:
            raise SystemExit(f"No backup manifest found under {primary_root}")
        protected = manifests[0].parent.resolve()
    if not protected.joinpath("manifest.json").is_file():
        raise SystemExit(f"Backup manifest not found: {protected}")

    verification = verify_incremental_dir(protected)
    if not verification.get("success"):
        raise SystemExit(f"Backup verification failed: {protected}")

    before_segments = list_wal_segments(wal_root)
    before_bytes = dir_size_bytes(wal_root)
    pruned = prune_incremental(
        primary_root,
        config["retention_local_count"],
        protected,
        wal_root=wal_root,
    )
    after_segments = list_wal_segments(wal_root)
    after_bytes = dir_size_bytes(wal_root)
    return {
        "success": True,
        "verified_backup_dir": str(protected),
        "verification": verification,
        "retention_local_count": config["retention_local_count"],
        "wal_archive_dir": str(wal_root),
        "before": {
            "wal_segment_count": len(before_segments),
            "wal_archive_bytes": before_bytes,
        },
        "after": {
            "wal_segment_count": len(after_segments),
            "wal_archive_bytes": after_bytes,
        },
        "pruned": pruned,
    }


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "plan":
        payload = build_plan(args)
    elif args.command == "run":
        payload = run_policy(args)
    elif args.command == "verify":
        payload = verify_incremental_dir(Path(args.backup_dir), restore_drill=args.restore_drill)
    elif args.command == "verify-prune":
        payload = verify_and_prune(args)
    else:
        parser.error(f"Unsupported command: {args.command}")

    if args.command == "plan" and not args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
