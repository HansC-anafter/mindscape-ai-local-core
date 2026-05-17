from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.routes.core import host_resources


def test_route_reservations_endpoint_forwards_state_limit_and_durable_flags(monkeypatch):
    received = {}

    def _list_route_reservations(**kwargs):
        received.update(kwargs)
        return [
            {
                "reservation_id": "res-active",
                "state": "reserved_waiting",
            }
        ]

    monkeypatch.setattr(
        host_resources,
        "list_route_reservations",
        _list_route_reservations,
    )
    app = FastAPI()
    app.include_router(host_resources.router)

    response = TestClient(app).get(
        "/api/v1/host-resources/route-reservations"
        "?state=active&include_durable=false&limit=5"
    )

    assert response.status_code == 200
    assert response.json() == {
        "reservations": [
            {
                "reservation_id": "res-active",
                "state": "reserved_waiting",
            }
        ]
    }
    assert received == {
        "include_durable": False,
        "state": "active",
        "limit": 5,
    }


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

    monkeypatch.setattr(host_resources, "get_host_resource_snapshot", _get_host_resource_snapshot)
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
    app = FastAPI()
    app.include_router(host_resources.router)

    response = TestClient(app).get("/api/v1/host-resources/summary?refresh=true")

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


def test_route_reservation_events_endpoint_returns_events(monkeypatch):
    monkeypatch.setattr(
        host_resources,
        "list_route_reservation_events",
        lambda reservation_id=None, limit=50: [
            {
                "event_id": "evt-1",
                "reservation_id": reservation_id,
                "event_type": "reservation_created",
                "limit": limit,
            }
        ],
    )
    app = FastAPI()
    app.include_router(host_resources.router)

    response = TestClient(app).get(
        "/api/v1/host-resources/route-reservations/events"
        "?reservation_id=res-1&limit=7"
    )

    assert response.status_code == 200
    assert response.json() == {
        "events": [
            {
                "event_id": "evt-1",
                "reservation_id": "res-1",
                "event_type": "reservation_created",
                "limit": 7,
            }
        ]
    }
