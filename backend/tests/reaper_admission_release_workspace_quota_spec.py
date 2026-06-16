import pytest

from backend.app.runner import reaper
from backend.tests.reaper_admission_release_support import (
    _FakeRedisQueue,
    _FakeTasksStore,
    _FakeWorkspaceQuotaDecision,
    _build_workspace_quota_task,
)


@pytest.mark.asyncio
async def test_releases_workspace_quota_task_only_with_available_reserved_capacity(
    monkeypatch,
):
    store = _FakeTasksStore(
        [
            _build_workspace_quota_task("quota_job_a"),
            _build_workspace_quota_task("quota_job_b"),
        ]
    )
    store.ready_workspace_quota_count = 2
    queue = _FakeRedisQueue("browser_local")
    monkeypatch.setattr(
        reaper,
        "decide_workspace_quota_admission_for_task",
        lambda _task: _FakeWorkspaceQuotaDecision(
            allow=True,
            active_count=1,
            max_parallel_task_claims=4,
        ),
    )

    released = await reaper._release_workspace_quota_tasks(
        store,
        queue,
        release_limit=4,
    )

    assert released == 1
    assert store.workspace_quota_calls == 1
    assert queue._client.enqueued == ["quota_job_a"]
    assert [task_id for task_id, _update in store.updated] == [
        "quota_job_a",
        "quota_job_b",
    ]
    released_update = store.updated[0][1]
    assert released_update["blocked_reason"] is None
    assert released_update["blocked_payload"] is None
    assert released_update["frontier_state"] == "ready"
    assert "workspace_quota_admission" not in released_update["execution_context"]
    assert "runner_claim_admission" not in released_update["execution_context"]
    assert "resume_after" not in released_update["execution_context"]
    blocked_update = store.updated[1][1]
    assert blocked_update["blocked_reason"] == "workspace_allocation_quota_exhausted"
    assert blocked_update["frontier_state"] == "cold"


@pytest.mark.asyncio
async def test_reextends_workspace_quota_task_when_reserved_capacity_is_full(
    monkeypatch,
):
    store = _FakeTasksStore([_build_workspace_quota_task()])
    store.ready_workspace_quota_count = 3
    queue = _FakeRedisQueue("browser_local")
    monkeypatch.setattr(
        reaper,
        "decide_workspace_quota_admission_for_task",
        lambda _task: _FakeWorkspaceQuotaDecision(
            allow=True,
            active_count=1,
            max_parallel_task_claims=4,
        ),
    )

    released = await reaper._release_workspace_quota_tasks(
        store,
        queue,
        release_limit=4,
    )

    assert released == 0
    assert queue._client.enqueued == []
    update = store.updated[0][1]
    assert update["blocked_reason"] == "workspace_allocation_quota_exhausted"
    assert update["frontier_state"] == "cold"
    assert update["blocked_payload"]["ready_pending_count"] == 3


@pytest.mark.asyncio
async def test_releases_workspace_allocation_required_task_when_allocation_becomes_available(
    monkeypatch,
):
    store = _FakeTasksStore(
        [_build_workspace_quota_task(blocked_reason="workspace_allocation_required")]
    )
    queue = _FakeRedisQueue("browser_local")
    monkeypatch.setattr(
        reaper,
        "decide_workspace_quota_admission_for_task",
        lambda _task: _FakeWorkspaceQuotaDecision(
            allow=True,
            active_count=0,
            max_parallel_task_claims=1,
        ),
    )

    released = await reaper._release_workspace_quota_tasks(
        store,
        queue,
        release_limit=1,
    )

    assert released == 1
    assert queue._client.enqueued == ["quota_job"]
    update = store.updated[0][1]
    assert update["blocked_reason"] is None
    assert update["frontier_state"] == "ready"
