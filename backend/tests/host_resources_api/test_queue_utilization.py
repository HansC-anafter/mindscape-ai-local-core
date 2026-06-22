from fastapi.testclient import TestClient

from backend.app.routes.core import host_resources

from .host_resources_api_test_support import build_app


def test_queue_utilization_endpoint_returns_latest_snapshot(monkeypatch):
    async def _build_queue_utilization_response(**kwargs):
        assert kwargs == {"live": False, "view": None, "queue_shard": None}
        return {
            "source": "live_resource_console",
            "queue_depths": {"browser_local": {"pending": 5}},
            "capacity_by_queue_shard": {
                "browser_local": {"max_inflight_total": 3}
            },
            "visible_lanes": {"browser_local": []},
            "visible_lane_count": {"browser_local": 0},
            "resource_lanes": {"browser_local": []},
            "resource_lane_count": {"browser_local": 0},
            "backlog_summary_by_queue_shard": {},
            "utilization_ratio_by_queue_shard": {"browser_local": 0},
            "degraded": False,
            "errors": [],
        }

    monkeypatch.setattr(
        host_resources,
        "build_queue_utilization_response",
        _build_queue_utilization_response,
    )

    response = TestClient(build_app()).get("/api/v1/host-resources/queue-utilization")

    assert response.status_code == 200
    assert response.json()["source"] == "live_resource_console"
    assert response.json()["queue_depths"]["browser_local"]["pending"] == 5


def test_queue_utilization_endpoint_live_uses_bounded_reader(monkeypatch):
    async def _build_queue_utilization_response(**kwargs):
        assert kwargs == {"live": True, "view": None, "queue_shard": None}
        return {
            "source": "live_redis_bounded",
            "queue_depths": {"browser_local": {"pending": 5}},
            "capacity_by_queue_shard": {
                "browser_local": {"max_inflight_total": 3}
            },
            "visible_lanes": {"browser_local": []},
            "visible_lane_count": {"browser_local": 0},
            "utilization_ratio_by_queue_shard": {"browser_local": 0},
            "degraded": False,
            "errors": [],
        }

    monkeypatch.setattr(
        host_resources,
        "build_queue_utilization_response",
        _build_queue_utilization_response,
    )

    response = TestClient(build_app()).get(
        "/api/v1/host-resources/queue-utilization?live=true"
    )

    assert response.status_code == 200
    assert response.json()["source"] == "live_redis_bounded"
