from backend.app.models.workspace import TaskStatus
from backend.tests.runner.try_claim_task_concurrency_guard_support import (
    _SqliteClaimStore,
)


def test_try_release_workspace_quota_task_moves_cold_task_to_ready():
    store = _SqliteClaimStore()
    store.insert_allocation(
        max_parallel_task_claims=4,
        queue_shard="browser_local",
        task_family="ig_browser_capture",
        selectors=["ig_analyze_following"],
    )
    store.insert_task(
        task_id="quota-cold-1",
        status=TaskStatus.PENDING.value,
        pack_id="ig_analyze_following",
        execution_context={
            "playbook_code": "ig_analyze_following",
            "workspace_quota_admission": {"reason": "quota"},
        },
        concurrency_key=None,
        blocked_reason="workspace_allocation_quota_exhausted",
        frontier_state="cold",
    )

    released = store.try_release_workspace_quota_task(
        "quota-cold-1",
        workspace_id="ws-1",
        queue_shard="browser_local",
        selectors=["ig_analyze_following"],
        task_selector="ig_analyze_following",
        allocation_key="alloc-browser",
        max_parallel_task_claims=4,
        execution_context={"playbook_code": "ig_analyze_following"},
    )

    row = store.fetch_task_row("quota-cold-1")
    assert released is True
    assert store.fetch_frontier("quota-cold-1") == "ready"
    assert row.blocked_reason is None
    assert row.blocked_payload is None
    assert store.deserialize_json(row.execution_context) == {
        "playbook_code": "ig_analyze_following"
    }


def test_try_release_workspace_quota_task_blocks_same_selector_when_reserved_full():
    store = _SqliteClaimStore()
    store.insert_allocation(
        max_parallel_task_claims=4,
        queue_shard="browser_local",
        task_family="ig_browser_capture",
        selectors=["ig_analyze_following"],
    )
    for index in range(4):
        store.insert_task(
            task_id=f"ready-following-{index}",
            status=TaskStatus.PENDING.value,
            pack_id="ig_analyze_following",
            execution_context={"playbook_code": "ig_analyze_following"},
            concurrency_key=None,
            frontier_state="ready",
        )
    store.insert_task(
        task_id="quota-cold-1",
        status=TaskStatus.PENDING.value,
        pack_id="ig_analyze_following",
        execution_context={"playbook_code": "ig_analyze_following"},
        concurrency_key=None,
        blocked_reason="workspace_allocation_quota_exhausted",
        frontier_state="cold",
    )

    released = store.try_release_workspace_quota_task(
        "quota-cold-1",
        workspace_id="ws-1",
        queue_shard="browser_local",
        selectors=["ig_analyze_following"],
        task_selector="ig_analyze_following",
        allocation_key="alloc-browser",
        max_parallel_task_claims=4,
        execution_context={"playbook_code": "ig_analyze_following"},
    )

    assert released is False
    assert store.fetch_frontier("quota-cold-1") == "cold"


def test_try_release_workspace_quota_task_allows_one_missing_selector_candidate():
    store = _SqliteClaimStore()
    store.insert_allocation(
        max_parallel_task_claims=4,
        queue_shard="browser_local",
        task_family="ig_browser_capture",
        selectors=["ig_analyze_following"],
    )
    for index in range(4):
        store.insert_task(
            task_id=f"ready-detail-{index}",
            status=TaskStatus.PENDING.value,
            pack_id="ig_pin_post_detail",
            execution_context={"playbook_code": "ig_pin_post_detail"},
            queue_shard="default_local_browser",
            concurrency_key=None,
            frontier_state="ready",
        )
    store.insert_task(
        task_id="quota-cold-following",
        status=TaskStatus.PENDING.value,
        pack_id="ig_analyze_following",
        execution_context={"playbook_code": "ig_analyze_following"},
        concurrency_key=None,
        blocked_reason="workspace_allocation_quota_exhausted",
        frontier_state="cold",
    )

    released = store.try_release_workspace_quota_task(
        "quota-cold-following",
        workspace_id="ws-1",
        queue_shard="browser_local",
        selectors=["ig_analyze_following"],
        task_selector="ig_analyze_following",
        allocation_key="alloc-browser",
        max_parallel_task_claims=4,
        execution_context={"playbook_code": "ig_analyze_following"},
    )

    assert released is True
    assert store.fetch_frontier("quota-cold-following") == "ready"


def test_try_release_workspace_quota_task_moves_allocation_required_cold_task_to_ready():
    store = _SqliteClaimStore()
    store.insert_allocation(
        max_parallel_task_claims=1,
        queue_shard="decision_synthesis",
        task_family="decision_assets_synthesize",
        selectors=["decision_assets_synthesize"],
    )
    store.insert_task(
        task_id="decision-cold-1",
        status=TaskStatus.PENDING.value,
        pack_id="decision_assets_synthesize",
        execution_context={"playbook_code": "decision_assets_synthesize"},
        concurrency_key=None,
        queue_shard="decision_synthesis",
        task_type="playbook_execution",
        blocked_reason="workspace_allocation_required",
        frontier_state="cold",
    )

    released = store.try_release_workspace_quota_task(
        "decision-cold-1",
        workspace_id="ws-1",
        queue_shard="decision_synthesis",
        selectors=["decision_assets_synthesize"],
        task_selector="decision_assets_synthesize",
        allocation_key="alloc-decision",
        max_parallel_task_claims=1,
        execution_context={"playbook_code": "decision_assets_synthesize"},
    )

    row = store.fetch_task_row("decision-cold-1")
    assert released is True
    assert store.fetch_frontier("decision-cold-1") == "ready"
    assert row.blocked_reason is None
