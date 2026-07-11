import asyncio
from threading import Event
from types import SimpleNamespace

import pytest

from backend.app.runner.task_executor_heartbeat import start_lease_renew_thread
from backend.app.runner.task_executor_runtime_cleanup import handle_control_signal


class _ImmediateFuture:
    def __init__(self, coroutine, value):
        self.coroutine = coroutine
        self.value = value

    def result(self, timeout=None):
        self.coroutine.close()
        return self.value


class _AsyncioSubmitFalse:
    @staticmethod
    def run_coroutine_threadsafe(coroutine, _loop):
        return _ImmediateFuture(coroutine, False)


@pytest.mark.asyncio
async def test_false_lock_renewal_sets_ownership_loss_and_stops_thread():
    class Queue:
        async def renew_lock(self, **_kwargs):
            return False

    stop_event = Event()
    ownership_lost = Event()
    thread = start_lease_renew_thread(
        asyncio_module=_AsyncioSubmitFalse,
        main_loop=object(),
        stop_event=stop_event,
        task=SimpleNamespace(id="task-1", pack_id="ig_batch_pin_references"),
        redis_queue=Queue(),
        lock_keys=["lock-1"],
        resource_lease_keys=[],
        ownership_lost_event=ownership_lost,
        lock_owner_id="runner-a:task-1",
        lock_ttl_seconds=120,
        heartbeat_interval_ms=15000,
    )
    thread.join(timeout=1)

    assert ownership_lost.is_set() is True
    assert thread.is_alive() is False


@pytest.mark.asyncio
async def test_ownership_loss_fences_child_before_recording_block():
    events = []

    class Process:
        alive = True

        def is_alive(self):
            return self.alive

        def terminate(self):
            events.append("terminate")

        def join(self, timeout=None):
            events.append("join")

        def kill(self):
            events.append("kill")
            self.alive = False

    class Hooks:
        asyncio_module = asyncio

        async def mark_task_failed(self, *_args, **kwargs):
            assert process.is_alive() is False
            assert kwargs["resource_pressure_source"] == "resource_ownership_lost"
            events.append("mark_blocked")

        def emit_run_state_changed_for_task(self, *_args, **_kwargs):
            raise AssertionError("unexpected terminal event")

    class Store:
        def get_task(self, _task_id):
            return SimpleNamespace(status="running")

    class ControlTask:
        def result(self):
            return {"kind": "resource_ownership_lost"}

    process = Process()
    exec_task = asyncio.create_task(asyncio.sleep(60))
    timeout_task = asyncio.create_task(asyncio.sleep(60))
    await handle_control_signal(
        Hooks(),
        Store(),
        SimpleNamespace(id="task-1", pack_id="ig_batch_pin_references"),
        "runner-a",
        None,
        process,
        exec_task,
        timeout_task,
        ControlTask(),
    )

    assert events == ["terminate", "join", "kill", "join", "mark_blocked"]
