from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.app.runner import worker_loop_control
from backend.app.runner.db_pool_pressure import DbPoolPressureDecision
from backend.app.services.host_resources.runner_claim_modes import (
    active_runner_claim_control,
)


@pytest.mark.asyncio
async def test_maintenance_only_env_blocks_claims_without_redis_or_pressure_probe(
    monkeypatch,
):
    monkeypatch.setenv("LOCAL_CORE_RUNNER_MAINTENANCE_ONLY", "true")
    get_control = AsyncMock(side_effect=AssertionError("redis control must not run"))
    pressure_probe = AsyncMock(side_effect=AssertionError("claim pressure must not run"))
    monkeypatch.setattr(worker_loop_control, "get_runner_claim_control", get_control)
    monkeypatch.setattr(worker_loop_control, "check_db_pool_pressure", pressure_probe)

    control, enabled, pressure, budget = (
        await worker_loop_control._resolve_loop_claim_budget(
            object(),
            runner_id="maintenance-owner",
            runner_profile=SimpleNamespace(profile_code="browser_maintenance"),
            inflight=0,
            max_inflight=1,
        )
    )

    assert enabled is False
    assert control.mode == "drain"
    assert control.reason == "maintenance_only"
    assert control.source == "environment"
    assert pressure.reason == "runner_claim_mode_drain"
    assert budget.allow_claim_scan is False
    assert budget.allow_release_maintenance is True
    get_control.assert_not_awaited()
    pressure_probe.assert_not_awaited()


@pytest.mark.asyncio
async def test_maintenance_only_false_preserves_normal_claim_budget(monkeypatch):
    monkeypatch.setenv("LOCAL_CORE_RUNNER_MAINTENANCE_ONLY", "false")
    get_control = AsyncMock(return_value=active_runner_claim_control("runner-a"))
    pressure_probe = AsyncMock(
        return_value=DbPoolPressureDecision.open(reason="test_open")
    )
    monkeypatch.setattr(worker_loop_control, "get_runner_claim_control", get_control)
    monkeypatch.setattr(worker_loop_control, "check_db_pool_pressure", pressure_probe)

    control, enabled, pressure, budget = (
        await worker_loop_control._resolve_loop_claim_budget(
            object(),
            runner_id="runner-a",
            runner_profile=SimpleNamespace(profile_code="browser_local"),
            inflight=0,
            max_inflight=2,
        )
    )

    assert control.mode == "active"
    assert enabled is True
    assert pressure.reason == "test_open"
    assert budget.allow_claim_scan is True
    get_control.assert_awaited_once()
    pressure_probe.assert_awaited_once()
