import json
from pathlib import Path

from backend.app.services.runner_live_state import RunnerLiveStateStore


class _FakeCache:
    def __init__(self):
        self.values = {}
        self.ttls = {}
        self.deleted = []

    def set_json(self, key, value, ttl=None):
        self.values[key] = json.dumps(value)
        self.ttls[key] = ttl
        return True

    def get(self, key):
        return self.values.get(key)

    def delete(self, key):
        self.deleted.append(key)
        return bool(self.values.pop(key, None))


def test_runner_live_state_writes_task_and_runner_ttl_keys():
    cache = _FakeCache()
    store = RunnerLiveStateStore(cache_service=cache)

    ok = store.renew_task_heartbeat(
        task_id="task/001",
        runner_id="runner A",
        workspace_id="workspace-1",
        execution_id="exec-1",
        playbook_code="pack-a",
        queue_shard="default",
        ttl_seconds=45,
    )

    task_key = "mindscape:runner_live:task:task_001"
    runner_key = "mindscape:runner_live:runner:runner_A:task:task_001"
    assert ok is True
    assert cache.ttls[task_key] == 45
    assert cache.ttls[runner_key] == 45
    payload = json.loads(cache.values[task_key])
    assert payload["task_id"] == "task/001"
    assert payload["runner_id"] == "runner A"
    assert payload["execution_id"] == "exec-1"
    assert payload["heartbeat_at"]


def test_runner_live_state_can_clear_task_keys():
    cache = _FakeCache()
    store = RunnerLiveStateStore(cache_service=cache)
    store.renew_task_heartbeat(
        task_id="task-1",
        runner_id="runner-1",
        ttl_seconds=180,
    )

    assert store.clear_task_heartbeat(task_id="task-1", runner_id="runner-1") is True
    assert "mindscape:runner_live:task:task-1" in cache.deleted
    assert "mindscape:runner_live:runner:runner-1:task:task-1" in cache.deleted


def test_update_task_heartbeat_does_not_write_tasks_hot_row():
    source = (
        Path(__file__).resolve().parents[1]
        / "app/services/stores/tasks_store/_runner.py"
    ).read_text(encoding="utf-8")
    method_source = source.split("def update_task_heartbeat", maxsplit=1)[1].split(
        "def should_abort_task",
        maxsplit=1,
    )[0]

    assert "UPDATE tasks" not in method_source
    assert "heartbeat_at =" not in method_source
    assert "runner_id =" not in method_source


def test_task_executor_writes_runner_live_state_during_heartbeat():
    source = (
        Path(__file__).resolve().parents[1]
        / "app/runner/task_executor.py"
    ).read_text(encoding="utf-8")

    assert "RunnerLiveStateStore()" in source
    assert "renew_task_heartbeat" in source
    assert "clear_task_heartbeat" in source


def test_reaper_uses_runner_live_state_before_legacy_heartbeat():
    source = (
        Path(__file__).resolve().parents[1]
        / "app/runner/reaper.py"
    ).read_text(encoding="utf-8")

    assert "RunnerLiveStateStore" in source
    assert "get_task_heartbeat" in source
    assert "_effective_task_heartbeat_at(t, ctx, live_state_store)" in source
