import pytest

from backend.app.runner import db_pool_pressure, worker_maintenance


class _NoDbQueue:
    async def _get_client(self):
        raise AssertionError("DB/Redis client path must not run")


@pytest.mark.asyncio
async def test_paused_gate_skips_leader_and_database(monkeypatch):
    monkeypatch.setattr(worker_maintenance, "_worker_facade", lambda: None)
    monkeypatch.setattr(
        worker_maintenance,
        "_runner_claim_gate_paused",
        lambda: (True, {"reason": "recovery", "source": "redis"}),
    )

    async def _unexpected_leader(*args, **kwargs):
        raise AssertionError("leadership must not be touched while gate is paused")

    monkeypatch.setattr(
        worker_maintenance,
        "try_hold_maintenance_leadership",
        _unexpected_leader,
    )
    monkeypatch.setattr(
        worker_maintenance,
        "try_hold_partition_maintenance_leadership",
        _unexpected_leader,
    )

    ran = await worker_maintenance._run_maintenance_cycle(
        object(),
        runner_id="runner-a",
        redis_queue=_NoDbQueue(),
        ready_queues={},
        ready_targets={},
        queue_cycle=[],
    )

    assert ran is False


@pytest.mark.asyncio
async def test_nonleader_skips_database_and_reaper(monkeypatch):
    monkeypatch.setattr(worker_maintenance, "_worker_facade", lambda: None)
    monkeypatch.setattr(
        worker_maintenance,
        "_runner_claim_gate_paused",
        lambda: (False, {"state": "open"}),
    )

    async def _not_leader(*args, **kwargs):
        return False

    monkeypatch.setattr(
        worker_maintenance,
        "try_hold_maintenance_leadership",
        _not_leader,
    )
    monkeypatch.setattr(
        worker_maintenance,
        "try_hold_partition_maintenance_leadership",
        _not_leader,
    )

    ran = await worker_maintenance._run_maintenance_cycle(
        object(),
        runner_id="runner-b",
        redis_queue=_NoDbQueue(),
        ready_queues={},
        ready_targets={},
        queue_cycle=[],
    )

    assert ran is False


@pytest.mark.asyncio
async def test_partition_leader_reaps_only_owned_partition(monkeypatch):
    monkeypatch.setattr(worker_maintenance, "_worker_facade", lambda: None)
    monkeypatch.setattr(
        worker_maintenance,
        "_runner_claim_gate_paused",
        lambda: (False, {"state": "open"}),
    )

    async def _not_global(*_args, **_kwargs):
        return False

    async def _partition_owner(*_args, **kwargs):
        return kwargs["queue_partition"] == "default_local_browser"

    calls = {"global": 0, "queues": []}
    monkeypatch.setattr(
        worker_maintenance,
        "try_hold_maintenance_leadership",
        _not_global,
    )
    monkeypatch.setattr(
        worker_maintenance,
        "try_hold_partition_maintenance_leadership",
        _partition_owner,
    )
    monkeypatch.setattr(
        worker_maintenance,
        "_reap_stale_running_tasks",
        lambda *_args, **_kwargs: calls.__setitem__("global", calls["global"] + 1),
    )

    async def _reap_queue(_tasks_store, queue, **_kwargs):
        calls["queues"].append(queue.pack_id)

    monkeypatch.setattr(worker_maintenance, "_reap_redis_queues", _reap_queue)
    browser_queue = type("Queue", (), {"pack_id": "browser_local"})()
    default_queue = type("Queue", (), {"pack_id": "default_local_browser"})()

    ran = await worker_maintenance._run_maintenance_cycle(
        object(),
        runner_id="runner-default",
        redis_queue=default_queue,
        ready_queues={
            "browser_local": browser_queue,
            "default_local_browser": default_queue,
        },
        ready_targets={"browser_local": 3, "default_local_browser": 3},
        queue_cycle=[browser_queue, default_queue],
    )

    assert ran is True
    assert calls == {"global": 0, "queues": ["default_local_browser"]}


@pytest.mark.asyncio
async def test_global_leader_runs_global_chores_without_foreign_partition_reap(
    monkeypatch,
):
    monkeypatch.setattr(worker_maintenance, "_worker_facade", lambda: None)
    monkeypatch.setattr(
        worker_maintenance,
        "_runner_claim_gate_paused",
        lambda: (False, {"state": "open"}),
    )

    async def _global_owner(*_args, **_kwargs):
        return True

    async def _not_partition_owner(*_args, **_kwargs):
        return False

    calls = {"reap": 0, "locks": 0, "watchdog": 0, "queues": 0}
    monkeypatch.setattr(
        worker_maintenance,
        "try_hold_maintenance_leadership",
        _global_owner,
    )
    monkeypatch.setattr(
        worker_maintenance,
        "try_hold_partition_maintenance_leadership",
        _not_partition_owner,
    )
    monkeypatch.setattr(
        worker_maintenance,
        "_reap_stale_running_tasks",
        lambda *_args, **_kwargs: calls.__setitem__("reap", calls["reap"] + 1),
    )
    monkeypatch.setattr(
        worker_maintenance,
        "_request_watchdog_abort_for_no_progress_tasks",
        lambda *_args, **_kwargs: calls.__setitem__(
            "watchdog", calls["watchdog"] + 1
        ),
    )

    async def _cleanup(*_args, **_kwargs):
        calls["locks"] += 1

    async def _reap_queue(*_args, **_kwargs):
        calls["queues"] += 1

    monkeypatch.setattr(worker_maintenance, "_cleanup_stale_locks", _cleanup)
    monkeypatch.setattr(worker_maintenance, "_reap_redis_queues", _reap_queue)
    queue = type("Queue", (), {"pack_id": "browser_local"})()

    ran = await worker_maintenance._run_maintenance_cycle(
        object(),
        runner_id="runner-global",
        redis_queue=queue,
        ready_queues={"browser_local": queue},
        ready_targets={"browser_local": 3},
        queue_cycle=[queue],
    )

    assert ran is True
    assert calls == {"reap": 1, "locks": 1, "watchdog": 1, "queues": 0}


@pytest.mark.asyncio
async def test_global_and_partition_work_share_one_database_pressure_check(
    monkeypatch,
):
    monkeypatch.setattr(worker_maintenance, "_worker_facade", lambda: None)
    monkeypatch.setattr(
        worker_maintenance,
        "_runner_claim_gate_paused",
        lambda: (False, {"state": "open"}),
    )

    async def _owns_maintenance(*_args, **_kwargs):
        return True

    pressure_calls = []

    async def _open_pressure(*_args, **_kwargs):
        pressure_calls.append(True)
        return db_pool_pressure.DbPoolPressureDecision.open(reason="test")

    monkeypatch.setattr(
        worker_maintenance,
        "try_hold_maintenance_leadership",
        _owns_maintenance,
    )
    monkeypatch.setattr(
        worker_maintenance,
        "try_hold_partition_maintenance_leadership",
        _owns_maintenance,
    )
    monkeypatch.setattr(worker_maintenance, "check_db_pool_pressure", _open_pressure)
    monkeypatch.setattr(
        worker_maintenance,
        "_reap_stale_running_tasks",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        worker_maintenance,
        "_request_watchdog_abort_for_no_progress_tasks",
        lambda *_args, **_kwargs: None,
    )

    async def _cleanup(*_args, **_kwargs):
        return None

    async def _reap_queue(*_args, **_kwargs):
        return None

    monkeypatch.setattr(worker_maintenance, "_cleanup_stale_locks", _cleanup)
    monkeypatch.setattr(worker_maintenance, "_reap_redis_queues", _reap_queue)

    class _Queue:
        pack_id = "browser_local"

        async def _get_client(self):
            return object()

    queue = _Queue()
    ran = await worker_maintenance._run_maintenance_cycle(
        object(),
        runner_id="runner-both",
        redis_queue=queue,
        ready_queues={"browser_local": queue},
        ready_targets={"browser_local": 3},
        queue_cycle=[queue],
    )

    assert ran is True
    assert pressure_calls == [True]
