from types import SimpleNamespace
from threading import Event

import backend.app.runner.task_executor_heartbeat as heartbeat

from backend.app.runner.task_executor_heartbeat import (
    _LOOP_TIMEOUT_EXIT_CODE,
    _handle_loop_future_timeout,
    start_heartbeat_thread,
    start_lease_renew_thread,
)


def _task():
    return SimpleNamespace(id="task-1", pack_id="ig_pin_post_detail")


def test_loop_future_timeout_waits_until_threshold():
    exits = []

    _handle_loop_future_timeout(
        kind="lease renew",
        task=_task(),
        owner_id="runner-1:task-1",
        consecutive_timeouts=2,
        threshold=3,
        exit_enabled=True,
        exit_func=exits.append,
    )

    assert exits == []


def test_loop_future_timeout_exits_at_threshold():
    exits = []

    _handle_loop_future_timeout(
        kind="lease renew",
        task=_task(),
        owner_id="runner-1:task-1",
        consecutive_timeouts=3,
        threshold=3,
        exit_enabled=True,
        exit_func=exits.append,
    )

    assert exits == [_LOOP_TIMEOUT_EXIT_CODE]


def test_loop_future_timeout_respects_disabled_exit():
    exits = []

    _handle_loop_future_timeout(
        kind="visibility heartbeat",
        task=_task(),
        owner_id="runner-1",
        consecutive_timeouts=3,
        threshold=3,
        exit_enabled=False,
        exit_func=exits.append,
    )

    assert exits == []


class _TimeoutFuture:
    def result(self, *, timeout):
        raise TimeoutError()


class _TimeoutAsyncio:
    @staticmethod
    def run_coroutine_threadsafe(coroutine, loop):
        coroutine.close()
        return _TimeoutFuture()


class _StopAfterWait:
    def __init__(self):
        self.stopped = False

    def is_set(self):
        return self.stopped

    def wait(self, timeout):
        self.stopped = True
        return True


def test_single_node_budget_future_timeout_does_not_lose_ownership(
    monkeypatch,
):
    class _NodeBudgetStore:
        def __init__(self, redis_queue):
            pass

        async def renew(self, reservation, *, ttl_seconds):
            return True

    class _TasksStore:
        @staticmethod
        def update_task_heartbeat(task_id, *, runner_id):
            return True

    monkeypatch.setattr(heartbeat, "RedisNodeBudgetStore", _NodeBudgetStore)
    ownership_lost = Event()
    stop_event = Event()
    task = SimpleNamespace(
        id="task-1",
        pack_id="ig_pin_post_detail",
        workspace_id="workspace-1",
        execution_id="execution-1",
        queue_shard="browser_local",
    )
    reservation = SimpleNamespace(
        owner_id="runner-1:task-1",
        revision=1,
    )

    thread = start_heartbeat_thread(
        asyncio_module=_TimeoutAsyncio,
        main_loop=object(),
        stop_event=stop_event,
        task=task,
        tasks_store=_TasksStore(),
        runner_id="runner-1",
        redis_queue=SimpleNamespace(),
        runner_live_state=SimpleNamespace(),
        node_budget_reservation=reservation,
        ownership_lost_event=ownership_lost,
        node_budget_ttl_seconds=3600,
        heartbeat_interval_ms=1,
        heartbeat_ttl_seconds=60,
        trace_heartbeat=False,
        proc_ref=[None],
    )
    thread.join(timeout=1)

    assert not thread.is_alive()
    assert stop_event.is_set()
    assert not ownership_lost.is_set()


def test_single_lease_future_timeout_does_not_lose_ownership():
    class _RedisQueue:
        async def renew_lock(self, **kwargs):
            return True

    stop_event = _StopAfterWait()
    ownership_lost = Event()
    thread = start_lease_renew_thread(
        asyncio_module=_TimeoutAsyncio,
        main_loop=object(),
        stop_event=stop_event,
        task=_task(),
        redis_queue=_RedisQueue(),
        lock_keys=["lock-1"],
        resource_lease_keys=[],
        ownership_lost_event=ownership_lost,
        lock_owner_id="runner-1:task-1",
        lock_ttl_seconds=3600,
        heartbeat_interval_ms=1,
    )
    assert thread is not None
    thread.join(timeout=1)

    assert not thread.is_alive()
    assert stop_event.is_set()
    assert not ownership_lost.is_set()
