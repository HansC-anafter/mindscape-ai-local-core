#!/usr/bin/env python3
"""Facade for the bounded PostgreSQL SIGQUIT sender observer."""

from __future__ import annotations

import argparse
import json
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.maintenance.postgres_signal_observer_core import (  # noqa: E402
    EvidenceBudget,
    ObserverConfig,
    ObserverEvidenceStore,
    PostgresSignalObserver,
    SIGNAL_FILTER,
    canonical_observer_artifact_sha256,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--healthcheck", action="store_true")
    parser.add_argument("--validate-config", action="store_true")
    parser.add_argument("--print-artifact-sha256", action="store_true")
    parser.add_argument("--max-health-age-seconds", type=int, default=30)
    return parser


def _healthcheck(config: ObserverConfig, max_age_seconds: int) -> int:
    try:
        payload = ObserverEvidenceStore(config.evidence_root).read_health()
        updated = datetime.fromisoformat(
            str(payload["updated_at"]).replace("Z", "+00:00")
        )
        age = (datetime.now(timezone.utc) - updated).total_seconds()
        healthy = (
            payload.get("ready") is True
            and payload.get("state") == "ready"
            and payload.get("artifact_sha256") == config.artifact_sha256
            and payload.get("source_commit") == config.source_commit
            and payload.get("image_digest") == config.image_digest
            and payload.get("filter") == SIGNAL_FILTER
            and age <= max(5, int(max_age_seconds))
        )
    except Exception:
        healthy = False
        payload = {"ready": False, "state": "health_unavailable"}
    print(json.dumps(payload, sort_keys=True))
    return 0 if healthy else 2


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    config = ObserverConfig.from_environment()
    if args.print_artifact_sha256:
        print(canonical_observer_artifact_sha256(config.repo_root))
        return 0
    if args.healthcheck:
        return _healthcheck(config, args.max_health_age_seconds)
    if args.validate_config:
        config.validate()
        budget = EvidenceBudget()
        print(
            json.dumps(
                {
                    "valid": True,
                    "budget_sha256": budget.sha256(),
                    "artifact_sha256": config.artifact_sha256,
                },
                sort_keys=True,
            )
        )
        return 0

    observer = PostgresSignalObserver(config)
    signal.signal(signal.SIGTERM, lambda *_: observer.stop())
    signal.signal(signal.SIGINT, lambda *_: observer.stop())
    return observer.run()


if __name__ == "__main__":
    raise SystemExit(main())
