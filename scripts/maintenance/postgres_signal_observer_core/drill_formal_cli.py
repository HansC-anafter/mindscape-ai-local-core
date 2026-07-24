"""Thin executable composition owner for one formal isolated observer drill."""

from __future__ import annotations

import os
import subprocess
from typing import Any, Callable, Mapping

from backend.app.services.runtime_database_incident_core.journal import (
    RuntimeDatabaseIncidentJournal,
)
from backend.app.services.runtime_database_incident_gate import (
    require_runtime_database_mutation_allowed,
)

from .drill_admin_url import DisposableDrillObserverEnvironment
from .drill_escalation import load_postgres_bootstrap_environment
from .drill_formal_contract import (
    FormalDrillCliConfig,
    build_formal_drill_cli_config,
)
from .drill_formal_executor import FormalDockerSubprocessExecutor
from .drill_formal_gates import FormalDrillGateOwner
from .drill_formal_sequence import (
    canonical_formal_drill_sequence,
    execute_formal_drill_sequence,
    materialize_formal_signal_envelope,
)
from .drill_formal_terminal import (
    FORMAL_MATERIALIZED_PRECONDITION_VALIDATION_FAILED,
    FormalPreconditionFailure,
    FormalPreconditionState,
    prepare_formal_preconditions,
    terminal_finalize,
)


FORMAL_FULL_SEQUENCE_ENTRY = "execute_formal_drill_sequence"
LEGACY_FORMAL_MUTATION_ENTRY_FAILURE = "formal_drill_full_sequence_entry_required"


def execute_canonical_formal_drill(
    config: FormalDrillCliConfig,
    *,
    run: Callable[..., Any] = subprocess.run,
) -> dict[str, Any]:
    """Execute the entire granted drill inside one formally escalated CLI."""

    config.validate()
    decision = require_runtime_database_mutation_allowed(
        "postgres_signal_observer_start",
        evidence={"artifact_sha256": config.artifact_sha256},
        journal_root=config.journal_root,
    )
    if decision.reason != "incident_diagnostic_permit" or not decision.incident_id:
        raise RuntimeError("incident_diagnostic_permit_required")
    incident_id = decision.incident_id
    executor = FormalDockerSubprocessExecutor(run=run)
    preconditions = FormalPreconditionState()
    try:
        preconditions = prepare_formal_preconditions(config)
        config.validate_materialized()
        executor.bootstrap_environment = load_postgres_bootstrap_environment(
            preconditions.files[0]
        )
        executor.client_environment = {
            **os.environ,
            "PGPASSWORD": executor.bootstrap_environment["POSTGRES_PASSWORD"],
        }
        executor.observer_environment = (
            DisposableDrillObserverEnvironment.from_isolated_preconditions(
                config.bootstrap,
                base_environment=os.environ,
            )
        )
    except BaseException as error:
        if isinstance(error, FormalPreconditionFailure):
            preconditions = error.state
            failure_detail_code = error.detail_code
            initial_cleanup_completed = error.cleanup_completed
        else:
            failure_detail_code = (
                FORMAL_MATERIALIZED_PRECONDITION_VALIDATION_FAILED
            )
            initial_cleanup_completed = False
        revocation_completed = False
        try:
            RuntimeDatabaseIncidentJournal(
                config.journal_root
            ).revoke_diagnostic_permit(
                incident_id,
                terminal_reason="formal_drill_precondition_failed",
                failure_code="formal_drill_precondition_failed",
            )
        except Exception:
            pass
        else:
            revocation_completed = True
        postflight = terminal_finalize(
            config,
            executor,
            preconditions,
            incident_id=incident_id,
            terminal_reason="formal_drill_precondition_failed",
        )
        return {
            "validation_passed": False,
            "first_failure": "formal_drill_precondition_failed",
            "failure_detail_code": failure_detail_code,
            "precondition_receipt": {
                "validation_passed": False,
                "detail_code": failure_detail_code,
                "initial_cleanup_completed": initial_cleanup_completed,
                "created_directory_count": len(
                    preconditions.owned_directories
                ),
                "unverified_created_path_count": len(
                    preconditions.unverified_created_paths
                ),
                "secret_files_created": len(preconditions.owned_files),
                "secret_files_remaining": (
                    0 if postflight["local_staging_removed"] else None
                ),
                "network_mutation_attempted": False,
                "container_mutation_attempted": False,
                "downstream_mutation_attempted": False,
                "exception_payload_persisted": False,
                "path_payload_persisted": False,
            },
            "permit_revocation_completed": revocation_completed,
            "ownership_handed_back": postflight["handed_back"],
            **postflight,
        }

    def revoke(reason: str) -> None:
        RuntimeDatabaseIncidentJournal(config.journal_root).revoke_diagnostic_permit(
            incident_id,
            terminal_reason=reason,
            failure_code=(
                None if reason == "formal_drill_sequence_terminal_complete" else reason
            ),
        )

    def finalize(first_failure: str | None) -> Mapping[str, Any]:
        return terminal_finalize(
            config,
            executor,
            preconditions,
            incident_id=incident_id,
            terminal_reason=(first_failure or "formal_drill_sequence_terminal_complete"),
        )

    gate_owner = FormalDrillGateOwner(config, executor)
    definition = canonical_formal_drill_sequence(
        config.bootstrap,
        config.observer,
        config.client,
    )
    receipt = execute_formal_drill_sequence(
        definition,
        execute_docker=lambda envelope: executor.execute(envelope, config=config),
        evaluate_gate=gate_owner.evaluate,
        materialize_operation=lambda owner: (
            materialize_formal_signal_envelope(executor.signal_config)
            if owner == "source_owned_signal_sender"
            and executor.signal_config is not None
            else (_ for _ in ()).throw(
                RuntimeError("formal_signal_target_pid_not_source_owned")
            )
        ),
        revoke_permit=revoke,
        finalize_cleanup=finalize,
    )
    return {
        **receipt,
        "entry": FORMAL_FULL_SEQUENCE_ENTRY,
        "incident_id": incident_id,
        "artifact_sha256": config.artifact_sha256,
        "single_formal_escalation_unit": True,
        "shell": False,
        "legacy_mutation_entry_allowed": False,
    }
