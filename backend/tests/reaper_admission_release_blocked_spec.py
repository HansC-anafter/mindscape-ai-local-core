from types import SimpleNamespace

import pytest

from backend.app.runner import reaper
from backend.tests.reaper_admission_release_support import (
    _FakeRedisQueue,
    _FakeTasksStore,
    _build_concurrency_locked_task,
    _build_dependency_hold_task,
    _build_resource_wait_task,
    _build_unblocked_cold_task,
)


@pytest.mark.asyncio
async def test_releases_due_concurrency_locked_task_to_ready_queue():
    store = _FakeTasksStore([_build_concurrency_locked_task()])
    queue = _FakeRedisQueue("default_local_browser")

    released = await reaper._release_concurrency_locked_tasks(
        store,
        queue,
        release_limit=1,
    )

    assert released == 1
    assert store.concurrency_locked_calls == 1
    assert queue._client.enqueued == ["task-locked"]
    assert queue._client.operations == [("rpush", "task-locked")]
    assert store.updated[0][0] == "task-locked"
    update = store.updated[0][1]
    assert update["blocked_reason"] is None
    assert update["blocked_payload"] is None
    assert update["frontier_state"] == "ready"
    assert update["queue_shard"] == "default_local_browser"
    assert update["frontier_enqueued_at"] is not None
    assert "runner_skip_reason" not in update["execution_context"]
    assert "runner_skip_lock_key" not in update["execution_context"]
    assert "runner_skip_conflict_lock_key" not in update["execution_context"]
    assert "resume_after" not in update["execution_context"]


@pytest.mark.asyncio
async def test_releasing_concurrency_locked_candidate_without_loaded_context_preserves_db_context():
    task = _build_concurrency_locked_task(
        concurrency_key="concurrency:playbook_input:ig_batch_pin_references:profile-a"
    )
    task.execution_context = None
    store = _FakeTasksStore([task])
    queue = _FakeRedisQueue("browser_local")

    released = await reaper._release_concurrency_locked_tasks(
        store,
        queue,
        release_limit=1,
    )

    assert released == 1
    update = store.updated[0][1]
    assert update["blocked_reason"] is None
    assert update["frontier_state"] == "ready"
    assert "execution_context" not in update


@pytest.mark.asyncio
async def test_releases_one_due_concurrency_locked_task_per_lock_key():
    store = _FakeTasksStore(
        [
            _build_concurrency_locked_task(
                "task-locked-a",
                "concurrency:playbook:ig_analyze_pinned_reference",
            ),
            _build_concurrency_locked_task(
                "task-locked-b",
                "concurrency:playbook:ig_analyze_pinned_reference",
            ),
        ]
    )
    queue = _FakeRedisQueue("browser_local")

    released = await reaper._release_concurrency_locked_tasks(
        store,
        queue,
        release_limit=2,
    )

    assert released == 1
    assert queue._client.enqueued == ["task-locked-a"]
    assert [task_id for task_id, _update in store.updated] == ["task-locked-a"]


@pytest.mark.asyncio
async def test_releases_due_dependency_hold_task_to_ready_queue():
    store = _FakeTasksStore([_build_dependency_hold_task()])
    queue = _FakeRedisQueue("vision_local")

    released = await reaper._release_dependency_hold_tasks(
        store,
        queue,
        release_limit=1,
    )

    assert released == 1
    assert store.dependency_hold_calls == 1
    assert queue._client.enqueued == ["task-dependency"]
    assert queue._client.operations == [("rpush", "task-dependency")]
    update = store.updated[0][1]
    assert update["blocked_reason"] is None
    assert update["blocked_payload"] is None
    assert update["frontier_state"] == "ready"
    assert update["queue_shard"] == "vision_local"
    assert "dependency_hold" not in update["execution_context"]
    assert "resume_after" not in update["execution_context"]


@pytest.mark.asyncio
async def test_releasing_dependency_hold_candidate_without_loaded_context_preserves_db_context():
    task = _build_dependency_hold_task()
    task.execution_context = None
    store = _FakeTasksStore([task])
    queue = _FakeRedisQueue("vision_local")

    released = await reaper._release_dependency_hold_tasks(
        store,
        queue,
        release_limit=1,
    )

    assert released == 1
    update = store.updated[0][1]
    assert update["blocked_reason"] is None
    assert update["frontier_state"] == "ready"
    assert "execution_context" not in update


@pytest.mark.asyncio
async def test_releases_due_resource_wait_task_to_ready_queue():
    store = _FakeTasksStore([_build_resource_wait_task()])
    queue = _FakeRedisQueue("default_local_browser")

    released = await reaper._release_resource_wait_tasks(
        store,
        queue,
        release_limit=1,
    )

    assert released == 1
    assert store.resource_wait_calls == 1
    assert queue._client.enqueued == ["task-resource"]
    assert queue._client.operations == [("rpush", "task-resource")]
    update = store.updated[0][1]
    assert update["blocked_reason"] is None
    assert update["blocked_payload"] is None
    assert update["frontier_state"] == "ready"
    assert update["queue_shard"] == "default_local_browser"
    assert "resource_admission" not in update["execution_context"]
    assert "runner_resource_leases" not in update["execution_context"]
    assert "resume_after" not in update["execution_context"]


@pytest.mark.asyncio
async def test_reextends_resource_wait_when_host_advisor_still_blocks(monkeypatch):
    task = _build_resource_wait_task(
        requirements={
            "memory_mb": 12288,
            "vision_lane": "comfyui_runtime:flux2_klein_true_v2_q6_local",
            "cpu_weight": 4,
        }
    )
    store = _FakeTasksStore([task])
    queue = _FakeRedisQueue("browser_local")
    monkeypatch.setattr(
        reaper,
        "_host_resource_wait_still_blocked",
        lambda _ctx: SimpleNamespace(
            decision="defer",
            reason="insufficient_memory_headroom",
            payload={"blocking_consumers": ["mlx:qwen9b_4bit_vision"]},
        ),
    )

    released = await reaper._release_resource_wait_tasks(
        store,
        queue,
        release_limit=1,
    )

    assert released == 0
    assert queue._client.enqueued == []
    update = store.updated[0][1]
    assert update["blocked_reason"] == "resource_wait"
    assert update["frontier_state"] == "cold"
    assert update["blocked_payload"]["host_decision"] == "defer"
    assert update["execution_context"]["resource_admission"]["state"] == "waiting"


@pytest.mark.asyncio
async def test_releases_one_due_resource_wait_task_per_resource_key():
    resource_key = "mindscape:runner_resources:lease:v1:ig_profile_lock:profile:hash"
    store = _FakeTasksStore(
        [
            _build_resource_wait_task("task-resource-a", resource_key),
            _build_resource_wait_task("task-resource-b", resource_key),
        ]
    )
    queue = _FakeRedisQueue("browser_local")

    released = await reaper._release_resource_wait_tasks(
        store,
        queue,
        release_limit=2,
    )

    assert released == 1
    assert queue._client.enqueued == ["task-resource-a"]
    assert [task_id for task_id, _update in store.updated] == ["task-resource-a"]


@pytest.mark.asyncio
async def test_releases_due_unblocked_cold_task_to_ready_queue():
    store = _FakeTasksStore([_build_unblocked_cold_task()])
    queue = _FakeRedisQueue("vision_local")

    released = await reaper._release_unblocked_cold_tasks(
        store,
        queue,
        release_limit=1,
    )

    assert released == 1
    assert store.unblocked_cold_calls == 1
    assert queue._client.enqueued == ["task-cold"]
    update = store.updated[0][1]
    assert update["blocked_reason"] is None
    assert update["blocked_payload"] is None
    assert update["frontier_state"] == "ready"
    assert update["queue_shard"] == "vision_local"
