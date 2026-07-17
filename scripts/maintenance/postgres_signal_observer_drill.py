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
    DisposableDrillObserverConfig,
    canonical_observer_artifact_sha256,
    launch_disposable_drill_client,
    launch_disposable_drill_observer,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--print-client-spec", action="store_true")
    mode.add_argument("--launch-client", action="store_true")
    mode.add_argument("--print-observer-spec", action="store_true")
    mode.add_argument("--launch-observer", action="store_true")
    parser.add_argument("--journal-root", type=Path)
    parser.add_argument("--container-name", required=True)
    parser.add_argument("--network-name")
    parser.add_argument("--image-ref", required=True)
    parser.add_argument("--pgbouncer-host")
    parser.add_argument("--pgbouncer-container-name")
    parser.add_argument("--pgbouncer-port", type=int, default=6432)
    parser.add_argument("--database-user")
    parser.add_argument("--database-name")
    parser.add_argument("--source-commit")
    parser.add_argument("--sleep-seconds", type=int, default=120)
    return parser


def _required(value: object, option: str) -> object:
    if value is None or not str(value).strip():
        raise SystemExit(f"{option} is required for the selected mode")
    return value


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    artifact_sha256 = canonical_observer_artifact_sha256(REPO_ROOT)
    if args.print_observer_spec or args.launch_observer:
        if args.journal_root is None:
            raise SystemExit("--journal-root is required for observer modes")
        observer_config = DisposableDrillObserverConfig(
            container_name=args.container_name,
            pgbouncer_container_name=str(
                _required(args.pgbouncer_container_name, "--pgbouncer-container-name")
            ),
            image_ref=args.image_ref,
            journal_host_root=args.journal_root,
            repo_root=REPO_ROOT,
            artifact_sha256=artifact_sha256,
            source_commit=str(_required(args.source_commit, "--source-commit")),
        )
        if args.print_observer_spec:
            print(json.dumps(observer_config.redacted_spec(), sort_keys=True))
            return 0
        decision = require_runtime_database_mutation_allowed(
            "postgres_signal_observer_start",
            evidence={"artifact_sha256": artifact_sha256},
            journal_root=args.journal_root,
        )
        if decision.reason != "incident_diagnostic_permit":
            raise RuntimeError("incident_diagnostic_permit_required")
        receipt = launch_disposable_drill_observer(observer_config)
        receipt["artifact_sha256"] = artifact_sha256
        receipt["incident_id"] = decision.incident_id
        receipt["admission_reason"] = decision.reason
        print(json.dumps(receipt, sort_keys=True))
        return 0 if receipt.get("ready") is True else 2

    config = DisposableDrillClientConfig(
        container_name=args.container_name,
        network_name=str(_required(args.network_name, "--network-name")),
        image_ref=args.image_ref,
        pgbouncer_host=str(_required(args.pgbouncer_host, "--pgbouncer-host")),
        pgbouncer_port=args.pgbouncer_port,
        database_user=str(_required(args.database_user, "--database-user")),
        database_name=str(_required(args.database_name, "--database-name")),
        sleep_seconds=args.sleep_seconds,
    )
    if args.print_client_spec:
        print(json.dumps(config.redacted_spec(), sort_keys=True))
        return 0
    if args.journal_root is None:
        raise SystemExit("--journal-root is required with --launch-client")
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
