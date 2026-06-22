from backend.app.models.workspace import TaskStatus
from backend.tests.runner.try_claim_task_concurrency_guard_support import (
    _SqliteClaimStore,
    _following_ctx,
    _pinned_reference_ctx,
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


def test_update_task_heartbeat_only_reads_abort_state():
    store = _SqliteClaimStore()
    store.insert_task(
        task_id="running-1",
        status=TaskStatus.RUNNING.value,
        pack_id="ig_pin_post_detail",
        execution_context={"status": "running"},
        queue_shard="default_local_browser",
        concurrency_key="profile:nagomi_art",
        blocked_reason="concurrency_locked",
    )

    should_abort = store.update_task_heartbeat("running-1", runner_id="runner-a")

    row = store.fetch_task_row("running-1")
    ctx = store.deserialize_json(row.execution_context)
    assert should_abort is False
    assert row.status == TaskStatus.RUNNING.value
    assert row.runner_id is None
    assert row.heartbeat_at is None
    assert row.blocked_reason == "concurrency_locked"
    assert row.blocked_payload is None
    assert ctx["status"] == "running"
    assert "runner_id" not in ctx
    assert "heartbeat_at" not in ctx
    assert "runner_heartbeat_at" not in ctx


def test_try_claim_task_blocks_pinned_reference_playbook_scope():
    store = _SqliteClaimStore()
    lock_key = "concurrency:playbook:ig_analyze_pinned_reference"
    store.insert_task(
        task_id="running-pinned",
        status=TaskStatus.RUNNING.value,
        pack_id="ig",
        execution_context=_pinned_reference_ctx("ref-a"),
        concurrency_key=lock_key,
    )
    store.insert_task(
        task_id="pending-pinned",
        status=TaskStatus.PENDING.value,
        pack_id="ig",
        execution_context=_pinned_reference_ctx("ref-b"),
        concurrency_key=lock_key,
    )

    claimed = store.try_claim_task("pending-pinned", runner_id="runner-a")

    assert claimed is False
    assert store.fetch_status("pending-pinned") == TaskStatus.PENDING.value
