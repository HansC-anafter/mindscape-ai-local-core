import pytest

from backend.app.runner import worker_maintenance


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

    ran = await worker_maintenance._run_maintenance_cycle(
        object(),
        runner_id="runner-b",
        redis_queue=_NoDbQueue(),
        ready_queues={},
        ready_targets={},
        queue_cycle=[],
    )

    assert ran is False
