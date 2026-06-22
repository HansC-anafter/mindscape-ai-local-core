from fastapi.testclient import TestClient

from backend.app.routes.core import host_resources

from .host_resources_api_test_support import build_app


def test_summary_endpoint_returns_compact_contract(monkeypatch):
    received = {}

    async def _get_host_resource_snapshot(**kwargs):
        received.update(kwargs)
        return {
            "captured_at": "2026-05-16T00:00:00Z",
            "degraded": False,
            "host": {
                "memory_pressure": {
                    "free_percent": 20,
                },
            },
            "capacity": {
                "memory_mb": 4096,
                "reserved_memory_mb": 1024,
            },
            "consumers": [
                {
                    "consumer_id": "ollama:process:1",
                    "label": "Ollama",
                    "memory_mb": 1024,
                    "memory_source": "rss",
                }
            ],
            "lanes": [
                {"lane_id": "lane:busy", "label": "Busy Lane", "state": "busy"},
                {"lane_id": "lane:paused", "label": "Paused Lane", "state": "paused"},
            ],
        }

    monkeypatch.setattr(
        host_resources,
        "get_host_resource_snapshot",
        _get_host_resource_snapshot,
    )
    monkeypatch.setattr(
        host_resources,
        "list_active_route_reservations",
        lambda: [
            {
                "reservation_id": "res-1",
                "state": "reserved_waiting",
                "route_request": {
                    "target_lane": "comfyui_runtime:flux2",
                    "drain_policy": "drain_after_current",
                },
            }
        ],
    )

    response = TestClient(build_app()).get("/api/v1/host-resources/summary?refresh=true")

    assert response.status_code == 200
    assert response.json() == {
        "captured_at": "2026-05-16T00:00:00Z",
        "degraded": False,
        "pressure_state": "watch",
        "free_percent": 20,
        "headroom_mb": 4096,
        "reserved_mb": 1024,
        "lanes": {
            "busy": 1,
            "blocked": 1,
            "total": 2,
        },
        "heavy_consumers": [
            {
                "consumer_id": "ollama:process:1",
                "label": "Ollama",
                "memory_mb": 1024,
                "memory_source": "rss",
            }
        ],
        "primary_blockers": [
            {
                "lane_id": "lane:paused",
                "label": "Paused Lane",
                "state": "paused",
                "reason": None,
            }
        ],
        "route_controls": {
            "active": 1,
            "draining": 1,
            "targets": ["comfyui_runtime:flux2"],
        },
        "control_plane_pressure": {
            "state": "ok",
            "memory_mb": 0,
            "process_count": 0,
            "primary_blockers": [],
            "recommended_actions": [],
        },
        "alerts": [
            {
                "alert_id": "memory_pressure_watch",
                "severity": "warning",
                "message": "Host memory headroom is low",
                "action_href": "/settings?tab=runtime&section=host-resources",
            },
            {
                "alert_id": "host_resource_lanes_blocked",
                "severity": "warning",
                "message": "1 host resource lane(s) blocked",
                "action_href": "/settings?tab=runtime&section=host-resources",
            },
            {
                "alert_id": "route_drain_active",
                "severity": "info",
                "message": "1 route reservation(s) draining",
                "action_href": "/settings?tab=runtime&section=host-resources",
            },
        ],
        "dashboard_href": "/settings?tab=runtime&section=host-resources",
    }
    assert received == {"refresh": True}


def test_summary_endpoint_can_use_cached_snapshot_without_refresh(monkeypatch):
    called = {"snapshot": False}

    async def _get_host_resource_snapshot(**kwargs):
        called["snapshot"] = True
        return {}

    monkeypatch.setattr(
        host_resources,
        "get_host_resource_snapshot",
        _get_host_resource_snapshot,
    )
    monkeypatch.setattr(
        host_resources,
        "get_cached_snapshot_or_degraded",
        lambda: {
            "captured_at": "2026-05-16T00:00:00Z",
            "degraded": False,
            "host": {"memory_pressure": {"free_percent": 40}},
            "capacity": {"memory_mb": 8192, "reserved_memory_mb": 0},
            "consumers": [],
            "lanes": [],
        },
    )
    monkeypatch.setattr(host_resources, "list_active_route_reservations", lambda: [])

    response = TestClient(build_app()).get(
        "/api/v1/host-resources/summary?allow_stale=true"
    )

    assert response.status_code == 200
    assert response.json()["pressure_state"] == "ok"
    assert called["snapshot"] is False


def test_admission_preview_endpoint_returns_gone_with_route_intent_replacement():
    response = TestClient(build_app()).get(
        "/api/v1/host-resources/admission-preview?lane_id=lane:a"
    )

    assert response.status_code == 410
    assert response.json()["detail"] == {
        "replacement": "/api/v1/host-resources/route-intents/preview",
        "reason": "admission_preview_replaced_by_route_intent_preview",
    }


def test_adapter_catalog_endpoint_returns_first_batch_contract():
    response = TestClient(build_app()).get("/api/v1/host-resources/adapter-catalog")

    assert response.status_code == 200
    adapters = {adapter["adapter_id"]: adapter for adapter in response.json()["adapters"]}
    assert adapters["apple_mlx_vlm"]["model_binding_policy"] == "required"
    assert adapters["apple_mlx_vlm"]["default_model_binding_profile"] == "vision"
    assert adapters["mcp_desktop_control"]["worker_capable"] is False
    assert adapters["a2a_protocol_connector"]["model_binding_policy"] == "forbidden"
