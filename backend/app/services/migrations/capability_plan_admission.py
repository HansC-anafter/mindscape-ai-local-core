"""Admission facade for capability migration plans during database incidents."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from backend.app.services.runtime_database_incident_gate import (
    MutationDecision,
    RuntimeDatabaseMutationBlocked,
    require_runtime_database_mutation_allowed,
)


MutationAdmission = Callable[[str], MutationDecision]


@dataclass(frozen=True)
class CapabilityMigrationPlanAdmission:
    """The one admitted execution mode for a capability migration plan."""

    mode: str
    decisions: tuple[MutationDecision, ...]


def require_capability_migration_plan_allowed(
    *,
    capability_code: str,
    alembic_config: Path,
    pending_revisions: Iterable[str],
    require_allowed: MutationAdmission = (
        require_runtime_database_mutation_allowed
    ),
) -> CapabilityMigrationPlanAdmission:
    """Admit a generic plan or require an exact permit for every revision."""

    normalized_code = str(capability_code).strip()
    revisions = tuple(
        str(revision).strip()
        for revision in pending_revisions
        if str(revision).strip()
    )
    try:
        decision = require_allowed(
            f"capability_migration:{normalized_code}"
        )
    except RuntimeDatabaseMutationBlocked:
        if not revisions:
            raise
        exact_decisions = tuple(
            require_allowed(
                f"alembic_upgrade:{alembic_config.name}:{revision}"
            )
            for revision in revisions
        )
        return CapabilityMigrationPlanAdmission(
            mode="exact_per_revision",
            decisions=exact_decisions,
        )
    return CapabilityMigrationPlanAdmission(
        mode="generic_capability",
        decisions=(decision,),
    )


__all__ = [
    "CapabilityMigrationPlanAdmission",
    "require_capability_migration_plan_allowed",
]
