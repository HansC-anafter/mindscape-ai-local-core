#!/usr/bin/env python3
"""Generate a PostgreSQL HA and read-replica readiness report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = Path(__file__).resolve().parents[1]
for _path in (REPO_ROOT, BACKEND_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from app.database.ha_readiness import build_ha_readiness_report  # noqa: E402


def _is_zero(value: Any) -> bool:
    return value == 0


def _check_report(report: dict[str, Any], *, use_readonly_probe: bool) -> list[str]:
    errors: list[str] = []
    primary = dict(report.get("primary") or {})
    pgbouncer = dict(report.get("pgbouncer") or {})
    replica = dict(report.get("replica") or {})

    if not primary.get("available"):
        errors.append("primary_unavailable")
    if primary.get("postgres_in_recovery") is not False:
        errors.append("primary_in_recovery_or_unknown")
    if str(primary.get("transaction_read_only") or "").lower() != "off":
        errors.append("primary_transaction_read_only")
    if int(primary.get("app_idle_in_transaction_count") or 0) > 0:
        errors.append("app_idle_in_transaction_present")

    if not pgbouncer.get("available"):
        errors.append("pgbouncer_unavailable")
    if not pgbouncer.get("core_database_present"):
        errors.append("pgbouncer_core_database_missing")
    if not pgbouncer.get("vector_database_present"):
        errors.append("pgbouncer_vector_database_missing")
    if not _is_zero(pgbouncer.get("core_waiting")):
        errors.append("pgbouncer_core_waiting")
    if not _is_zero(pgbouncer.get("vector_waiting")):
        errors.append("pgbouncer_vector_waiting")

    if use_readonly_probe:
        if not replica.get("available"):
            errors.append("replica_readonly_probe_unavailable")
        if not pgbouncer.get("readonly_core_database_present"):
            errors.append("pgbouncer_readonly_core_database_missing")
        if not pgbouncer.get("readonly_vector_database_present"):
            errors.append("pgbouncer_readonly_vector_database_missing")
        if not _is_zero(pgbouncer.get("readonly_core_waiting")):
            errors.append("pgbouncer_readonly_core_waiting")
        if not _is_zero(pgbouncer.get("readonly_vector_waiting")):
            errors.append("pgbouncer_readonly_vector_waiting")

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate a non-mutating PostgreSQL HA readiness report.",
    )
    parser.add_argument(
        "--use-readonly-probe",
        action="store_true",
        help="Probe the explicit read-only PgBouncer alias when configured.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON output.",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero when the readiness gate fails.",
    )
    args = parser.parse_args(argv)

    report = build_ha_readiness_report(use_readonly_probe=args.use_readonly_probe)
    if args.check:
        errors = _check_report(report, use_readonly_probe=args.use_readonly_probe)
        report["check_passed"] = not errors
        report["check_errors"] = errors

    if args.json or args.pretty:
        print(
            json.dumps(
                report,
                ensure_ascii=True,
                indent=2 if args.pretty else None,
                sort_keys=True,
            )
        )
    else:
        print(
            "postgres_in_recovery="
            f"{report.get('postgres_in_recovery')} "
            "transaction_read_only="
            f"{report.get('transaction_read_only')} "
            "pgbouncer_core_waiting="
            f"{report.get('pgbouncer_core_waiting')} "
            "pgbouncer_vector_waiting="
            f"{report.get('pgbouncer_vector_waiting')} "
            "replica_available="
            f"{report.get('replica_available')} "
            "wal_archive_mode="
            f"{report.get('wal_archive_mode')}"
        )

    if args.check and not report.get("check_passed"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
