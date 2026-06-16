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
async def test_worker_target_fallback_env_includes_lane_watchdog_settings(monkeypatch):
    lane = {
        "lane_id": "runner:decision_synthesis_35b",
        "queue_shard": "decision_synthesis",
        "runner_profile": "35b_synthesis",
        "resource_class": "compute",
        "max_concurrency": 1,
        "desired_worker_count": 0,
        "resource_flavor": "local.mlx.vision",
        "model_profile": {
            "port": 8212,
            "model": "froggeric/Qwen3.6-35B-A3B-Uncensored-Heretic-MLX-4bit",
            "watchdog": {
                "inflight_hard_timeout_seconds": 10800,
                "inflight_heartbeat_timeout_seconds": 180,
                "inflight_ustate_max_failures": 12,
            },
        },
        "metadata": {},
    }
    bridge_calls = []

    async def _resource_gate_allows_start():
        return True, {"reason": "resource_gate_open"}

    async def _call_host_resource_lane_workers_set(arguments):
        bridge_calls.append(arguments)
        return {"accepted": True, "reason": "worker_target_started"}

    monkeypatch.setattr(worker_targets, "get_dynamic_lane", lambda lane_id: lane)
    monkeypatch.setattr(
        worker_targets,
        "resolve_worker_target",
        lambda resolved_lane, desired: {
            "accepted": True,
            "reason": "worker_target_resolved",
        },
    )
    monkeypatch.setattr(worker_targets, "_resource_gate_allows_start", _resource_gate_allows_start)
    monkeypatch.setattr(
        worker_targets,
        "call_host_resource_lane_workers_set",
        _call_host_resource_lane_workers_set,
    )
    monkeypatch.setattr(worker_targets, "update_dynamic_lane", lambda lane_id, payload: lane)

    result = await worker_targets.set_lane_worker_target("runner:decision_synthesis_35b", 1)

    assert result["accepted"] is True
    assert bridge_calls[0]["worker_env"]["MLX_WATCHDOG_INFLIGHT_HARD_TIMEOUT"] == 10800
    assert bridge_calls[0]["worker_env"]["MLX_WATCHDOG_INFLIGHT_HEARTBEAT_TIMEOUT"] == 180
    assert bridge_calls[0]["worker_env"]["MLX_WATCHDOG_INFLIGHT_USTATE_MAX_FAILURES"] == 12


@pytest.mark.asyncio
async def test_worker_target_start_clears_snapshot_cache_after_lane_update(monkeypatch):
    lane = {
        "lane_id": "runner:vision_mlx_dev",
        "queue_shard": "vision_mlx_dev",
        "runner_profile": "vision_mlx_dev",
        "resource_class": "compute",
        "max_concurrency": 1,
        "desired_worker_count": 0,
        "resource_flavor": "local.mlx.vision",
        "model_profile": {
            "port": 8212,
            "model": "mlx-community/Qwen3.5-9B-4bit",
        },
        "metadata": {},
    }
    update_calls = []
    clear_calls = []

    async def _resource_gate_allows_start():
        return True, {"reason": "resource_gate_open"}

    async def _call_host_resource_lane_workers_set(arguments):
        return {"accepted": True, "reason": "worker_target_started"}

    def _update_dynamic_lane(lane_id, payload):
        update_calls.append((lane_id, payload))
        return {**lane, **payload}

    monkeypatch.setattr(worker_targets, "get_dynamic_lane", lambda lane_id: lane)
    monkeypatch.setattr(
        worker_targets,
        "resolve_worker_target",
        lambda resolved_lane, desired: {
            "accepted": True,
            "reason": "worker_target_resolved",
            "worker_env": {"MLX_PORT": 8212},
        },
    )
    monkeypatch.setattr(worker_targets, "_resource_gate_allows_start", _resource_gate_allows_start)
    monkeypatch.setattr(
        worker_targets,
        "call_host_resource_lane_workers_set",
        _call_host_resource_lane_workers_set,
    )
    monkeypatch.setattr(worker_targets, "update_dynamic_lane", _update_dynamic_lane)
    monkeypatch.setattr(
        worker_targets,
        "clear_host_resource_snapshot_cache",
        lambda: clear_calls.append(True),
    )

    result = await worker_targets.set_lane_worker_target("runner:vision_mlx_dev", 1)

    assert result["accepted"] is True
    assert result["lane"]["desired_worker_count"] == 1
    assert result["lane"]["state"] == "starting"
    assert update_calls == [
        (
            "runner:vision_mlx_dev",
            {
                "desired_worker_count": 1,
                "state": "starting",
            },
        )
    ]
    assert clear_calls == [True]


@pytest.mark.asyncio
async def test_stop_worker_target_marks_degraded_when_host_stop_not_verified(monkeypatch):
    lane = {
        "lane_id": "runner:35b_synthesis",
        "queue_shard": "synthesis_mlx_high",
        "runner_profile": "synthesis_mlx_high",
        "resource_class": "compute",
        "max_concurrency": 1,
        "desired_worker_count": 1,
        "state": "available",
        "model_profile": {"port": 8212, "model": "froggeric/Qwen3.6-35B-A3B-Uncensored-Heretic-MLX-4bit"},
    }
    update_calls = []
    bridge_calls = []

    async def _call_host_resource_lane_workers_set(arguments):
        bridge_calls.append(arguments)
        return {
            "accepted": False,
            "reason": "worker_target_stop_incomplete",
            "port_listening": True,
            "remaining_port_owners": [12345],
        }

    def _update_dynamic_lane(lane_id, payload):
        assert bridge_calls
        update_calls.append((lane_id, payload))
        return {**lane, **payload}

    monkeypatch.setattr(worker_targets, "get_dynamic_lane", lambda lane_id: lane)
    monkeypatch.setattr(worker_targets, "update_dynamic_lane", _update_dynamic_lane)
    monkeypatch.setattr(
        worker_targets,
        "call_host_resource_lane_workers_set",
        _call_host_resource_lane_workers_set,
    )

    result = await worker_targets.set_lane_worker_target("runner:35b_synthesis", 0)

    assert result["accepted"] is False
    assert result["reason"] == "worker_target_stop_incomplete"
    assert result["lane"]["desired_worker_count"] == 0
    assert result["lane"]["state"] == "degraded"
    assert update_calls == [
        (
            "runner:35b_synthesis",
            {
                "desired_worker_count": 0,
                "state": "degraded",
            },
        )
    ]


@pytest.mark.asyncio
async def test_stop_worker_target_marks_offline_after_host_stop_verified(monkeypatch):
    lane = {
        "lane_id": "runner:35b_synthesis",
        "queue_shard": "synthesis_mlx_high",
        "runner_profile": "synthesis_mlx_high",
        "resource_class": "compute",
        "max_concurrency": 1,
        "desired_worker_count": 1,
        "state": "available",
        "model_profile": {"port": 8212, "model": "froggeric/Qwen3.6-35B-A3B-Uncensored-Heretic-MLX-4bit"},
    }
    update_calls = []
    bridge_calls = []

    async def _call_host_resource_lane_workers_set(arguments):
        bridge_calls.append(arguments)
        return {
            "accepted": True,
            "reason": "worker_target_stopped",
            "stop_verified": True,
        }

    def _update_dynamic_lane(lane_id, payload):
        assert bridge_calls
        update_calls.append((lane_id, payload))
        return {**lane, **payload}

    monkeypatch.setattr(worker_targets, "get_dynamic_lane", lambda lane_id: lane)
    monkeypatch.setattr(worker_targets, "update_dynamic_lane", _update_dynamic_lane)
    monkeypatch.setattr(
        worker_targets,
        "call_host_resource_lane_workers_set",
        _call_host_resource_lane_workers_set,
    )

    result = await worker_targets.set_lane_worker_target("runner:35b_synthesis", 0)

    assert result["accepted"] is True
    assert result["lane"]["desired_worker_count"] == 0
    assert result["lane"]["state"] == "offline"
    assert update_calls == [
        (
            "runner:35b_synthesis",
            {
                "desired_worker_count": 0,
                "state": "offline",
            },
        )
    ]


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
