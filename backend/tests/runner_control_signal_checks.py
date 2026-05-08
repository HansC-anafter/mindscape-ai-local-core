import pytest

from backend.app.models.workspace import Task, TaskStatus, _utc_now
from backend.app.runner import task_executor
from backend.app.runner.task_executor import _get_task_control_signal
from backend.app.services.execution_intent_resolver import ExecutionIntentResolution


def _task(status: TaskStatus, *, error: str = "", execution_context=None) -> Task:
    return Task(
        id="task-1",
        workspace_id="ws-1",
        message_id="msg-1",
        execution_id="exec-1",
        pack_id="generic_playbook",
        task_type="playbook_execution",
        status=status,
        params={},
        execution_context=execution_context or {},
        created_at=_utc_now(),
    )


def test_failed_status_does_not_abort_owned_subprocess_cleanup():
    signal = _get_task_control_signal(
        _task(TaskStatus.FAILED, error="Workflow completed with step errors")
    )

    assert signal is None


def test_user_cancel_still_aborts_runner_subprocess():
    signal = _get_task_control_signal(
        _task(TaskStatus.CANCELLED_BY_USER, error="Cancelled by user")
    )

    assert signal == {"kind": "cancelled", "message": "Cancelled by user"}


def test_watchdog_abort_still_controls_runner_subprocess():
    signal = _get_task_control_signal(
        _task(
            TaskStatus.RUNNING,
            execution_context={
                "watchdog_abort_requested_at": _utc_now().isoformat(),
                "watchdog_abort_reason": "No semantic progress",
            },
        )
    )

    assert signal == {"kind": "watchdog_abort", "message": "No semantic progress"}


@pytest.mark.asyncio
async def test_trace_heartbeat_context_does_not_abort_after_subprocess_start(monkeypatch):
    task = _task(
        TaskStatus.RUNNING,
        execution_context={"trace_runner_heartbeat": True, "inputs": {}},
    )
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
        pid = 1234
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

    async def _mark_succeeded(tasks_store, task_id, runner_id, result_file, redis_queue):
        marked["task_id"] = task_id

    monkeypatch.setattr(task_executor, "_mark_task_succeeded", _mark_succeeded)

    await task_executor._run_single_task(
        FakeTasksStore(),
        "runner-1",
        task.id,
        redis_queue=None,
        lock_owner_id="runner-1:task-1",
    )

    assert marked == {"task_id": task.id}


@pytest.mark.asyncio
async def test_unexpected_orchestration_error_waits_for_live_subprocess(monkeypatch):
    task = _task(
        TaskStatus.RUNNING,
        execution_context={"inputs": {}},
    )
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
        pid = 4321
        exitcode = 0

        def __init__(self):
            self.alive_checks = 0
            self.killed = False

        def start(self):
            return None

        def is_alive(self):
            self.alive_checks += 1
            return self.alive_checks == 1

        def join(self, timeout=None):
            return None

        def terminate(self):
            return None

        def kill(self):
            self.killed = True

    fake_process = FakeProcess()

    class FakeMpContext:
        def Process(self, target, args, daemon):
            return fake_process

    async def fail_wait(*args, **kwargs):
        raise RuntimeError("orchestration interrupted")

    async def _mark_succeeded(tasks_store, task_id, runner_id, result_file, redis_queue):
        marked["task_id"] = task_id

    monkeypatch.setattr(task_executor.mp, "get_context", lambda method: FakeMpContext())
    monkeypatch.setattr(task_executor.asyncio, "wait", fail_wait)
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
    monkeypatch.setattr(task_executor, "_mark_task_succeeded", _mark_succeeded)

    with pytest.raises(RuntimeError, match="orchestration interrupted"):
        await task_executor._run_single_task(
            FakeTasksStore(),
            "runner-1",
            task.id,
            redis_queue=None,
            lock_owner_id="runner-1:task-1",
        )

    assert marked == {"task_id": task.id}
    assert fake_process.killed is False
