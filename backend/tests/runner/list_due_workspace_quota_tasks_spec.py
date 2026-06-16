from backend.app.models.workspace import TaskStatus
from backend.tests.runner.try_claim_task_concurrency_guard_support import (
    _SqliteClaimStore,
    _utc_now,
)


def test_list_due_workspace_quota_tasks_includes_allocation_required_and_disabled():
    store = _SqliteClaimStore()
    for task_id, blocked_reason in (
        ("decision-required", "workspace_allocation_required"),
        ("decision-disabled", "workspace_allocation_disabled"),
        ("decision-quota", "workspace_allocation_quota_exhausted"),
    ):
        store.insert_task(
            task_id=task_id,
            status=TaskStatus.PENDING.value,
            pack_id="decision_assets_synthesize",
            execution_context={"playbook_code": "decision_assets_synthesize"},
            concurrency_key=None,
            queue_shard="decision_synthesis",
            task_type="playbook_execution",
            blocked_reason=blocked_reason,
            frontier_state="cold",
            created_at=_utc_now(),
            next_eligible_at=_utc_now(),
        )

    tasks = store.list_due_workspace_quota_tasks(
        queue_shard="decision_synthesis",
        limit=10,
    )

    assert {task.id for task in tasks} == {
        "decision-required",
        "decision-disabled",
        "decision-quota",
    }
    assert {task.blocked_reason for task in tasks} == {
        "workspace_allocation_required",
        "workspace_allocation_disabled",
        "workspace_allocation_quota_exhausted",
    }
