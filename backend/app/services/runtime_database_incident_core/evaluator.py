"""Canonical runtime database mutation decision evaluator."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .journal import IncidentJournalUnavailable, RuntimeDatabaseIncidentJournal
from .models import IncidentState, MutationDecision


class RuntimeDatabaseMutationBlocked(RuntimeError):
    """Raised when a high-risk mutation is blocked by the incident gate."""

    def __init__(self, decision: MutationDecision):
        self.decision = decision
        super().__init__(decision.reason)


class RuntimeDatabaseMutationGate:
    """Return one stable decision for every high-risk mutation caller."""

    def __init__(self, journal_root: Optional[Path] = None):
        self.journal = RuntimeDatabaseIncidentJournal(journal_root)

    def evaluate(self, operation: str) -> MutationDecision:
        operation_name = str(operation).strip() or "unspecified_mutation"
        try:
            current = self.journal.current()
        except IncidentJournalUnavailable:
            return MutationDecision(
                allowed=False,
                operation=operation_name,
                reason="incident_journal_unavailable",
            )
        if current is None or current.state is IncidentState.CLOSED:
            return MutationDecision(
                allowed=True,
                operation=operation_name,
                reason="allowed",
                retry_after_seconds=0,
            )
        return MutationDecision(
            allowed=False,
            operation=operation_name,
            reason="runtime_database_incident_open",
            incident_id=current.incident_id,
            details={"incident_state": current.state.value},
        )

    def require_allowed(self, operation: str) -> MutationDecision:
        decision = self.evaluate(operation)
        if not decision.allowed:
            raise RuntimeDatabaseMutationBlocked(decision)
        return decision
