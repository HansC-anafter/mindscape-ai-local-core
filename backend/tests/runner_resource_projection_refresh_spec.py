from datetime import datetime, timezone

from backend.app.models.workspace import TaskStatus
from backend.tests.runner.try_claim_task_concurrency_guard_support import (
    _SqliteClaimStore,
)


def _store_with_resource_block() -> _SqliteClaimStore:
    store = _SqliteClaimStore()
    store.insert_task(
        task_id="resource-cold-1",
        status=TaskStatus.PENDING.value,
        pack_id="core_resource_task",
        task_type="tool_execution",
        execution_context={"resource_block": {"memory": 4096}},
        concurrency_key=None,
        blocked_reason="resource_exhausted",
        frontier_state="cold",
    )
    return store


def test_resource_resume_refreshes_projection_in_the_same_transaction():
    store = _store_with_resource_block()

    resumed = store.try_resume_resource_block(
        "resource-cold-1",
        expected_blocked_reason="resource_exhausted",
        execution_context={"resume_reason": "capacity restored"},
        resumed_at=datetime.now(timezone.utc),
    )

    row = store.fetch_task_row("resource-cold-1")
    assert resumed is True
    assert store.fetch_frontier("resource-cold-1") == "ready"
    assert row.blocked_reason is None
    assert store.projection_refreshes == ["resource-cold-1"]


def test_resource_resume_noop_does_not_refresh_projection():
    store = _store_with_resource_block()

    resumed = store.try_resume_resource_block(
        "resource-cold-1",
        expected_blocked_reason="different_reason",
        execution_context={"resume_reason": "capacity restored"},
        resumed_at=datetime.now(timezone.utc),
    )

    assert resumed is False
    assert store.fetch_frontier("resource-cold-1") == "cold"
    assert store.projection_refreshes == []
