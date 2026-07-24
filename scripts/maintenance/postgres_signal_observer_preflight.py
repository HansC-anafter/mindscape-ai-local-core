#!/usr/bin/env python3
"""Facade for the target-scoped PostgreSQL signal observer preflight."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.maintenance.postgres_signal_observer_preflight_core import (  # noqa: E402
    ObserverPreflightConfig,
    collect_observer_preflight,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("qualification", "terminal"), required=True)
    parser.add_argument("--artifact-sha256", required=True)
    parser.add_argument("--expected-runner-capacity", type=int, required=True)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--journal-root", type=Path)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--pgbouncer-sample-interval-seconds", type=float, default=5.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    config = ObserverPreflightConfig(
        repo_root=REPO_ROOT,
        journal_root=args.journal_root
        or Path(
            os.getenv(
                "RUNTIME_DATABASE_INCIDENT_DIR",
                "/app/data/runtime-database-incidents",
            )
        ),
        output_json=args.output_json,
        artifact_sha256=args.artifact_sha256,
        expected_runner_capacity=args.expected_runner_capacity,
        owner=args.owner,
        phase=args.phase,
        pgbouncer_sample_interval_seconds=args.pgbouncer_sample_interval_seconds,
    )
    receipt = collect_observer_preflight(config)
    config.output_json.parent.mkdir(parents=True, exist_ok=True)
    config.output_json.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(receipt, sort_keys=True))
    return 0 if receipt["gate_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
