import pytest

from backend.app.dependencies.auth import AuthContext
from backend.app.services.host_resources import worker_targets


@pytest.mark.asyncio
async def test_positive_worker_target_blocked_by_gate_does_not_update_lane(monkeypatch):
    lane = {
        "lane_id": "runner:vision_mlx_high",
        "queue_shard": "vision_mlx_high",
        "runner_profile": "vision_mlx_high",
        "resource_class": "compute",
        "max_concurrency": 2,
        "desired_worker_count": 0,
        "model_profile": {"port": 8211, "model": "mlx-community/Qwen2.5-VL"},
    }
    update_calls = []
    bridge_calls = []

    async def _resource_gate_allows_start():
        return False, {
            "reason": "pgbouncer_client_waiting",
            "db_pool_pressure": {"state": "paused"},
        }

    async def _call_host_resource_lane_workers_set(arguments):
        bridge_calls.append(arguments)
        return {"accepted": True}

    monkeypatch.setattr(worker_targets, "get_dynamic_lane", lambda lane_id: lane)
    monkeypatch.setattr(
        worker_targets,
        "resolve_worker_target",
        lambda resolved_lane, desired: {
            "accepted": True,
            "reason": "worker_target_resolved",
            "worker_env": {"MLX_PORT": 8211},
        },
    )
    monkeypatch.setattr(
        worker_targets,
        "update_dynamic_lane",
        lambda lane_id, payload: update_calls.append((lane_id, payload)) or lane,
    )
    monkeypatch.setattr(worker_targets, "_resource_gate_allows_start", _resource_gate_allows_start)
    monkeypatch.setattr(
        worker_targets,
        "call_host_resource_lane_workers_set",
        _call_host_resource_lane_workers_set,
    )

    result = await worker_targets.set_lane_worker_target("runner:vision_mlx_high", 1)

    assert result["accepted"] is False
    assert result["reason"] == "pgbouncer_client_waiting"
    assert result["lane"]["desired_worker_count"] == 0
    assert update_calls == []
    assert bridge_calls == []


@pytest.mark.asyncio
async def test_positive_worker_target_requires_runtime_slot_before_gate(monkeypatch):
    lane = {
        "lane_id": "runner:vision_mlx_high",
        "queue_shard": "vision_mlx_high",
        "runner_profile": "vision_mlx_high",
        "resource_class": "compute",
        "max_concurrency": 1,
        "desired_worker_count": 0,
        "resource_flavor": "local.mlx.vision",
        "model_profile": {},
        "metadata": {},
    }
    gate_calls = []
    update_calls = []
    bridge_calls = []

    async def _resource_gate_allows_start():
        gate_calls.append(True)
        return True, {"reason": "resource_gate_open"}

    async def _call_host_resource_lane_workers_set(arguments):
        bridge_calls.append(arguments)
        return {"accepted": True}

    monkeypatch.setattr(worker_targets, "get_dynamic_lane", lambda lane_id: lane)
    monkeypatch.setattr(
        worker_targets,
        "update_dynamic_lane",
        lambda lane_id, payload: update_calls.append((lane_id, payload)) or lane,
    )
    monkeypatch.setattr(worker_targets, "_resource_gate_allows_start", _resource_gate_allows_start)
    monkeypatch.setattr(
        worker_targets,
        "call_host_resource_lane_workers_set",
        _call_host_resource_lane_workers_set,
    )

    result = await worker_targets.set_lane_worker_target("runner:vision_mlx_high", 1)

    assert result["accepted"] is False
    assert result["reason"] == "host_resource_slot_missing"
    assert result["lane"]["desired_worker_count"] == 0
    assert gate_calls == []
    assert update_calls == []
    assert bridge_calls == []


@pytest.mark.asyncio
async def test_workspace_worker_target_quota_blocks_before_runtime_resolution(monkeypatch):
    lane = {
        "lane_id": "runner:vision_mlx_high",
        "queue_shard": "vision_mlx_high",
        "runner_profile": "vision_mlx_high",
        "resource_class": "compute",
        "max_concurrency": 2,
        "desired_worker_count": 0,
        "resource_flavor": "local.mlx.vision",
        "model_profile": {},
        "metadata": {},
    }
    resolve_calls = []
    gate_calls = []
    bridge_calls = []

    def _workspace_allocation_decision(**kwargs):
        return {
            "accepted": False,
            "reason": "workspace_allocation_quota_zero",
            "kwargs": kwargs,
        }

    async def _resource_gate_allows_start():
        gate_calls.append(True)
        return True, {"reason": "resource_gate_open"}

    async def _call_host_resource_lane_workers_set(arguments):
        bridge_calls.append(arguments)
        return {"accepted": True}

    monkeypatch.setattr(worker_targets, "get_dynamic_lane", lambda lane_id: lane)
    monkeypatch.setattr(
        worker_targets,
        "resolve_worker_target",
        lambda resolved_lane, desired: resolve_calls.append((resolved_lane, desired))
        or {"accepted": True},
    )
    monkeypatch.setattr(
        worker_targets,
        "workspace_allocation_decision",
        _workspace_allocation_decision,
    )
    monkeypatch.setattr(worker_targets, "_resource_gate_allows_start", _resource_gate_allows_start)
    monkeypatch.setattr(
        worker_targets,
        "call_host_resource_lane_workers_set",
        _call_host_resource_lane_workers_set,
    )

    result = await worker_targets.set_lane_worker_target(
        "runner:vision_mlx_high",
        1,
        auth_context=AuthContext(
            user_id="workspace_user",
            tenant_id="tenant",
            workspace_ids=["ws-1"],
        ),
        workspace_id="ws-1",
        allocation_id="alloc-1",
    )

    assert result["accepted"] is False
    assert result["reason"] == "workspace_allocation_quota_zero"
    assert resolve_calls == []
    assert gate_calls == []
    assert bridge_calls == []
