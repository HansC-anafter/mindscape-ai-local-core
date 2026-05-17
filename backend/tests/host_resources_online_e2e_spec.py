from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.routes.core import host_resources
from backend.app.services.host_resources import manager


class _MemoryCache:
    def __init__(self):
        self.values = {}

    def get_json(self, key):
        return self.values.get(key)

    def set_json(self, key, value, ttl=None):
        self.values[key] = value
        return True

    def delete(self, key):
        self.values.pop(key, None)
        return True


class _FakeDurableLedger:
    def __init__(self):
        self.reservations = {}
        self.events = []
        self.list_reservations_calls = 0

    def save_reservation(self, reservation):
        self.reservations[reservation["reservation_id"]] = dict(reservation)
        return dict(reservation)

    def append_event(self, event_type, **kwargs):
        event = {
            "event_id": f"evt-{len(self.events) + 1}",
            "reservation_id": kwargs.get("reservation_id"),
            "event_type": event_type,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "source": kwargs.get("source"),
            "actor": kwargs.get("actor"),
            "lane_id": kwargs.get("lane_id"),
            "payload": kwargs.get("payload") or {},
        }
        self.events.append(event)
        return event

    def cancel_reservation(self, reservation_id, *, cancelled_at=None):
        reservation = self.reservations.get(reservation_id)
        if not reservation:
            return None
        reservation = dict(reservation)
        reservation["state"] = "cancelled"
        reservation["cancelled_at"] = cancelled_at or datetime.now(timezone.utc).isoformat()
        reservation["updated_at"] = reservation["cancelled_at"]
        self.reservations[reservation_id] = reservation
        return reservation

    def expire_stale_reservations(self, limit=100):
        return []

    def list_reservations(self, limit=100):
        self.list_reservations_calls += 1
        return list(self.reservations.values())[:limit]

    def list_active_reservations(self, limit=100):
        return [
            reservation
            for reservation in self.reservations.values()
            if reservation.get("state") in {"reserved_waiting", "permitted"}
        ][:limit]

    def list_events(self, reservation_id=None, limit=50):
        events = [
            event
            for event in self.events
            if not reservation_id or event.get("reservation_id") == reservation_id
        ]
        return list(reversed(events))[:limit]


async def _snapshot(**kwargs):
    return {
        "captured_at": "2026-05-16T00:00:00Z",
        "degraded": False,
        "host": {
            "memory_pressure": {
                "free_percent": 35,
            },
        },
        "capacity": {
            "memory_mb": 20480,
            "reserved_memory_mb": 7168,
        },
        "consumers": [
            {
                "consumer_id": "mlx:qwen9b_4bit_vision",
                "label": "MLX Qwen9B 4bit Vision",
                "memory_mb": 7168,
                "memory_source": "declared",
            }
        ],
        "lanes": [
            {
                "lane_id": "comfyui_runtime:flux2",
                "label": "Flux2 Lane",
                "state": "available",
            }
        ],
    }


def test_online_safe_reservation_lifecycle_e2e_without_live_db_migration(monkeypatch):
    cache = _MemoryCache()
    ledger = _FakeDurableLedger()
    monkeypatch.setattr(manager, "get_cache_service", lambda: cache)
    monkeypatch.setattr(manager, "_get_route_reservation_store", lambda: ledger)
    monkeypatch.setattr(host_resources, "get_host_resource_snapshot", _snapshot)
    manager._route_reservations.clear()

    app = FastAPI()
    app.include_router(host_resources.router)
    client = TestClient(app)

    created = client.post(
        "/api/v1/host-resources/route-reservations",
        json={
            "ttl_seconds": 120,
            "route_request": {
                "target_lane": "comfyui_runtime:flux2",
                "resource_groups": ["apple_metal_heavy"],
                "priority_class": "interactive_high",
                "drain_policy": "drain_after_current",
                "preemption_policy": "never",
                "resume_policy": "auto_restore_previous",
                "requested_by": "online_safe_e2e",
            },
        },
    ).json()
    reservation_id = created["reservation_id"]

    assert created["state"] == "reserved_waiting"
    assert created["ledger_persisted"] is True
    assert ledger.events[0]["event_type"] == "reservation_created"

    active = client.get(
        "/api/v1/host-resources/route-reservations"
        "?state=active&include_durable=false&limit=5"
    ).json()
    assert [reservation["reservation_id"] for reservation in active["reservations"]] == [reservation_id]
    assert ledger.list_reservations_calls == 0

    summary = client.get("/api/v1/host-resources/summary").json()
    assert summary["route_controls"] == {
        "active": 1,
        "draining": 1,
        "targets": ["comfyui_runtime:flux2"],
    }

    cancelled = client.delete(f"/api/v1/host-resources/route-reservations/{reservation_id}").json()
    assert cancelled["state"] == "cancelled"
    assert ledger.events[-1]["event_type"] == "reservation_cancelled"

    history = client.get(
        "/api/v1/host-resources/route-reservations?state=history&limit=5"
    ).json()
    assert [reservation["reservation_id"] for reservation in history["reservations"]] == [reservation_id]

    events = client.get(
        f"/api/v1/host-resources/route-reservations/events?reservation_id={reservation_id}&limit=5"
    ).json()
    assert [event["event_type"] for event in events["events"]] == [
        "reservation_cancelled",
        "reservation_created",
    ]
