from types import SimpleNamespace

import pytest

from backend.app.runner import resource_pressure
from backend.app.runner.task_executor import _mark_task_failed
from backend.app.models.workspace import TaskStatus


def _write(path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def test_runner_resource_snapshot_uses_cgroup_working_set(tmp_path, monkeypatch):
    monkeypatch.delenv("LOCAL_CORE_RUNNER_BROWSER_MEMORY_SOFT_RATIO", raising=False)
    monkeypatch.setenv("LOCAL_CORE_RUNNER_BROWSER_SESSION_MAX_ACTIVE", "2")
    resource_pressure._reset_resource_cooldown_for_tests()

    _write(tmp_path / "memory.current", "900")
    _write(tmp_path / "memory.max", "1000")
    _write(tmp_path / "memory.stat", "inactive_file 300\nanon 500\n")
    _write(tmp_path / "pids.current", "12")
    _write(tmp_path / "pids.max", "max")

    snapshot = resource_pressure.build_runner_resource_snapshot(
        profile_code="runner-browser",
        inflight=1,
        cgroup_root=tmp_path,
        now_epoch=100.0,
    )

    assert snapshot["memory"]["working_set_bytes"] == 600
    assert snapshot["memory"]["working_set_ratio"] == 0.6
    assert snapshot["pids"]["limit"] is None
    assert snapshot["admission"]["state"] == "normal"
    assert snapshot["admission"]["should_defer"] is False


def test_runner_resource_pressure_defers_when_browser_session_slots_are_full(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("LOCAL_CORE_RUNNER_BROWSER_SESSION_MAX_ACTIVE", "1")
    resource_pressure._reset_resource_cooldown_for_tests()

    _write(tmp_path / "memory.current", "100")
    _write(tmp_path / "memory.max", "1000")
    _write(tmp_path / "memory.stat", "inactive_file 0\n")
    _write(tmp_path / "pids.current", "12")
    _write(tmp_path / "pids.max", "max")

    snapshot = resource_pressure.build_runner_resource_snapshot(
        profile_code="runner-browser",
        inflight=1,
        cgroup_root=tmp_path,
        now_epoch=100.0,
    )

    assert snapshot["admission"]["state"] == "soft_defer"
    assert snapshot["admission"]["should_defer"] is True
    assert snapshot["admission"]["reasons"] == ["browser_session_slots"]
    assert snapshot["admission"]["browser_session_max_active"] == 1


def test_browser_session_default_follows_runner_max_inflight(tmp_path, monkeypatch):
    monkeypatch.delenv("LOCAL_CORE_RUNNER_BROWSER_SESSION_MAX_ACTIVE", raising=False)
    resource_pressure._reset_resource_cooldown_for_tests()

    _write(tmp_path / "memory.current", "100")
    _write(tmp_path / "memory.max", "1000")
    _write(tmp_path / "memory.stat", "inactive_file 0\n")
    _write(tmp_path / "pids.current", "12")
    _write(tmp_path / "pids.max", "max")

    snapshot = resource_pressure.build_runner_resource_snapshot(
        profile_code="runner-browser",
        inflight=1,
        max_inflight=2,
        available_slots=1,
        cgroup_root=tmp_path,
        now_epoch=100.0,
    )

    assert snapshot["admission"]["state"] == "normal"
    assert snapshot["admission"]["should_defer"] is False
    assert snapshot["admission"]["browser_session_max_active"] == 2


def test_runner_resource_pressure_enters_cooldown(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCAL_CORE_RUNNER_BROWSER_MEMORY_HARD_RATIO", "0.90")
    monkeypatch.setenv("LOCAL_CORE_RUNNER_BROWSER_RESOURCE_COOLDOWN_SECONDS", "120")
    resource_pressure._reset_resource_cooldown_for_tests()

    _write(tmp_path / "memory.current", "950")
    _write(tmp_path / "memory.max", "1000")
    _write(tmp_path / "memory.stat", "inactive_file 0\n")

    snapshot = resource_pressure.build_runner_resource_snapshot(
        profile_code="runner-browser",
        cgroup_root=tmp_path,
        now_epoch=100.0,
    )
    assert snapshot["admission"]["state"] == "hard_cooldown"
    assert snapshot["admission"]["should_defer"] is True
    assert snapshot["admission"]["cooldown_until_epoch"] == 220.0

    _write(tmp_path / "memory.current", "100")
    cooled_snapshot = resource_pressure.build_runner_resource_snapshot(
        profile_code="runner-browser",
        cgroup_root=tmp_path,
        now_epoch=101.0,
    )
    assert cooled_snapshot["admission"]["state"] == "cooldown"
    assert cooled_snapshot["admission"]["should_defer"] is True


def test_classify_subprocess_resource_failure():
    assert (
        resource_pressure.classify_subprocess_resource_failure(-9, "")
        == "subprocess_sigkill"
    )
    assert (
        resource_pressure.classify_subprocess_resource_failure(
            1,
            "Browser launch timed out after 60s",
        )
        == "browser_launch_timeout"
    )
    assert (
        resource_pressure.classify_subprocess_resource_failure(
            1,
            "Timed out waiting for IG browser resource lease",
        )
        == "browser_resource_lease"
    )


class _FakeTasksStore:
    def __init__(self):
        self.task = SimpleNamespace(
            id="task-1",
            status=TaskStatus.RUNNING,
            execution_context={"retry_count": 2},
            started_at=None,
        )
        self.update_kwargs = None

    def get_task(self, task_id):
        assert task_id == self.task.id
        return self.task

    def update_task(self, task_id, **kwargs):
        assert task_id == self.task.id
        self.update_kwargs = kwargs
        self.task.status = kwargs["status"]
        self.task.execution_context = kwargs["execution_context"]
        return self.task


class _FakeRedisQueue:
    def __init__(self):
        self.delayed = None
        self.deadlettered = False
        self.acked = False

    async def nack_task_to_delayed(self, task_id, delay_sec=15):
        self.delayed = (task_id, delay_sec)
        return True

    async def move_to_deadletter(self, task_id):
        self.deadlettered = True
        return True

    async def ack_task(self, task_id):
        self.acked = True
        return True


@pytest.mark.asyncio
async def test_browser_resource_lease_wait_does_not_consume_workflow_retry():
    store = _FakeTasksStore()
    queue = _FakeRedisQueue()

    await _mark_task_failed(
        store,
        "task-1",
        "runner-browser",
        "Timed out waiting for IG browser resource lease",
        queue,
        retry_delay_sec=300,
        resource_pressure_source="browser_resource_lease",
    )

    updated_context = store.update_kwargs["execution_context"]
    assert store.update_kwargs["status"] == TaskStatus.PENDING
    assert store.update_kwargs["frontier_state"] == "cold"
    assert store.update_kwargs["error"] is None
    assert updated_context["retry_count"] == 2
    assert updated_context["resource_wait_count"] == 1
    assert updated_context["resource_pressure_source"] == "browser_resource_lease"
    assert queue.delayed == ("task-1", 300)
    assert queue.deadlettered is False
    assert queue.acked is False


@pytest.mark.asyncio
async def test_subprocess_sigkill_resource_wait_clears_runner_ownership():
    store = _FakeTasksStore()
    store.task.execution_context = {
        "retry_count": 2,
        "runner_id": "previous-runner",
        "heartbeat_at": "2026-05-08T03:00:00+00:00",
    }
    queue = _FakeRedisQueue()

    await _mark_task_failed(
        store,
        "task-1",
        "runner-browser",
        "Runner subprocess exited with code -9",
        queue,
        retry_delay_sec=300,
        resource_pressure_source="subprocess_sigkill",
    )

    updated_context = store.update_kwargs["execution_context"]
    assert store.update_kwargs["status"] == TaskStatus.PENDING
    assert store.update_kwargs["frontier_state"] == "cold"
    assert store.update_kwargs["started_at"] is None
    assert updated_context["retry_count"] == 2
    assert updated_context["resource_wait_count"] == 1
    assert updated_context["resource_pressure_source"] == "subprocess_sigkill"
    assert updated_context["last_runner_id"] == "runner-browser"
    assert "runner_id" not in updated_context
    assert "heartbeat_at" not in updated_context
    assert queue.delayed == ("task-1", 300)
    assert queue.deadlettered is False
