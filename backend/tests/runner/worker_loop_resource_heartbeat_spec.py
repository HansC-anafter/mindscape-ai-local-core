import logging
from types import SimpleNamespace

import pytest

from backend.app.runner import worker_loop_control


@pytest.mark.asyncio
async def test_publish_resource_heartbeat_logs_publish_failure(monkeypatch, caplog):
    async def failing_publish(_redis_queue, _heartbeat):
        raise RuntimeError("redis unavailable")

    monkeypatch.setattr(
        worker_loop_control,
        "build_runner_resource_heartbeat",
        lambda **kwargs: kwargs,
    )
    monkeypatch.setattr(
        worker_loop_control,
        "publish_runner_resource_heartbeat",
        failing_publish,
    )
    monkeypatch.setattr(
        worker_loop_control,
        "_next_resource_heartbeat_failure_log_at",
        0.0,
    )

    runner_profile = SimpleNamespace(
        profile_code="default_local_browser",
        accepted_queue_partitions=["default_local_browser"],
    )
    runner_claim_control = SimpleNamespace(to_dict=lambda: {"mode": "active"})

    with caplog.at_level(logging.WARNING, logger="backend.app.runner.worker"):
        await worker_loop_control._publish_resource_heartbeat(
            object(),
            runner_id="runner-1",
            runner_profile=runner_profile,
            capacity=object(),
            resource_snapshot=None,
            runner_claim_control=runner_claim_control,
        )

    assert "Runner resource heartbeat publish failed" in caplog.text
    assert "runner-1" in caplog.text
