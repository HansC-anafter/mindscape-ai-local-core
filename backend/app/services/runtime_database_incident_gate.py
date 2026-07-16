"""Public facade for runtime database incidents and mutation admission."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Optional

from backend.app.services.runtime_database_incident_core.classifier_bridge import (
    record_failure,
)
from backend.app.services.runtime_database_incident_core.evaluator import (
    RuntimeDatabaseMutationBlocked,
    RuntimeDatabaseMutationGate,
)
from backend.app.services.runtime_database_incident_core.journal import (
    IncidentJournalUnavailable,
    IncidentTransitionError,
    RuntimeDatabaseIncidentJournal,
)
from backend.app.services.runtime_database_incident_core.models import (
    IncidentCloseReceipt,
    IncidentReceipt,
    IncidentState,
    MutationDecision,
)


def record_database_failure(
    failure_code: str,
    *,
    postmaster_start_time: str = "unknown",
    evidence: Optional[Mapping[str, str]] = None,
    journal_root: Optional[Path] = None,
) -> IncidentReceipt:
    return record_failure(
        failure_code,
        postmaster_start_time=postmaster_start_time,
        evidence=evidence,
        journal_root=journal_root,
    )


def evaluate_runtime_database_mutation(
    operation: str,
    *,
    journal_root: Optional[Path] = None,
) -> MutationDecision:
    return RuntimeDatabaseMutationGate(journal_root).evaluate(operation)


def require_runtime_database_mutation_allowed(
    operation: str,
    *,
    journal_root: Optional[Path] = None,
) -> MutationDecision:
    return RuntimeDatabaseMutationGate(journal_root).require_allowed(operation)


__all__ = [
    "IncidentCloseReceipt",
    "IncidentJournalUnavailable",
    "IncidentReceipt",
    "IncidentState",
    "IncidentTransitionError",
    "MutationDecision",
    "RuntimeDatabaseIncidentJournal",
    "RuntimeDatabaseMutationBlocked",
    "RuntimeDatabaseMutationGate",
    "evaluate_runtime_database_mutation",
    "record_database_failure",
    "require_runtime_database_mutation_allowed",
]
