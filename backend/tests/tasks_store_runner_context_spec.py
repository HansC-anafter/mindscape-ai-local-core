from datetime import datetime, timedelta, timezone
import inspect
from types import SimpleNamespace

import backend.app.services.stores.tasks_store._runner as runner_module
from backend.app.services.stores.tasks_store._runner import (
    _build_claim_execution_context,
    _normalize_concurrency_keys,
    _running_concurrency_conflict_clause,
    TasksStoreRunnerMixin,
)


class _FakeTasksStore(TasksStoreRunnerMixin):
    def __init__(self, tasks):
        self._tasks = tasks
        self.status_updates = []

    def list_tasks_by_workspace(self, workspace_id=None, status=None):
        return self._tasks

    def update_task_status(self, **kwargs):
        self.status_updates.append(kwargs)
        for task in self._tasks:
            if task.id == kwargs["task_id"]:
                task.status = kwargs["status"]
                task.error = kwargs.get("error")
                task.completed_at = kwargs.get("completed_at")


def _running_task(task_id, *, heartbeat_at, started_at):
    return SimpleNamespace(
        id=task_id,
        execution_context={
            "runner_id": "runner-a",
            "heartbeat_at": heartbeat_at.isoformat()
            if isinstance(heartbeat_at, datetime)
            else heartbeat_at,
        },
        heartbeat_at=heartbeat_at,
        started_at=started_at,
        created_at=started_at,
        status=runner_module.TaskStatus.RUNNING,
        error=None,
        completed_at=None,
    )


def test_claim_context_clears_stale_deferred_metadata():
    now = datetime(2026, 5, 8, 3, 30, tzinfo=timezone.utc)

    ctx = _build_claim_execution_context(
        {
            "inputs": {"target_handle": "example"},
            "retry_count": 2,
            "resource_wait_count": 1,
            "resource_pressure_source": "subprocess_sigkill",
            "resource_pressure": True,
            "resource_retry_delay_sec": 300,
            "resource_snapshot": {"memory": {"working_set_ratio": 0.91}},
            "runner_id": "old-runner",
            "heartbeat_at": "2026-05-08T03:00:00+00:00",
            "resume_after": "2026-05-08T03:05:00+00:00",
            "runner_skip_reason": "concurrency_locked",
            "error": "previous failure",
            "failed_at": "2026-05-08T03:00:01+00:00",
        },
        task_params={"target_handle": "from-params"},
        runner_id="new-runner",
        now=now,
    )

    assert ctx["inputs"] == {"target_handle": "example"}
    assert ctx["retry_count"] == 2
    assert ctx["resource_wait_count"] == 1
    assert ctx["runner_id"] == "new-runner"
    assert ctx["heartbeat_at"] == "2026-05-08T03:30:00+00:00"
    assert ctx["status"] == "running"

    for stale_key in (
        "resource_pressure_source",
        "resource_pressure",
        "resource_retry_delay_sec",
        "resource_snapshot",
        "resume_after",
        "runner_skip_reason",
        "error",
        "failed_at",
    ):
        assert stale_key not in ctx


def test_claim_context_restores_missing_inputs_from_params():
    now = datetime(2026, 5, 8, 3, 30, tzinfo=timezone.utc)

    ctx = _build_claim_execution_context(
        {
            "runner_skip_reason": "concurrency_locked",
            "resume_after": "2026-05-08T03:05:00+00:00",
        },
        task_params={
            "workspace_id": "ws-1",
            "reference_id": "ref_1",
            "analysis_profile": "visual_anatomy",
        },
        runner_id="runner-a",
        now=now,
    )

    assert ctx["inputs"]["workspace_id"] == "ws-1"
    assert ctx["inputs"]["reference_id"] == "ref_1"
    assert ctx["inputs"]["analysis_profile"] == "visual_anatomy"
    assert "runner_skip_reason" not in ctx
    assert "resume_after" not in ctx


def test_concurrency_conflict_clause_targets_running_control_rows():
    keys = _normalize_concurrency_keys(
        [
            " concurrency:playbook:ig_analyze_pinned_reference ",
            "concurrency:playbook:ig_analyze_pinned_reference",
            "concurrency:playbook:other",
            "",
            None,
        ]
    )

    clause, params = _running_concurrency_conflict_clause(keys)

    assert keys == [
        "concurrency:playbook:ig_analyze_pinned_reference",
        "concurrency:playbook:other",
    ]
    assert "AND NOT EXISTS" in clause
    assert "running_task.status = :running_status" in clause
    assert "running_task.concurrency_key IN" in clause
    assert params == {
        "concurrency_key_0": "concurrency:playbook:ig_analyze_pinned_reference",
        "concurrency_key_1": "concurrency:playbook:other",
    }


def test_update_task_heartbeat_is_abort_check_only_source_guard():
    source = inspect.getsource(TasksStoreRunnerMixin.update_task_heartbeat)

    assert "SELECT status, error" in source
    assert "UPDATE tasks" not in source
    assert "heartbeat_at =" not in source
    assert "runner_id =" not in source


def test_reap_zombie_tasks_reads_runner_live_state_before_db_heartbeat():
    source = inspect.getsource(TasksStoreRunnerMixin.reap_zombie_tasks)

    assert "RunnerLiveStateStore()" in source
    assert "_effective_runner_heartbeat_at(task, ctx, live_state_store)" in source


def test_reap_zombie_tasks_keeps_running_task_with_fresh_live_heartbeat(monkeypatch):
    now = datetime.now(timezone.utc)
    stale_at = now - timedelta(minutes=20)
    task = _running_task("task-live", heartbeat_at=stale_at, started_at=stale_at)

    class FreshLiveStateStore:
        def get_task_heartbeat(self, task_id):
            assert task_id == "task-live"
            return {"heartbeat_at": now.isoformat()}

    monkeypatch.setattr(runner_module, "RunnerLiveStateStore", FreshLiveStateStore)

    store = _FakeTasksStore([task])
    reaped_tasks = []

    assert store.reap_zombie_tasks(
        heartbeat_ttl_minutes=10,
        on_reaped=reaped_tasks.append,
    ) == []
    assert store.status_updates == []
    assert reaped_tasks == []
    assert task.status == runner_module.TaskStatus.RUNNING


def test_reap_zombie_tasks_fails_stale_task_without_live_heartbeat(monkeypatch):
    now = datetime.now(timezone.utc)
    stale_at = now - timedelta(minutes=20)
    task = _running_task("task-stale", heartbeat_at=stale_at, started_at=stale_at)

    class MissingLiveStateStore:
        def get_task_heartbeat(self, task_id):
            assert task_id == "task-stale"
            return None

    monkeypatch.setattr(runner_module, "RunnerLiveStateStore", MissingLiveStateStore)

    store = _FakeTasksStore([task])
    reaped_tasks = []

    assert store.reap_zombie_tasks(
        heartbeat_ttl_minutes=10,
        on_reaped=reaped_tasks.append,
    ) == ["task-stale"]
    assert store.status_updates[0]["task_id"] == "task-stale"
    assert store.status_updates[0]["status"] == runner_module.TaskStatus.FAILED
    assert "Zombie: heartbeat stale" in store.status_updates[0]["error"]
    assert reaped_tasks == [task]
    assert task.status == runner_module.TaskStatus.FAILED


def test_try_claim_task_keeps_single_control_state_transition():
    source = inspect.getsource(TasksStoreRunnerMixin.try_claim_task)

    assert "UPDATE tasks" in source
    assert "SET status = :running_status" in source
    assert "runner_id = :runner_id" in source
    assert "frontier_state = :frontier_state" in source
    assert "blocked_payload = NULL" in source
    assert source.count("UPDATE tasks") == 1
