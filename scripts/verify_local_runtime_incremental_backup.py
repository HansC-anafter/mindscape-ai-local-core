#!/usr/bin/env python3
"""Verify incremental local runtime backup manifests."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from local_runtime_incremental_backup import verify_incremental_dir  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify an incremental local runtime backup")
    parser.add_argument("backup_dir")
    parser.add_argument("--restore-drill", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    payload = verify_incremental_dir(Path(args.backup_dir).expanduser(), restore_drill=args.restore_drill)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
