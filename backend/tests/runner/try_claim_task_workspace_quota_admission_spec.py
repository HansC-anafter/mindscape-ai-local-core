from types import SimpleNamespace

from backend.app.models.workspace import TaskStatus
from backend.tests.runner.try_claim_task_concurrency_guard_support import (
    _SqliteClaimStore,
    _following_ctx,
)


def test_try_claim_task_blocks_workspace_quota_over_parallel_cap():
    store = _SqliteClaimStore()
    allocation = store.insert_allocation(max_parallel_task_claims=4)
    profile_dir = "/app/data/ig-browser-profiles/default"
    for index in range(4):
        store.insert_task(
            task_id=f"running-{index}",
            status=TaskStatus.RUNNING.value,
            pack_id="ig_analyze_following",
            execution_context=_following_ctx(f"{profile_dir}-{index}"),
            concurrency_key=f"ig_profile:{profile_dir}-{index}",
        )
    store.insert_task(
        task_id="pending-1",
        status=TaskStatus.PENDING.value,
        pack_id="ig_analyze_following",
        execution_context=_following_ctx(f"{profile_dir}-pending"),
        concurrency_key=f"ig_profile:{profile_dir}-pending",
    )

    claimed = store.try_claim_task(
        "pending-1",
        runner_id="runner-a",
        workspace_quota_decision=SimpleNamespace(
            to_dict=lambda: {"allow": True, "allocation": allocation}
        ),
    )

    assert claimed is False
    assert store.fetch_status("pending-1") == TaskStatus.PENDING.value


def test_try_claim_task_allows_workspace_quota_at_available_slot():
    store = _SqliteClaimStore()
    allocation = store.insert_allocation(max_parallel_task_claims=4)
    profile_dir = "/app/data/ig-browser-profiles/default"
    for index in range(3):
        store.insert_task(
            task_id=f"running-{index}",
            status=TaskStatus.RUNNING.value,
            pack_id="ig_analyze_following",
            execution_context=_following_ctx(f"{profile_dir}-{index}"),
            concurrency_key=f"ig_profile:{profile_dir}-{index}",
        )
    store.insert_task(
        task_id="pending-1",
        status=TaskStatus.PENDING.value,
        pack_id="ig_analyze_following",
        execution_context=_following_ctx(f"{profile_dir}-pending"),
        concurrency_key=f"ig_profile:{profile_dir}-pending",
    )

    claimed = store.try_claim_task(
        "pending-1",
        runner_id="runner-a",
        workspace_quota_decision=SimpleNamespace(
            to_dict=lambda: {"allow": True, "allocation": allocation}
        ),
    )

    assert claimed is True
    assert store.fetch_status("pending-1") == TaskStatus.RUNNING.value
