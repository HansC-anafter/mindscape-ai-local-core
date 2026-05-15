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
