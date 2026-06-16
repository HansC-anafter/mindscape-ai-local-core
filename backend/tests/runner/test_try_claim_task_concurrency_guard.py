from backend.app.models.workspace import TaskStatus
from backend.tests.runner.try_claim_task_concurrency_guard_support import (
    _SqliteClaimStore,
    _following_ctx,
)


def test_try_claim_task_blocks_same_profile_running_conflict():
    store = _SqliteClaimStore()
    profile_dir = "/app/data/ig-browser-profiles/default"
    lock_key = f"ig_profile:{profile_dir}"
    store.insert_task(
        task_id="running-1",
        status=TaskStatus.RUNNING.value,
        pack_id="ig_analyze_following",
        execution_context=_following_ctx(profile_dir),
        concurrency_key=lock_key,
    )
    store.insert_task(
        task_id="pending-1",
        status=TaskStatus.PENDING.value,
        pack_id="ig_analyze_following",
        execution_context=_following_ctx(profile_dir),
        concurrency_key=lock_key,
    )

    claimed = store.try_claim_task("pending-1", runner_id="runner-a")

    assert claimed is False
    assert store.fetch_status("pending-1") == TaskStatus.PENDING.value


def test_try_claim_task_allows_distinct_profile():
    store = _SqliteClaimStore()
    default_dir = "/app/data/ig-browser-profiles/default"
    walto_dir = "/app/data/ig-browser-profiles/walto_lab"
    store.insert_task(
        task_id="running-1",
        status=TaskStatus.RUNNING.value,
        pack_id="ig_analyze_following",
        execution_context=_following_ctx(default_dir),
        concurrency_key=f"ig_profile:{default_dir}",
    )
    store.insert_task(
        task_id="pending-1",
        status=TaskStatus.PENDING.value,
        pack_id="ig_analyze_following",
        execution_context=_following_ctx(walto_dir),
        concurrency_key=f"ig_profile:{walto_dir}",
    )

    claimed = store.try_claim_task("pending-1", runner_id="runner-a")

    assert claimed is True
    assert store.fetch_status("pending-1") == TaskStatus.RUNNING.value
