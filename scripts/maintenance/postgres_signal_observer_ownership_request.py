#!/usr/bin/env python3
"""Materialize an exact qualification-bound live observer ownership request."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.maintenance.postgres_signal_observer_ownership_grant import (  # noqa: E402
    _write_exclusive_json,
)
from scripts.maintenance.postgres_signal_observer_preflight_core import (  # noqa: E402
    materialize_ownership_request,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qualification-receipt", type=Path, required=True)
    parser.add_argument("--exact-operation", required=True)
    parser.add_argument("--issued-at", required=True)
    parser.add_argument("--expires-at", required=True)
    parser.add_argument("--requested-owner", required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        request = materialize_ownership_request(
            args.qualification_receipt,
            exact_operation=args.exact_operation,
            issued_at=args.issued_at,
            expires_at=args.expires_at,
            requested_owner=args.requested_owner,
        )
        _write_exclusive_json(args.output_json, request)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(request, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
