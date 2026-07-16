#!/usr/bin/env python3
"""Only CLI entrypoint for isolated PostgreSQL recovery drills."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.postgres_recovery_drill_core.commands import (  # noqa: E402
    preflight,
    rebuild_standby,
    status,
    switchback,
    switchover,
)
from scripts.postgres_recovery_drill_core.policy import (  # noqa: E402
    DrillScope,
    validate_drill_scope,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["status", "preflight", "switchover", "rebuild-standby", "switchback"])
    parser.add_argument("--project", required=True)
    parser.add_argument("--compose-file", type=Path, default=REPO_ROOT / "docker-compose.yml")
    parser.add_argument("--receipt-dir", type=Path, required=True)
    parser.add_argument("--operator", default="")
    parser.add_argument("--fence-proof", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    scope = validate_drill_scope(
        DrillScope(args.project, args.compose_file, args.receipt_dir)
    )
    if args.command == "status":
        result = status(scope)
    elif args.command == "preflight":
        result = preflight(scope)
    elif args.command == "switchover":
        result = switchover(
            scope,
            operator=args.operator,
            fence_proof=args.fence_proof,
        )
    elif args.command == "rebuild-standby":
        result = rebuild_standby(scope)
    else:
        result = switchback(
            scope,
            operator=args.operator,
            fence_proof=args.fence_proof,
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
