#!/usr/bin/env python3
"""CLI facade for Local Core Docker Compose topology validation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from compose_topology.runner import validate_repo


DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[2]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(DEFAULT_REPO_ROOT))
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    report = validate_repo(Path(args.repo_root).resolve())
    if not args.quiet:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
