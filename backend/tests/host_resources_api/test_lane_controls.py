from fastapi.testclient import TestClient

from backend.app.routes.core import host_resources

from .host_resources_api_test_support import build_app


def test_create_lane_endpoint_returns_created_dynamic_lane(monkeypatch):
    received = {}
    cleared = {"count": 0}

    def _create_dynamic_lane(payload):
        received.update(payload)
        return {"lane_id": payload["lane_id"], "queue_shard": payload["queue_shard"]}

    monkeypatch.setattr(host_resources, "create_dynamic_lane", _create_dynamic_lane)
    monkeypatch.setattr(
        host_resources,
        "clear_host_resource_snapshot_cache",
        lambda: cleared.update(count=cleared["count"] + 1),
    )

    response = TestClient(build_app()).post(
        "/api/v1/host-resources/lanes",
        json={
            "lane_id": "runner:vision_mlx_high",
            "capability_scope": "ig",
            "label": "Vision MLX High",
            "kind": "vision_analyze",
            "queue_shard": "vision_mlx_high",
            "runner_profile": "vision_mlx_high",
            "resource_class": "compute",
        },
    )

    assert response.status_code == 200
    assert response.json()["lane"]["queue_shard"] == "vision_mlx_high"
    assert received["lane_id"] == "runner:vision_mlx_high"
    assert cleared["count"] == 1


def test_patch_lane_endpoint_clears_cached_snapshot(monkeypatch):
    received = {}
    cleared = {"count": 0}

    def _update_dynamic_lane(lane_id, payload):
        received["lane_id"] = lane_id
        received["payload"] = payload
        return {"lane_id": lane_id, "model_profile": payload["model_profile"]}

    monkeypatch.setattr(host_resources, "update_dynamic_lane", _update_dynamic_lane)
    monkeypatch.setattr(
        host_resources,
        "clear_host_resource_snapshot_cache",
        lambda: cleared.update(count=cleared["count"] + 1),
    )

    response = TestClient(build_app()).patch(
        "/api/v1/host-resources/lanes/runner:vision_mlx_high",
        json={
            "model_profile": {
                "port": 8211,
                "model": "froggeric/Qwen3.6-35B-A3B-Uncensored-Heretic-MLX-4bit",
            }
        },
    )

    assert response.status_code == 200
    assert response.json()["lane"]["model_profile"]["port"] == 8211
    assert received["lane_id"] == "runner:vision_mlx_high"
    assert cleared["count"] == 1


def test_worker_target_endpoint_returns_blocked_result(monkeypatch):
    async def _set_lane_worker_target(lane_id, desired_worker_count, **kwargs):
        return {
            "accepted": False,
            "lane_id": lane_id,
            "desired_worker_count": desired_worker_count,
            "reason": "pgbouncer_client_waiting",
            "auth_user_id": getattr(kwargs.get("auth_context"), "user_id", None),
        }

    monkeypatch.setattr(
        host_resources,
        "set_lane_worker_target",
        _set_lane_worker_target,
    )

    response = TestClient(build_app()).post(
        "/api/v1/host-resources/lanes/runner:vision_mlx_high/worker-target",
        json={"desired_worker_count": 1},
    )

    assert response.status_code == 200
    assert response.json()["accepted"] is False
    assert response.json()["reason"] == "pgbouncer_client_waiting"
    assert response.json()["auth_user_id"] == "default_user"
