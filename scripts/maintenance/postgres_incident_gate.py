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
    IncidentPackInstallPermitReceipt,
    IncidentTargetedMigrationPermitReceipt,
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

    pack_permit = commands.add_parser("permit-pack-install")
    pack_permit.add_argument("incident_id")
    pack_permit.add_argument("--permit-id", required=True)
    pack_permit.add_argument("--capability-code", required=True)
    pack_permit.add_argument("--current-version", required=True)
    pack_permit.add_argument("--candidate-version", required=True)
    pack_permit.add_argument("--artifact-sha256", required=True)
    pack_permit.add_argument("--preflight-evidence-path", action="append", required=True)
    pack_permit.add_argument("--migration-revision", action="append", required=True)
    pack_permit.add_argument("--migration-files-digest", required=True)
    pack_permit.add_argument("--backout-install-id", required=True)
    pack_permit.add_argument("--backout-artifact-sha256", required=True)
    pack_permit.add_argument("--expires-at", required=True)
    pack_permit.add_argument("--owner", required=True)
    pack_permit.add_argument("--owner-authorization", required=True)

    migration_permit = commands.add_parser("permit-targeted-migration")
    migration_permit.add_argument("incident_id")
    migration_permit.add_argument("--permit-id", required=True)
    migration_permit.add_argument("--alembic-config-name", required=True)
    migration_permit.add_argument("--revision", required=True)
    migration_permit.add_argument("--migration-file-sha256", required=True)
    migration_permit.add_argument("--created-relation", action="append", required=True)
    migration_permit.add_argument(
        "--preflight-evidence-path",
        action="append",
        required=True,
    )
    migration_permit.add_argument("--expires-at", required=True)
    migration_permit.add_argument("--owner", required=True)
    migration_permit.add_argument("--owner-authorization", required=True)

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
    elif args.command == "permit-pack-install":
        artifact_sha256 = args.artifact_sha256.strip().lower()
        receipt = journal.grant_pack_install_permit(
            args.incident_id,
            IncidentPackInstallPermitReceipt(
                permit_id=args.permit_id,
                capability_code=args.capability_code,
                current_version=args.current_version,
                candidate_version=args.candidate_version,
                artifact_sha256=artifact_sha256,
                allowed_operation_keys=(
                    f"capability_install_intake:file@sha256:{artifact_sha256}",
                    f"capability_install_job@sha256:{artifact_sha256}",
                ),
                preflight_evidence_paths=tuple(args.preflight_evidence_path),
                migration_revisions=tuple(args.migration_revision),
                migration_files_digest=args.migration_files_digest,
                schema_mutation_required=False,
                backout_install_id=args.backout_install_id,
                backout_artifact_sha256=args.backout_artifact_sha256,
                expires_at=args.expires_at,
                owner=args.owner,
                owner_authorization=args.owner_authorization,
            ),
        )
    elif args.command == "permit-targeted-migration":
        operation_key = (
            f"alembic_upgrade:{args.alembic_config_name}:{args.revision}"
        )
        receipt = journal.grant_targeted_migration_permit(
            args.incident_id,
            IncidentTargetedMigrationPermitReceipt(
                permit_id=args.permit_id,
                alembic_config_name=args.alembic_config_name,
                revision=args.revision,
                migration_file_sha256=args.migration_file_sha256,
                migration_mode="create_only",
                created_relations=tuple(args.created_relation),
                allowed_operation_key=operation_key,
                preflight_evidence_paths=tuple(args.preflight_evidence_path),
                expires_at=args.expires_at,
                owner=args.owner,
                owner_authorization=args.owner_authorization,
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
