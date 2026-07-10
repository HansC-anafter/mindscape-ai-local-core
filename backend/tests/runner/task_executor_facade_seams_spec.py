import asyncio
from types import SimpleNamespace

from backend.app.models.workspace import Task, TaskStatus, _utc_now
from backend.app.services.execution_intent_resolver import ExecutionIntentResolution
from backend.app.runner import task_executor


def _task() -> Task:
    return Task(
        id="task-1",
        workspace_id="ws-1",
        message_id="msg-1",
        execution_id="exec-1",
        pack_id="generic_playbook",
        task_type="playbook_execution",
        status=TaskStatus.RUNNING,
        params={},
        execution_context={"inputs": {}},
        created_at=_utc_now(),
    )


def test_task_executor_facade_exports_legacy_helpers():
    for name in (
        "_run_single_task",
        "_mark_task_failed",
        "_mark_task_succeeded",
        "_build_resource_failure_snapshot",
        "_child_execute_playbook",
        "_initialize_capability_packages_for_runner",
        "_get_task_control_signal",
        "_resolve_execution_attempt_inputs",
        "_apply_runtime_binding_to_playbook_task",
        "_park_task_after_intent_resolution",
        "_emit_run_state_changed_for_task",
    ):
        assert hasattr(task_executor, name)


def test_build_resource_failure_snapshot_uses_facade_snapshot_hook(monkeypatch):
    captured = {}

    monkeypatch.setenv("LOCAL_CORE_RUNNER_PROFILE", "browser_local")
    monkeypatch.setenv("LOCAL_CORE_RUNNER_MAX_INFLIGHT", "2")

    def fake_snapshot(**kwargs):
        captured.update(kwargs)
        return {"ok": True}

    monkeypatch.setattr(task_executor, "build_runner_resource_snapshot", fake_snapshot)

    assert task_executor._build_resource_failure_snapshot(inflight=1) == {"ok": True}
    assert captured["profile_code"] == "browser_local"
    assert captured["max_inflight"] == 2


def test_run_single_task_uses_facade_success_hook(monkeypatch):
    task = _task()
    marked = {}

    class FakeTasksStore:
        def get_task(self, task_id):
            return task

        def update_task(self, task_id, **kwargs):
            if "execution_context" in kwargs:
                task.execution_context = kwargs["execution_context"]
            if "status" in kwargs:
                task.status = kwargs["status"]

        def update_task_heartbeat(self, task_id, *, runner_id):
            return None

    class FakeProcess:
        pid = 101
        exitcode = 0

        def start(self):
            return None

        def is_alive(self):
            return False

        def join(self, timeout=None):
            return None

        def terminate(self):
            return None

        def kill(self):
            return None

    class FakeMpContext:
        def Process(self, target, args, daemon):
            return FakeProcess()

    async def fake_mark_succeeded(tasks_store, task_id, runner_id, result_file, redis_queue):
        marked["task_id"] = task_id

    monkeypatch.setattr(task_executor.mp, "get_context", lambda method: FakeMpContext())
    monkeypatch.setattr(
        task_executor,
        "_resolve_execution_attempt_inputs",
        lambda task, ctx: ({}, ExecutionIntentResolution(effective_inputs={})),
    )
    monkeypatch.setattr(
        task_executor,
        "_apply_runtime_binding_to_playbook_task",
        lambda task, ctx, inputs, profile_id: (inputs, ctx, object()),
    )
    monkeypatch.setattr(task_executor, "_mark_task_succeeded", fake_mark_succeeded)

    asyncio.run(
        task_executor._run_single_task(
            FakeTasksStore(),
            "runner-1",
            task.id,
            redis_queue=None,
            lock_owner_id="runner-1:task-1",
        )
    )

    assert marked == {"task_id": task.id}


def test_run_single_task_uses_facade_park_hook(monkeypatch):
    task = _task()
    parked = {}
    released = []

    class FakeTasksStore:
        def get_task(self, task_id):
            return task

    async def fake_park(tasks_store, task, runner_id, resolution, redis_queue):
        parked["task_id"] = task.id

    async def fake_release_locks(redis_queue, lock_keys, lock_owner_id):
        released.append(("locks", lock_owner_id))

    async def fake_release_leases(
        redis_queue,
        resource_lease_keys,
        lock_owner_id,
        node_budget_reservation=None,
    ):
        assert node_budget_reservation is None
        released.append(("leases", lock_owner_id))

    monkeypatch.setattr(
        task_executor,
        "_resolve_execution_attempt_inputs",
        lambda task, ctx: (
            {},
            ExecutionIntentResolution(
                effective_inputs={},
                park_task=True,
                blocked_reason="runtime_unavailable",
            ),
        ),
    )
    monkeypatch.setattr(task_executor, "_park_task_after_intent_resolution", fake_park)
    monkeypatch.setattr(task_executor, "_release_task_locks", fake_release_locks)
    monkeypatch.setattr(
        task_executor,
        "_release_task_resource_leases",
        fake_release_leases,
    )

    asyncio.run(
        task_executor._run_single_task(
            FakeTasksStore(),
            "runner-1",
            task.id,
            redis_queue=None,
            lock_owner_id="runner-1:task-1",
        )
    )

    assert parked == {"task_id": task.id}
    assert released == [("locks", "runner-1:task-1"), ("leases", "runner-1:task-1")]
