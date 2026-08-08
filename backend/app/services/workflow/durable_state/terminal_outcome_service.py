"""Canonical terminal-to-outcome composition over existing owners."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from backend.app.services.stores.tasks_store import TasksStore

from .compatibility import CompatibilityRegistry
from .facade import DurableWorkflowFacade
from .outcome_adapter_resolver import OutcomeAdapterResolver
from .outcome_evaluation_task_handler import OutcomeEvaluationTaskHandler
from .outcome_evidence_repository import OutcomeEvidenceRepository
from .outcome_runtime_trust import OutcomeRuntimeTrust
from .outcome_task_adapter import OutcomeTaskAdapter
from .signature import Ed25519Signer


class DurableTerminalOutcomeService:
    """Owns one transaction, then wakes only a newly committed task."""

    def __init__(
        self,
        *,
        transaction: Callable,
        facade: DurableWorkflowFacade,
        resolver: OutcomeAdapterResolver,
        task_adapter: OutcomeTaskAdapter,
        evidence_repository: OutcomeEvidenceRepository,
        capability_entries: Mapping[str, dict[str, Any]],
        terminal_verification_keys: dict[str, object],
        enrollment_verification_keys: dict[str, object],
    ) -> None:
        self._transaction = transaction
        self._facade = facade
        self._task_adapter = task_adapter
        self._evidence_repository = evidence_repository
        self._capability_entries = capability_entries
        self._handler = OutcomeEvaluationTaskHandler(
            resolver,
            create_task_with_conn=task_adapter.create_with_conn,
            append_linkage_with_conn=(facade.append_outcome_evaluation_intent),
            terminal_verification_keys=terminal_verification_keys,
            enrollment_verification_keys=enrollment_verification_keys,
        )

    def record_terminal(self, **terminal_kwargs) -> dict[str, Any]:
        with self._transaction() as conn:
            terminal = self._facade.append_execution_terminal(
                conn,
                **terminal_kwargs,
            )
            enrollment_record = self._evidence_repository.enrollment_for_terminal(
                conn,
                terminal_receipt_id=terminal["receipt_id"],
                workspace_id=terminal["workspace_id"],
            )
            outcome = self._handler.prepare(
                conn,
                capability_entries=self._capability_entries,
                terminal_receipt=terminal,
                enrollment=(
                    enrollment_record["enrollment"] if enrollment_record else None
                ),
            )
        task_id = None
        if outcome["status"] == "task_created":
            task = self._task_adapter.finalize_after_commit(outcome["task"])
            task_id = task.id
        return {
            "terminal_receipt": terminal,
            "outcome_evaluation": {
                "status": outcome["status"],
                "task_id": task_id,
                "rejection": outcome.get("rejection"),
            },
        }


def build_terminal_outcome_service() -> DurableTerminalOutcomeService:
    """Build the production service from mounted trust and existing stores."""

    from backend.app.database.engine import engine_postgres_core
    from backend.app.services.capability_registry import get_registry

    if engine_postgres_core is None:
        raise RuntimeError("durable_terminal_core_database_unavailable")
    workflow_signer = Ed25519Signer.from_mounted_file()
    trust = OutcomeRuntimeTrust.from_mounted_files()
    verification_keys = {
        workflow_signer.key_id: workflow_signer.public_key(),
        **trust.observation_verification_keys,
    }
    facade = DurableWorkflowFacade(
        signer=workflow_signer,
        compatibility=CompatibilityRegistry(),
        verification_keys=verification_keys,
    )
    tasks_store = TasksStore()
    return DurableTerminalOutcomeService(
        transaction=engine_postgres_core.begin,
        facade=facade,
        resolver=OutcomeAdapterResolver(workflow_signer),
        task_adapter=OutcomeTaskAdapter(
            tasks_store=tasks_store,
            admission_signer=trust.descriptor_signer,
        ),
        evidence_repository=OutcomeEvidenceRepository(),
        capability_entries=get_registry().capabilities,
        terminal_verification_keys={
            workflow_signer.key_id: workflow_signer.public_key()
        },
        enrollment_verification_keys={
            workflow_signer.key_id: workflow_signer.public_key()
        },
    )


__all__ = (
    "DurableTerminalOutcomeService",
    "build_terminal_outcome_service",
)
