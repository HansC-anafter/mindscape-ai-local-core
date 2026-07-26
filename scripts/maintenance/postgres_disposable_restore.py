#!/usr/bin/env python3
"""Only CLI entrypoint for verified disposable PostgreSQL restores."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.postgres_disposable_restore_core.commands import (  # noqa: E402
    cleanup,
    preflight,
    run_restore,
    status,
)
from scripts.postgres_disposable_restore_core.policy import (  # noqa: E402
    RestoreScope,
    validate_restore_scope,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["status", "preflight", "run", "cleanup"])
    parser.add_argument("--project", required=True)
    parser.add_argument("--compose-file", type=Path, default=REPO_ROOT / "docker-compose.yml")
    parser.add_argument("--backup-dir", type=Path, required=True)
    parser.add_argument("--receipt-dir", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--timeout-seconds", type=int, default=3600)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = validate_restore_scope(
        RestoreScope(
            project=args.project,
            compose_file=args.compose_file,
            backup_dir=args.backup_dir,
            receipt_dir=args.receipt_dir,
            data_dir=args.data_dir,
        ),
        allow_existing_data=args.command == "cleanup",
    )
    if args.command == "status":
        result = status(source)
    elif args.command == "preflight":
        result = preflight(source)
    elif args.command == "run":
        result = run_restore(source, timeout_seconds=args.timeout_seconds)
    else:
        result = cleanup(source)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
