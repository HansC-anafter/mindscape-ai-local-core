#!/usr/bin/env python3
"""Facade for the bounded PostgreSQL SIGQUIT sender observer."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.maintenance.postgres_signal_observer_core.artifact import (  # noqa: E402
    canonical_observer_artifact_sha256,
)
from scripts.maintenance.postgres_signal_observer_core.evidence import (  # noqa: E402
    EvidenceBudget,
    ObserverEvidenceStore,
    utc_now,
)
from scripts.maintenance.postgres_signal_observer_core.tracefs import (  # noqa: E402
    SIGNAL_FILTER,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--healthcheck", action="store_true")
    parser.add_argument("--validate-config", action="store_true")
    parser.add_argument("--print-artifact-sha256", action="store_true")
    parser.add_argument("--correlate-target-pid", type=int)
    parser.add_argument("--max-health-age-seconds", type=int, default=30)
    return parser


def _required_environment(name: str) -> str:
    value = os.environ.get(name)
    if type(value) is not str or not value.strip():
        raise ValueError(f"{name.lower()}_required")
    return value.strip()


def _healthcheck(max_age_seconds: int) -> int:
    try:
        evidence_root = Path(
            _required_environment("POSTGRES_SIGNAL_OBSERVER_EVIDENCE_DIR")
        )
        artifact_sha256 = _required_environment(
            "POSTGRES_SIGNAL_OBSERVER_ARTIFACT_SHA256"
        )
        source_commit = _required_environment(
            "POSTGRES_SIGNAL_OBSERVER_SOURCE_COMMIT"
        )
        image_digest = _required_environment(
            "POSTGRES_SIGNAL_OBSERVER_IMAGE_DIGEST"
        )
        payload = ObserverEvidenceStore(evidence_root).read_health()
        updated = datetime.fromisoformat(
            str(payload["updated_at"]).replace("Z", "+00:00")
        )
        age = (datetime.now(timezone.utc) - updated).total_seconds()
        healthy = (
            payload.get("ready") is True
            and payload.get("state") == "ready"
            and payload.get("artifact_sha256") == artifact_sha256
            and payload.get("source_commit") == source_commit
            and payload.get("image_digest") == image_digest
            and payload.get("filter") == SIGNAL_FILTER
            and age <= max(5, int(max_age_seconds))
        )
    except Exception:
        healthy = False
        payload = {"ready": False, "state": "health_unavailable"}
    print(json.dumps(payload, sort_keys=True))
    return 0 if healthy else 2


def _write_startup_health() -> None:
    evidence_root = Path(
        _required_environment("POSTGRES_SIGNAL_OBSERVER_EVIDENCE_DIR")
    )
    ObserverEvidenceStore(evidence_root).write_health(
        {
            "ready": False,
            "state": "starting",
            "filter": SIGNAL_FILTER,
            "filter_sha256": hashlib.sha256(
                SIGNAL_FILTER.encode("utf-8")
            ).hexdigest(),
            "source_commit": _required_environment(
                "POSTGRES_SIGNAL_OBSERVER_SOURCE_COMMIT"
            ),
            "image_digest": _required_environment(
                "POSTGRES_SIGNAL_OBSERVER_IMAGE_DIGEST"
            ),
            "artifact_sha256": _required_environment(
                "POSTGRES_SIGNAL_OBSERVER_ARTIFACT_SHA256"
            ),
            "heartbeat_at": utc_now(),
            "startup_phase": "config_and_permit_validation",
        }
    )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.print_artifact_sha256:
        repo_root = Path(
            _required_environment("POSTGRES_SIGNAL_OBSERVER_REPO_ROOT")
        )
        print(canonical_observer_artifact_sha256(repo_root))
        return 0
    if args.healthcheck:
        return _healthcheck(args.max_health_age_seconds)
    if args.correlate_target_pid is not None:
        if not 0 < args.correlate_target_pid <= 4_194_304:
            raise SystemExit("observer_correlation_target_pid_invalid")
        from scripts.maintenance.postgres_signal_observer_core.pgbouncer import (
            PgBouncerCorrelationClient,
        )

        correlation = PgBouncerCorrelationClient(
            _required_environment("PGBOUNCER_ADMIN_URL"),
            expected_application_name=(
                os.getenv(
                    "POSTGRES_SIGNAL_OBSERVER_EXPECTED_APPLICATION_NAME",
                    "",
                ).strip()
                or None
            ),
        ).correlate(args.correlate_target_pid)
        print(json.dumps(correlation, sort_keys=True, separators=(",", ":")))
        return 0

    if not args.validate_config:
        _write_startup_health()
    from scripts.maintenance.postgres_signal_observer_core.service import (
        ObserverConfig,
        PostgresSignalObserver,
    )

    config = ObserverConfig.from_environment()
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
