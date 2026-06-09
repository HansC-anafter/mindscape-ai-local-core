import pytest

from backend.app.services.host_resources import worker_target_reconciler as reconciler


def _lane(
    *,
    desired_worker_count: int = 1,
    adapter_id: str = "apple_mlx_vlm",
    resource_flavor: str = "local.mlx.vision",
) -> dict:
    return {
        "lane_id": "runner:35b_synthesis",
        "queue_shard": "ig_synthesis",
        "runner_profile": "35b_synthesis",
        "resource_class": "compute",
        "desired_worker_count": desired_worker_count,
        "resource_flavor": resource_flavor,
        "model_profile": {
            "port": 8212,
            "model": "froggeric/Qwen3.6-35B-A3B-Uncensored-Heretic-MLX-4bit",
            "adapter_id": adapter_id,
        },
        "metadata": {
            "adapter_id": adapter_id,
        },
    }


@pytest.mark.asyncio
async def test_reconcile_starts_missing_managed_worker(monkeypatch):
    lane = _lane()
    bridge_calls = []
    update_calls = []

    class _Store:
        def __init__(self, *_args, **_kwargs):
            pass

        def list_lanes(self):
            return [lane]

    async def _call_host_resource_lane_workers_set(arguments):
        bridge_calls.append(arguments)
        return {
            "accepted": True,
            "reason": "worker_target_started",
            "port": 8212,
        }

    monkeypatch.setattr(reconciler, "HostResourceDynamicLaneStore", _Store)
    monkeypatch.setattr(
        reconciler,
        "resolve_worker_target",
        lambda current_lane, desired: {
            "accepted": True,
            "worker_env": {
                "LOCAL_CORE_RUNTIME_ADAPTER_ID": "apple_mlx_vlm",
                "MLX_MODEL": current_lane["model_profile"]["model"],
                "MLX_PORT": 8212,
            },
        },
    )
    monkeypatch.setattr(
        reconciler,
        "call_host_resource_lane_workers_set",
        _call_host_resource_lane_workers_set,
    )
    monkeypatch.setattr(
        reconciler,
        "update_dynamic_lane",
        lambda lane_id, payload: update_calls.append((lane_id, payload)) or {**lane, **payload},
    )

    result = await reconciler.reconcile_desired_worker_targets()

    assert result["inspected"] == 1
    assert result["started"] == 1
    assert bridge_calls == [
        {
            "lane_id": "runner:35b_synthesis",
            "desired_worker_count": 1,
            "queue_shard": "ig_synthesis",
            "runner_profile": "35b_synthesis",
            "resource_class": "compute",
            "worker_env": {
                "LOCAL_CORE_RUNTIME_ADAPTER_ID": "apple_mlx_vlm",
                "MLX_MODEL": "froggeric/Qwen3.6-35B-A3B-Uncensored-Heretic-MLX-4bit",
                "MLX_PORT": 8212,
            },
        }
    ]
    assert update_calls == [("runner:35b_synthesis", {"state": "starting"})]


@pytest.mark.asyncio
async def test_reconcile_marks_available_when_worker_is_already_running(monkeypatch):
    lane = _lane()
    update_calls = []

    class _Store:
        def __init__(self, *_args, **_kwargs):
            pass

        def list_lanes(self):
            return [lane]

    monkeypatch.setattr(reconciler, "HostResourceDynamicLaneStore", _Store)
    monkeypatch.setattr(
        reconciler,
        "resolve_worker_target",
        lambda *_args, **_kwargs: {"accepted": True, "worker_env": {"MLX_PORT": 8212}},
    )

    async def _call_host_resource_lane_workers_set(_arguments):
        return {
            "accepted": True,
            "reason": "worker_target_already_running",
            "port": 8212,
        }

    monkeypatch.setattr(
        reconciler,
        "call_host_resource_lane_workers_set",
        _call_host_resource_lane_workers_set,
    )
    monkeypatch.setattr(
        reconciler,
        "update_dynamic_lane",
        lambda lane_id, payload: update_calls.append((lane_id, payload)) or {**lane, **payload},
    )

    result = await reconciler.reconcile_desired_worker_targets()

    assert result["inspected"] == 1
    assert result["already_running"] == 1
    assert update_calls == [("runner:35b_synthesis", {"state": "available"})]


@pytest.mark.asyncio
async def test_reconcile_marks_lane_degraded_when_resolution_fails(monkeypatch):
    lane = _lane()
    update_calls = []

    class _Store:
        def __init__(self, *_args, **_kwargs):
            pass

        def list_lanes(self):
            return [lane]

    monkeypatch.setattr(reconciler, "HostResourceDynamicLaneStore", _Store)
    monkeypatch.setattr(
        reconciler,
        "resolve_worker_target",
        lambda *_args, **_kwargs: {
            "accepted": False,
            "reason": "runtime_environment_not_configured",
        },
    )
    monkeypatch.setattr(
        reconciler,
        "update_dynamic_lane",
        lambda lane_id, payload: update_calls.append((lane_id, payload)) or {**lane, **payload},
    )

    result = await reconciler.reconcile_desired_worker_targets()

    assert result["inspected"] == 1
    assert result["degraded"] == 1
    assert update_calls == [("runner:35b_synthesis", {"state": "degraded"})]
    assert result["lanes"][0]["reason"] == "runtime_environment_not_configured"


@pytest.mark.asyncio
async def test_reconcile_skips_lanes_without_desired_managed_worker(monkeypatch):
    lanes = [
        _lane(desired_worker_count=0),
        _lane(adapter_id="other_adapter"),
        _lane(resource_flavor="local.mps.comfyui"),
    ]

    class _Store:
        def __init__(self, *_args, **_kwargs):
            pass

        def list_lanes(self):
            return lanes

    monkeypatch.setattr(reconciler, "HostResourceDynamicLaneStore", _Store)

    result = await reconciler.reconcile_desired_worker_targets()

    assert result["inspected"] == 0
    assert result["skipped"] == 3
    assert result["lanes"] == []
