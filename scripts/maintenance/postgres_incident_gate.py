#!/usr/bin/env python3
"""Inspect and operate the canonical runtime database incident gate."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.services.runtime_database_incident_gate import (  # noqa: E402
    ATTRIBUTION_EXHAUSTION_CLASSIFICATION,
    RESIDUAL_CLOSURE_MODE,
    RESIDUAL_RISK_STATEMENT,
    IncidentAttributionExhaustionReceipt,
    IncidentCloseReceipt,
    IncidentContainmentReceipt,
    IncidentDiagnosticPermit,
    IncidentPackInstallPermitReceipt,
    IncidentResidualCloseReceipt,
    IncidentTargetedMigrationPermitReceipt,
    RuntimeDatabaseIncidentJournal,
    RuntimeDatabaseMutationGate,
)
from scripts.maintenance.postgres_signal_observer_preflight_core import (  # noqa: E402
    receipt_bound_incident_id,
)


_ARTIFACT_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_DIAGNOSTIC_OPERATIONS = (
    "postgres_signal_observer_start",
    "postgres_identity_logging_reload",
)


def _add_common_close_arguments(command: argparse.ArgumentParser) -> None:
    command.add_argument("--fix-commit", required=True)
    command.add_argument("--containment-evidence-path", required=True)
    command.add_argument("--containment-evidence-sha256", required=True)
    command.add_argument("--test-evidence-path", action="append", required=True)
    command.add_argument("--test-evidence-sha256", required=True)
    command.add_argument("--reproduction-evidence-path", required=True)
    command.add_argument("--reproduction-evidence-sha256", required=True)
    command.add_argument("--soak-window", required=True)
    command.add_argument("--restore-id", required=True)
    command.add_argument("--restore-evidence-path", required=True)
    command.add_argument("--restore-evidence-sha256", required=True)
    command.add_argument("--resource-budget-evidence-path", required=True)
    command.add_argument("--resource-budget-evidence-sha256", required=True)
    command.add_argument("--owner", required=True)
    command.add_argument("--owner-receipt-path", required=True)
    command.add_argument("--owner-receipt-sha256", required=True)


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

    renew = commands.add_parser("renew-containment")
    renew.add_argument("incident_id")
    renew.add_argument("--permit-id", required=True)
    renew.add_argument("--trigger-classification", required=True)
    renew.add_argument("--fix-commit", required=True)
    renew.add_argument("--allowed-operation-key", action="append", required=True)
    renew.add_argument("--test-evidence-path", action="append", required=True)
    renew.add_argument("--restore-id", required=True)
    renew.add_argument("--expires-at", required=True)
    renew.add_argument("--owner", required=True)
    renew.add_argument("--authorization", required=True)

    pack_permit = commands.add_parser("permit-pack-install")
    pack_permit.add_argument("incident_id")
    pack_permit.add_argument("--permit-id", required=True)
    pack_permit.add_argument("--capability-code", required=True)
    pack_permit.add_argument("--current-version", required=True)
    pack_permit.add_argument("--candidate-version", required=True)
    pack_permit.add_argument("--artifact-sha256", required=True)
    pack_permit.add_argument("--preflight-evidence-path", action="append", required=True)
    pack_permit.add_argument("--migration-revision", action="append", default=[])
    pack_permit.add_argument("--migration-files-digest", required=True)
    pack_permit.add_argument("--backout-install-id", required=True)
    pack_permit.add_argument("--backout-artifact-sha256", required=True)
    pack_permit.add_argument("--expires-at", required=True)
    pack_permit.add_argument("--owner", required=True)
    pack_permit.add_argument("--owner-authorization", required=True)

    revoke_pack_permit = commands.add_parser("revoke-pack-install")
    revoke_pack_permit.add_argument("incident_id")
    revoke_pack_permit.add_argument("--permit-id", required=True)
    revoke_pack_permit.add_argument("--terminal-install-id", required=True)
    revoke_pack_permit.add_argument(
        "--terminal-status",
        choices=("succeeded", "failed", "cancelled"),
        required=True,
    )
    revoke_pack_permit.add_argument("--terminal-evidence-path", required=True)

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

    diagnose = commands.add_parser("diagnose")
    diagnose.add_argument("--incident-id")
    diagnose.add_argument("--qualification-receipt", type=Path)
    diagnose.add_argument("--ownership-request-receipt", type=Path)
    diagnose.add_argument("--ownership-grant-receipt", type=Path)
    diagnose.add_argument("--permit-id", required=True)
    diagnose.add_argument("--source-commit", required=True)
    diagnose.add_argument(
        "--diagnostic-operation",
        choices=_DIAGNOSTIC_OPERATIONS,
        required=True,
    )
    diagnose.add_argument("--artifact-sha256", required=True)
    diagnose.add_argument("--test-evidence-path", action="append", required=True)
    diagnose.add_argument("--capture-evidence-id", required=True)
    diagnose.add_argument("--budget-sha256", required=True)
    diagnose.add_argument("--expires-at", required=True)
    diagnose.add_argument("--owner", required=True)

    revoke_diagnostic = commands.add_parser("revoke-diagnostic")
    revoke_diagnostic.add_argument("incident_id")
    revoke_diagnostic.add_argument(
        "--terminal-reason",
        choices=(
            "planned_reconfigure",
            "attribution_event_recorded",
            "observer_failure",
        ),
        required=True,
    )
    revoke_diagnostic.add_argument("--failure-code")

    exhaustion = commands.add_parser("record-attribution-exhaustion")
    exhaustion.add_argument("incident_id")
    exhaustion.add_argument("--search-started-at", required=True)
    exhaustion.add_argument("--search-ended-at", required=True)
    exhaustion.add_argument("--searched-source", action="append", required=True)
    exhaustion.add_argument("--evidence-bundle-path", required=True)
    exhaustion.add_argument("--evidence-bundle-sha256", required=True)
    exhaustion.add_argument("--owner", required=True)
    exhaustion.add_argument("--owner-authorization", required=True)
    exhaustion.add_argument("--owner-authorization-path", required=True)
    exhaustion.add_argument("--owner-authorization-sha256", required=True)

    reopen = commands.add_parser("reopen-for-attribution")
    reopen.add_argument("incident_id")
    reopen.add_argument("--owner", required=True)
    reopen.add_argument("--authorization", required=True)
    reopen.add_argument("--authorization-path", required=True)
    reopen.add_argument("--authorization-sha256", required=True)
    reopen.add_argument("--reason", required=True)

    close = commands.add_parser("close")
    close.add_argument("incident_id")
    close.add_argument("--deep-trigger-classification", required=True)
    close.add_argument("--deep-trigger-event-sha256", required=True)
    _add_common_close_arguments(close)

    close_residual = commands.add_parser("close-residual")
    close_residual.add_argument("incident_id")
    close_residual.add_argument("--attribution-exhaustion-sha256", required=True)
    _add_common_close_arguments(close_residual)
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
    elif args.command == "renew-containment":
        receipt = journal.renew_containment(
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
            authorization=args.authorization,
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
    elif args.command == "revoke-pack-install":
        receipt = journal.revoke_pack_install_permit(
            args.incident_id,
            permit_id=args.permit_id,
            terminal_install_id=args.terminal_install_id,
            terminal_status=args.terminal_status,
            terminal_evidence_path=args.terminal_evidence_path,
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
    elif args.command == "diagnose":
        artifact_sha256 = str(args.artifact_sha256).strip()
        if not _ARTIFACT_SHA256_PATTERN.fullmatch(artifact_sha256):
            raise SystemExit("diagnostic_artifact_sha256_invalid")
        operation_key = gate.operation_key(
            args.diagnostic_operation,
            {"artifact_sha256": artifact_sha256},
        )
        if args.diagnostic_operation == "postgres_signal_observer_start":
            if args.incident_id is not None:
                raise SystemExit("observer_incident_id_must_be_receipt_bound")
            receipt_paths = (
                args.qualification_receipt,
                args.ownership_request_receipt,
                args.ownership_grant_receipt,
            )
            if any(path is None for path in receipt_paths):
                raise SystemExit("observer_diagnostic_receipt_chain_required")
            incident_id = receipt_bound_incident_id(
                qualification_path=args.qualification_receipt,
                ownership_request_path=args.ownership_request_receipt,
                ownership_grant_path=args.ownership_grant_receipt,
                artifact_sha256=artifact_sha256,
                owner=args.owner,
                expires_at=args.expires_at,
            )
        else:
            if any(
                path is not None
                for path in (
                    args.qualification_receipt,
                    args.ownership_request_receipt,
                    args.ownership_grant_receipt,
                )
            ):
                raise SystemExit("identity_logging_receipt_chain_not_supported")
            incident_id = str(args.incident_id or "").strip()
            if not incident_id:
                raise SystemExit("diagnostic_incident_id_required")
        receipt = journal.record_diagnostic_permit(
            incident_id,
            IncidentDiagnosticPermit(
                permit_id=args.permit_id,
                source_commit=args.source_commit,
                allowed_operation_keys=(operation_key,),
                test_evidence_paths=tuple(args.test_evidence_path),
                capture_evidence_id=args.capture_evidence_id,
                budget_sha256=args.budget_sha256,
                expires_at=args.expires_at,
                owner=args.owner,
            ),
        )
    elif args.command == "revoke-diagnostic":
        receipt = journal.revoke_diagnostic_permit(
            args.incident_id,
            terminal_reason=args.terminal_reason,
            failure_code=args.failure_code,
        )
    elif args.command == "record-attribution-exhaustion":
        receipt = journal.record_attribution_exhaustion(
            args.incident_id,
            IncidentAttributionExhaustionReceipt(
                incident_id=args.incident_id,
                classification=ATTRIBUTION_EXHAUSTION_CLASSIFICATION,
                search_started_at=args.search_started_at,
                search_ended_at=args.search_ended_at,
                searched_sources=tuple(args.searched_source),
                evidence_bundle_path=args.evidence_bundle_path,
                evidence_bundle_sha256=args.evidence_bundle_sha256,
                residual_risk_statement=RESIDUAL_RISK_STATEMENT,
                owner=args.owner,
                owner_authorization=args.owner_authorization,
                owner_authorization_path=args.owner_authorization_path,
                owner_authorization_sha256=args.owner_authorization_sha256,
                search_complete=True,
            ),
        )
    elif args.command == "reopen-for-attribution":
        receipt = journal.reopen_for_attribution(
            args.incident_id,
            owner=args.owner,
            authorization=args.authorization,
            authorization_path=args.authorization_path,
            authorization_sha256=args.authorization_sha256,
            reason=args.reason,
        )
    elif args.command == "close":
        receipt = journal.close(
            args.incident_id,
            IncidentCloseReceipt(
                deep_trigger_classification=args.deep_trigger_classification,
                deep_trigger_event_sha256=args.deep_trigger_event_sha256,
                fix_commit=args.fix_commit,
                containment_evidence_path=args.containment_evidence_path,
                containment_evidence_sha256=args.containment_evidence_sha256,
                test_evidence_paths=tuple(args.test_evidence_path),
                test_evidence_sha256=args.test_evidence_sha256,
                reproduction_evidence_path=args.reproduction_evidence_path,
                reproduction_evidence_sha256=args.reproduction_evidence_sha256,
                soak_window=args.soak_window,
                restore_id=args.restore_id,
                restore_evidence_path=args.restore_evidence_path,
                restore_evidence_sha256=args.restore_evidence_sha256,
                resource_budget_evidence_path=args.resource_budget_evidence_path,
                resource_budget_evidence_sha256=args.resource_budget_evidence_sha256,
                owner=args.owner,
                owner_receipt_path=args.owner_receipt_path,
                owner_receipt_sha256=args.owner_receipt_sha256,
            ),
        )
    elif args.command == "close-residual":
        receipt = journal.close_residual(
            args.incident_id,
            IncidentResidualCloseReceipt(
                closure_mode=RESIDUAL_CLOSURE_MODE,
                attribution_exhaustion_sha256=args.attribution_exhaustion_sha256,
                residual_risk_statement=RESIDUAL_RISK_STATEMENT,
                fix_commit=args.fix_commit,
                containment_evidence_path=args.containment_evidence_path,
                containment_evidence_sha256=args.containment_evidence_sha256,
                test_evidence_paths=tuple(args.test_evidence_path),
                test_evidence_sha256=args.test_evidence_sha256,
                reproduction_evidence_path=args.reproduction_evidence_path,
                reproduction_evidence_sha256=args.reproduction_evidence_sha256,
                soak_window=args.soak_window,
                restore_id=args.restore_id,
                restore_evidence_path=args.restore_evidence_path,
                restore_evidence_sha256=args.restore_evidence_sha256,
                resource_budget_evidence_path=args.resource_budget_evidence_path,
                resource_budget_evidence_sha256=args.resource_budget_evidence_sha256,
                owner=args.owner,
                owner_receipt_path=args.owner_receipt_path,
                owner_receipt_sha256=args.owner_receipt_sha256,
            ),
        )
    else:
        raise AssertionError(f"Unhandled command: {args.command}")
    print(json.dumps(receipt.to_dict(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
