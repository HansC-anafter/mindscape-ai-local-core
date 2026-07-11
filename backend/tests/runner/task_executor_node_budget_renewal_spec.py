import asyncio
from threading import Event
from types import SimpleNamespace

import pytest

from backend.app.runner.task_executor_heartbeat import start_heartbeat_thread
from backend.app.runner.task_executor_runtime import (
    _renew_node_budget_before_child,
)
from backend.app.services.runner_resources import NodeBudgetReservation


def _reservation() -> NodeBudgetReservation:
    return NodeBudgetReservation(
        owner_id="runner-a:task-1",
        bytes=1024,
        revision=7,
        expires_at_epoch=1000.0,
        policy_fingerprint="policy",
        resource_profile_fingerprint="profile",
        allocatable_bytes=4096,
        policy_mode="calibrated",
    )


class _RedisClient:
    def __init__(self, result: int):
        self.result = result
        self.eval_calls = []

    async def eval(self, *args):
        self.eval_calls.append(args)
        return self.result


class _Queue:
    def __init__(self, client: _RedisClient):
        self.client = client

    async def _get_client(self):
        return self.client

    async def touch_visibility_timeout(self, *_args, **_kwargs):
        raise AssertionError("live visibility must follow node renewal")


@pytest.mark.asyncio
async def test_prelaunch_node_budget_renew_requires_exact_redis_owner():
    accepted_client = _RedisClient(1)
    rejected_client = _RedisClient(0)

    assert await _renew_node_budget_before_child(
        _Queue(accepted_client),
        _reservation(),
        ttl_seconds=120,
    ) is True
    assert await _renew_node_budget_before_child(
        _Queue(rejected_client),
        _reservation(),
        ttl_seconds=120,
    ) is False
    assert await _renew_node_budget_before_child(
        None,
        _reservation(),
        ttl_seconds=120,
    ) is False
    assert len(accepted_client.eval_calls) == 1
    assert len(rejected_client.eval_calls) == 1


@pytest.mark.asyncio
async def test_primary_heartbeat_fences_before_live_publish_when_renew_fails():
    class TasksStore:
        def update_task_heartbeat(self, *_args, **_kwargs):
            raise AssertionError("DB heartbeat must follow node renewal")

    class LiveState:
        def renew_task_heartbeat(self, **_kwargs):
            raise AssertionError("live heartbeat must follow node renewal")

    queue = _Queue(_RedisClient(0))
    ownership_lost = Event()
    thread = start_heartbeat_thread(
        asyncio_module=asyncio,
        main_loop=asyncio.get_running_loop(),
        stop_event=Event(),
        task=SimpleNamespace(
            id="task-1",
            pack_id="ig_pin_post_detail",
            workspace_id="workspace-1",
            execution_id="execution-1",
            queue_shard="browser_local",
        ),
        tasks_store=TasksStore(),
        runner_id="runner-a",
        redis_queue=queue,
        runner_live_state=LiveState(),
        node_budget_reservation=_reservation(),
        ownership_lost_event=ownership_lost,
        node_budget_ttl_seconds=120,
        heartbeat_interval_ms=15_000,
        heartbeat_ttl_seconds=60,
        trace_heartbeat=False,
        proc_ref=[None],
    )

    for _ in range(20):
        if ownership_lost.is_set():
            break
        await asyncio.sleep(0.01)
    thread.join(timeout=1)

    assert ownership_lost.is_set() is True
    assert thread.is_alive() is False
    assert len(queue.client.eval_calls) == 1
