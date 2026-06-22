from fastapi.testclient import TestClient

from backend.app.routes.core import host_resources

from .host_resources_api_test_support import build_app


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

    response = TestClient(build_app()).get(
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


def test_route_intent_preview_endpoint_forwards_payload(monkeypatch):
    received = {}

    async def _build_route_intent_preview(payload, *, auth_context=None):
        received.update(payload)
        received["auth_user_id"] = getattr(auth_context, "user_id", None)
        return {
            "route_intent": payload,
            "route_intent_preview": {
                "decision": "preview_ready",
                "reservation_payload": {
                    "route_request": payload,
                },
            },
        }

    monkeypatch.setattr(
        host_resources,
        "build_route_intent_preview",
        _build_route_intent_preview,
    )

    response = TestClient(build_app()).post(
        "/api/v1/host-resources/route-intents/preview",
        json={"target_lane": "comfyui_runtime:flux2"},
    )

    assert response.status_code == 200
    assert response.json()["route_intent"] == {"target_lane": "comfyui_runtime:flux2"}
    assert received == {
        "target_lane": "comfyui_runtime:flux2",
        "auth_user_id": "default_user",
    }


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

    response = TestClient(build_app()).get(
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
