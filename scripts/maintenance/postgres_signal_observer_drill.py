#!/usr/bin/env python3
"""Facade for the permit-gated disposable signal-observer drill client."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.services.runtime_database_incident_gate import (  # noqa: E402
    require_runtime_database_mutation_allowed,
)
from scripts.maintenance.postgres_signal_observer_core import (  # noqa: E402
    DisposableDrillClientConfig,
    canonical_observer_artifact_sha256,
    launch_disposable_drill_client,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--print-client-spec", action="store_true")
    mode.add_argument("--launch-client", action="store_true")
    parser.add_argument("--journal-root", type=Path)
    parser.add_argument("--container-name", required=True)
    parser.add_argument("--network-name", required=True)
    parser.add_argument("--image-ref", required=True)
    parser.add_argument("--pgbouncer-host", required=True)
    parser.add_argument("--pgbouncer-port", type=int, default=6432)
    parser.add_argument("--database-user", required=True)
    parser.add_argument("--database-name", required=True)
    parser.add_argument("--sleep-seconds", type=int, default=120)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    config = DisposableDrillClientConfig(
        container_name=args.container_name,
        network_name=args.network_name,
        image_ref=args.image_ref,
        pgbouncer_host=args.pgbouncer_host,
        pgbouncer_port=args.pgbouncer_port,
        database_user=args.database_user,
        database_name=args.database_name,
        sleep_seconds=args.sleep_seconds,
    )
    if args.print_client_spec:
        print(json.dumps(config.redacted_spec(), sort_keys=True))
        return 0
    if args.journal_root is None:
        raise SystemExit("--journal-root is required with --launch-client")
    artifact_sha256 = canonical_observer_artifact_sha256(REPO_ROOT)
    decision = require_runtime_database_mutation_allowed(
        "postgres_signal_observer_start",
        evidence={"artifact_sha256": artifact_sha256},
        journal_root=args.journal_root,
    )
    if decision.reason != "incident_diagnostic_permit":
        raise RuntimeError("incident_diagnostic_permit_required")
    receipt = launch_disposable_drill_client(config)
    receipt["artifact_sha256"] = artifact_sha256
    receipt["incident_id"] = decision.incident_id
    receipt["admission_reason"] = decision.reason
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
