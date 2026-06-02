import pytest

from backend.app.runner import db_pool_pressure, worker


class _FakeQueue:
    pass


@pytest.mark.asyncio
async def test_maintenance_skips_db_work_when_pgbouncer_pressure_paused(monkeypatch):
    calls = {"reap": 0, "locks": 0, "watchdog": 0, "queues": 0}

    async def paused_pressure(*_args, **_kwargs):
        return db_pool_pressure.DbPoolPressureDecision.paused_for(
            "pgbouncer_client_waiting"
        )

    monkeypatch.setattr(worker, "_runner_claim_gate_paused", lambda: (False, {}))
    monkeypatch.setattr(worker, "check_db_pool_pressure", paused_pressure)
    monkeypatch.setattr(
        worker,
        "_reap_stale_running_tasks",
        lambda *_args, **_kwargs: calls.__setitem__("reap", calls["reap"] + 1),
    )
    monkeypatch.setattr(
        worker,
        "_request_watchdog_abort_for_no_progress_tasks",
        lambda *_args, **_kwargs: calls.__setitem__(
            "watchdog", calls["watchdog"] + 1
        ),
    )

    async def cleanup(*_args, **_kwargs):
        calls["locks"] += 1

    async def reap_queue(*_args, **_kwargs):
        calls["queues"] += 1

    monkeypatch.setattr(worker, "_cleanup_stale_locks", cleanup)
    monkeypatch.setattr(worker, "_reap_redis_queues", reap_queue)

    ran = await worker._run_maintenance_cycle(
        object(),
        runner_id="runner-a",
        redis_queue=_FakeQueue(),
        ready_queues={"default": _FakeQueue()},
        ready_targets={"default": 1},
        queue_cycle=[_FakeQueue()],
    )

    assert ran is False
    assert calls == {"reap": 0, "locks": 0, "watchdog": 0, "queues": 0}
