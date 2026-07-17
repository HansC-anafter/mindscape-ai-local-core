#!/usr/bin/env python3
"""Inspect and operate the canonical runtime database incident gate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.services.runtime_database_incident_gate import (  # noqa: E402
    IncidentCloseReceipt,
    IncidentContainmentReceipt,
    IncidentDiagnosticPermit,
    RuntimeDatabaseIncidentJournal,
    RuntimeDatabaseMutationGate,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--journal-root", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)

    status = commands.add_parser("status")
    status.add_argument("--operation", default="maintenance")
    status.add_argument("--artifact-sha256", default="")

    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument("operation")
    evaluate.add_argument("--artifact-sha256", default="")

    open_command = commands.add_parser("open")
    open_command.add_argument("failure_code")
    open_command.add_argument("--postmaster-start-time", default="unknown")

    contain = commands.add_parser("contain")
    contain.add_argument("incident_id")
    contain.add_argument("--permit-id", required=True)
    contain.add_argument("--trigger-classification", required=True)
    contain.add_argument("--fix-commit", required=True)
    contain.add_argument("--allowed-operation-key", action="append", required=True)
    contain.add_argument("--test-evidence-path", action="append", required=True)
    contain.add_argument("--restore-id", required=True)
    contain.add_argument("--expires-at", required=True)
    contain.add_argument("--owner", required=True)

    diagnose = commands.add_parser("diagnose")
    diagnose.add_argument("incident_id")
    diagnose.add_argument("--permit-id", required=True)
    diagnose.add_argument("--source-commit", required=True)
    diagnose.add_argument("--allowed-operation-key", action="append", required=True)
    diagnose.add_argument("--test-evidence-path", action="append", required=True)
    diagnose.add_argument("--isolated-drill-id", required=True)
    diagnose.add_argument("--budget-sha256", required=True)
    diagnose.add_argument("--expires-at", required=True)
    diagnose.add_argument("--owner", required=True)

    close = commands.add_parser("close")
    close.add_argument("incident_id")
    close.add_argument("--deep-trigger-classification", required=True)
    close.add_argument("--fix-commit", required=True)
    close.add_argument("--test-evidence-path", action="append", required=True)
    close.add_argument("--soak-window", required=True)
    close.add_argument("--restore-id", required=True)
    close.add_argument("--owner", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    journal = RuntimeDatabaseIncidentJournal(args.journal_root)
    gate = RuntimeDatabaseMutationGate(args.journal_root)

    if args.command == "status":
        current = journal.current()
        decision = gate.evaluate(
            args.operation,
            {"artifact_sha256": args.artifact_sha256},
        )
        payload = {
            "current": current.to_dict() if current else None,
            "decision": decision.to_dict(),
        }
        print(json.dumps(payload, sort_keys=True))
        return 0 if decision.allowed else 2
    if args.command == "evaluate":
        decision = gate.evaluate(
            args.operation,
            {"artifact_sha256": args.artifact_sha256},
        )
        print(json.dumps(decision.to_dict(), sort_keys=True))
        return 0 if decision.allowed else 2
    if args.command == "open":
        receipt = journal.open_incident(
            failure_code=args.failure_code,
            postmaster_start_time=args.postmaster_start_time,
        )
    elif args.command == "diagnose":
        receipt = journal.record_diagnostic_permit(
            args.incident_id,
            IncidentDiagnosticPermit(
                permit_id=args.permit_id,
                source_commit=args.source_commit,
                allowed_operation_keys=tuple(args.allowed_operation_key),
                test_evidence_paths=tuple(args.test_evidence_path),
                isolated_drill_id=args.isolated_drill_id,
                budget_sha256=args.budget_sha256,
                expires_at=args.expires_at,
                owner=args.owner,
            ),
        )
    elif args.command == "contain":
        receipt = journal.mark_contained(
            args.incident_id,
            IncidentContainmentReceipt(
                permit_id=args.permit_id,
                trigger_classification=args.trigger_classification,
                fix_commit=args.fix_commit,
                allowed_operation_keys=tuple(args.allowed_operation_key),
                test_evidence_paths=tuple(args.test_evidence_path),
                restore_id=args.restore_id,
                expires_at=args.expires_at,
                owner=args.owner,
            ),
        )
    elif args.command == "close":
        receipt = journal.close(
            args.incident_id,
            IncidentCloseReceipt(
                deep_trigger_classification=args.deep_trigger_classification,
                fix_commit=args.fix_commit,
                test_evidence_paths=tuple(args.test_evidence_path),
                soak_window=args.soak_window,
                restore_id=args.restore_id,
                owner=args.owner,
            ),
        )
    else:
        raise AssertionError(f"Unhandled command: {args.command}")
    print(json.dumps(receipt.to_dict(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
