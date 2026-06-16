import pytest

from backend.app.models.workspace import Task, TaskStatus, _utc_now
from backend.app.runner import reaper
from backend.tests.reaper_admission_release_support import (
    _FakeRedisQueue,
    _FakeTasksStore,
)


def test_blocked_release_limit_keeps_small_fairness_floor(monkeypatch):
    monkeypatch.setenv("LOCAL_CORE_RUNNER_BLOCKED_RELEASE_MINIMUM", "4")

    assert reaper._blocked_release_limit(ready_target=64, ready_depth=80) == 4
    assert reaper._blocked_release_limit(ready_target=64, ready_depth=60) == 4
    assert reaper._blocked_release_limit(ready_target=64, ready_depth=10) == 54


@pytest.mark.asyncio
async def test_browser_peer_frontier_refills_batch_and_detail_when_hot_queue_lacks_peer_lanes(monkeypatch):
    monkeypatch.setenv("LOCAL_CORE_RUNNER_BROWSER_PEER_REFILL_LIMIT", "4")
    now = _utc_now()
    tasks = [
        Task(
            id="task-following",
            workspace_id="ws-1",
            message_id="msg-following",
            execution_id="exec-following",
            pack_id="ig_analyze_following",
            task_type="playbook_execution",
            status=TaskStatus.PENDING,
            queue_shard="browser_local",
            created_at=now,
            next_eligible_at=now,
            frontier_state="ready",
            execution_context={"playbook_code": "ig_analyze_following"},
        ),
        Task(
            id="task-detail",
            workspace_id="ws-1",
            message_id="msg-detail",
            execution_id="exec-detail",
            pack_id="ig_pin_post_detail",
            task_type="playbook_execution",
            status=TaskStatus.PENDING,
            queue_shard="browser_local",
            created_at=now,
            next_eligible_at=now,
            frontier_state="ready",
            execution_context={"playbook_code": "ig_pin_post_detail"},
        ),
        Task(
            id="task-batch",
            workspace_id="ws-1",
            message_id="msg-batch",
            execution_id="exec-batch",
            pack_id="ig_batch_pin_references",
            task_type="playbook_execution",
            status=TaskStatus.PENDING,
            queue_shard="browser_local",
            created_at=now,
            next_eligible_at=now,
            frontier_state="ready",
            execution_context={"playbook_code": "ig_batch_pin_references"},
        ),
    ]
    store = _FakeTasksStore(tasks)
    queue = _FakeRedisQueue("browser_local")
    queue._client.pending_members = ["existing-following"]

    refilled = await reaper._refill_browser_peer_frontier(store, queue)

    assert refilled == 2
    assert queue._client.enqueued == ["task-detail", "task-batch"]
    assert [task_id for task_id, _update in store.updated] == [
        "task-detail",
        "task-batch",
    ]
    assert [update["frontier_state"] for _task_id, update in store.updated] == [
        "ready",
        "ready",
    ]
