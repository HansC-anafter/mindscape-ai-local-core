from pathlib import Path

import pytest

from backend.app.services.migrations.capability_plan_admission import (
    require_capability_migration_plan_allowed,
)
from backend.app.services.runtime_database_incident_gate import (
    MutationDecision,
    RuntimeDatabaseMutationBlocked,
)


def _decision(operation: str, *, allowed: bool) -> MutationDecision:
    return MutationDecision(
        allowed=allowed,
        operation=operation,
        reason="test_allowed" if allowed else "test_blocked",
        incident_id="incident-test",
    )


def test_generic_capability_admission_remains_the_default() -> None:
    calls: list[str] = []

    def require_allowed(operation: str) -> MutationDecision:
        calls.append(operation)
        return _decision(operation, allowed=True)

    admission = require_capability_migration_plan_allowed(
        capability_code="frontier_research",
        alembic_config=Path("alembic.postgres.ini"),
        pending_revisions=("20260730010000",),
        require_allowed=require_allowed,
    )

    assert admission.mode == "generic_capability"
    assert calls == ["capability_migration:frontier_research"]


def test_incident_requires_every_exact_pending_revision() -> None:
    calls: list[str] = []

    def require_allowed(operation: str) -> MutationDecision:
        calls.append(operation)
        decision = _decision(
            operation,
            allowed=not operation.startswith("capability_migration:"),
        )
        if not decision.allowed:
            raise RuntimeDatabaseMutationBlocked(decision)
        return decision

    admission = require_capability_migration_plan_allowed(
        capability_code="frontier_research",
        alembic_config=Path("alembic.postgres.ini"),
        pending_revisions=("revision_a", "revision_b"),
        require_allowed=require_allowed,
    )

    assert admission.mode == "exact_per_revision"
    assert calls == [
        "capability_migration:frontier_research",
        "alembic_upgrade:alembic.postgres.ini:revision_a",
        "alembic_upgrade:alembic.postgres.ini:revision_b",
    ]


def test_missing_exact_revision_permit_stays_fail_closed() -> None:
    def require_allowed(operation: str) -> MutationDecision:
        decision = _decision(
            operation,
            allowed=operation.endswith(":revision_a"),
        )
        if not decision.allowed:
            raise RuntimeDatabaseMutationBlocked(decision)
        return decision

    with pytest.raises(RuntimeDatabaseMutationBlocked) as raised:
        require_capability_migration_plan_allowed(
            capability_code="frontier_research",
            alembic_config=Path("alembic.postgres.ini"),
            pending_revisions=("revision_a", "revision_b"),
            require_allowed=require_allowed,
        )

    assert raised.value.decision.operation.endswith(":revision_b")
