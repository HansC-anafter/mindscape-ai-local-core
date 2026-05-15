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


def test_route_reservation_is_written_to_ttl_state(monkeypatch):
    cache = _MemoryCache()
    monkeypatch.setattr(manager, "get_cache_service", lambda: cache)
    monkeypatch.setattr(manager, "_get_route_reservation_store", lambda: None)
    manager._route_reservations.clear()

    reservation = manager.create_route_reservation(
        {
            "route_request": {
                "target_lane": "comfyui_runtime:flux2_klein_true_v2_q6_local",
                "resource_groups": ["apple_metal_heavy"],
            }
        }
    )

    manager._route_reservations.clear()
    reservations = manager.list_active_route_reservations()

    assert reservation["reservation_id"] in cache.values[manager.ROUTE_RESERVATIONS_KEY]
    assert reservations[0]["reservation_id"] == reservation["reservation_id"]


def test_paused_lane_is_restored_from_ttl_state(monkeypatch):
    cache = _MemoryCache()
    monkeypatch.setattr(manager, "get_cache_service", lambda: cache)
    manager._paused_lanes.clear()

    manager.pause_lane("runner:vision_local")
    manager._paused_lanes.clear()

    assert manager.is_lane_paused("runner:vision_local") is True


def test_runner_claim_gate_is_restored_from_ttl_state(monkeypatch):
    cache = _MemoryCache()
    monkeypatch.setattr(manager, "get_cache_service", lambda: cache)
    monkeypatch.setattr(manager, "_get_route_reservation_store", lambda: None)
    manager._runner_claim_gate_state = None

    gate = manager.pause_runner_claim_gate(
        {
            "reason": "postgres_maintenance",
            "requested_by": "test",
            "ttl_seconds": 120,
        }
    )
    manager._runner_claim_gate_state = None
    restored = manager.get_runner_claim_gate()

    assert gate["state"] == "paused"
    assert gate["persisted"] is True
    assert restored["state"] == "paused"
    assert restored["source"] == "redis"


def test_runner_claim_gate_resume_clears_ttl_state(monkeypatch):
    cache = _MemoryCache()
    monkeypatch.setattr(manager, "get_cache_service", lambda: cache)
    monkeypatch.setattr(manager, "_get_route_reservation_store", lambda: None)
    manager._runner_claim_gate_state = None

    manager.pause_runner_claim_gate({"reason": "postgres_maintenance"})
    resumed = manager.resume_runner_claim_gate()
    manager._runner_claim_gate_state = None

    assert resumed["state"] == "open"
    assert manager.RUNNER_CLAIM_GATE_KEY not in cache.values
    assert manager.get_runner_claim_gate()["state"] == "open"


def test_route_reservation_dual_writes_durable_ledger(monkeypatch):
    class _Store:
        def __init__(self):
            self.saved = []
            self.events = []

        def save_reservation(self, reservation):
            self.saved.append(dict(reservation))
            return reservation

        def append_event(self, event_type, **kwargs):
            self.events.append((event_type, kwargs))
            return {"event_type": event_type}

    cache = _MemoryCache()
    store = _Store()
    monkeypatch.setattr(manager, "get_cache_service", lambda: cache)
    monkeypatch.setattr(manager, "_get_route_reservation_store", lambda: store)
    manager._route_reservations.clear()

    reservation = manager.create_route_reservation(
        {
            "route_request": {
                "target_lane": "comfyui_runtime:flux2_klein_true_v2_q6_local",
                "resource_groups": ["apple_metal_heavy"],
                "drain_policy": "drain_after_current",
                "requested_by": "test",
            },
            "ttl_seconds": 120,
        }
    )

    assert reservation["ledger_persisted"] is True
    assert reservation["reservation_id"] in cache.values[manager.ROUTE_RESERVATIONS_KEY]
    assert store.saved[0]["reservation_id"] == reservation["reservation_id"]
    assert store.saved[0]["expires_at"]
    assert store.events[0][0] == "reservation_created"


def test_route_reservation_list_reads_durable_history_without_hot_active_path(monkeypatch):
    class _Store:
        def __init__(self):
            self.list_called = False

        def expire_stale_reservations(self, limit=100):
            return []

        def list_reservations(self, limit=100):
            self.list_called = True
            return [
                {
                    "reservation_id": "durable-1",
                    "state": "cancelled",
                    "created_at": "2026-05-14T00:00:00+00:00",
                    "route_request": {"target_lane": "runner:default_local"},
                }
            ]

    cache = _MemoryCache()
    store = _Store()
    monkeypatch.setattr(manager, "get_cache_service", lambda: cache)
    monkeypatch.setattr(manager, "_get_route_reservation_store", lambda: store)
    manager._route_reservations.clear()

    history = manager.list_route_reservations()
    active = manager.list_active_route_reservations()

    assert store.list_called is True
    assert history[0]["reservation_id"] == "durable-1"
    assert active == []


def test_route_reservation_list_can_filter_active_projection_without_db(monkeypatch):
    cache = _MemoryCache()
    cache.values[manager.ROUTE_RESERVATIONS_KEY] = {
        "hot-active": {
            "reservation_id": "hot-active",
            "state": "reserved_waiting",
            "created_at": "2026-05-14T00:00:02+00:00",
            "expires_at": "2999-01-01T00:00:00+00:00",
            "route_request": {"target_lane": "runner:default_local"},
        },
        "hot-history": {
            "reservation_id": "hot-history",
            "state": "cancelled",
            "created_at": "2026-05-14T00:00:01+00:00",
            "cancelled_at": "2026-05-14T00:01:00+00:00",
            "route_request": {"target_lane": "runner:default_local"},
        },
    }
    monkeypatch.setattr(manager, "get_cache_service", lambda: cache)
    monkeypatch.setattr(
        manager,
        "_get_route_reservation_store",
        lambda: (_ for _ in ()).throw(AssertionError("active UI path must not open DB")),
    )
    manager._route_reservations.clear()

    active = manager.list_route_reservations(
        include_durable=False,
        state="active",
        limit=10,
    )

    assert [reservation["reservation_id"] for reservation in active] == ["hot-active"]


def test_route_reservation_list_can_filter_history_and_limit(monkeypatch):
    class _Store:
        def expire_stale_reservations(self, limit=100):
            return []

        def list_reservations(self, limit=100):
            return [
                {
                    "reservation_id": "history-new",
                    "state": "cancelled",
                    "created_at": "2026-05-14T00:00:03+00:00",
                    "route_request": {"target_lane": "runner:default_local"},
                },
                {
                    "reservation_id": "active-1",
                    "state": "reserved_waiting",
                    "created_at": "2026-05-14T00:00:02+00:00",
                    "expires_at": "2999-01-01T00:00:00+00:00",
                    "route_request": {"target_lane": "runner:default_local"},
                },
                {
                    "reservation_id": "history-old",
                    "state": "expired",
                    "created_at": "2026-05-14T00:00:01+00:00",
                    "route_request": {"target_lane": "runner:default_local"},
                },
            ]

    cache = _MemoryCache()
    monkeypatch.setattr(manager, "get_cache_service", lambda: cache)
    monkeypatch.setattr(manager, "_get_route_reservation_store", lambda: _Store())
    manager._route_reservations.clear()

    history = manager.list_route_reservations(
        include_durable=True,
        state="history",
        limit=1,
    )

    assert [reservation["reservation_id"] for reservation in history] == ["history-new"]


def test_active_route_reservations_use_hot_projection_not_db(monkeypatch):
    cache = _MemoryCache()
    cache.values[manager.ROUTE_RESERVATIONS_KEY] = {
        "hot-1": {
            "reservation_id": "hot-1",
            "state": "reserved_waiting",
            "created_at": "2026-05-14T00:00:00+00:00",
            "expires_at": "2999-01-01T00:00:00+00:00",
            "route_request": {"target_lane": "runner:default_local"},
        }
    }
    monkeypatch.setattr(manager, "get_cache_service", lambda: cache)
    monkeypatch.setattr(
        manager,
        "_get_route_reservation_store",
        lambda: (_ for _ in ()).throw(AssertionError("hot path must not open DB")),
    )
    manager._route_reservations.clear()

    active = manager.list_active_route_reservations()

    assert [reservation["reservation_id"] for reservation in active] == ["hot-1"]


def test_route_reservation_events_return_durable_history(monkeypatch):
    class _Store:
        def list_events(self, reservation_id=None, limit=50):
            return [
                {
                    "event_id": "evt-1",
                    "reservation_id": reservation_id,
                    "event_type": "reservation_created",
                }
            ]

    monkeypatch.setattr(manager, "_get_route_reservation_store", lambda: _Store())

    events = manager.list_route_reservation_events(
        reservation_id="res-1",
        limit=10,
    )

    assert events == [
        {
            "event_id": "evt-1",
            "reservation_id": "res-1",
            "event_type": "reservation_created",
        }
    ]


def test_rehydrate_route_reservation_projection_restores_active_rows(monkeypatch):
    class _Store:
        def list_active_reservations(self, limit=100):
            return [
                {
                    "reservation_id": "durable-active",
                    "state": "reserved_waiting",
                    "created_at": "2026-05-14T00:00:00+00:00",
                    "expires_at": "2999-01-01T00:00:00+00:00",
                    "route_request": {"target_lane": "runner:default_local"},
                }
            ]

    cache = _MemoryCache()
    monkeypatch.setattr(manager, "get_cache_service", lambda: cache)
    monkeypatch.setattr(manager, "_get_route_reservation_store", lambda: _Store())
    manager._route_reservations.clear()

    restored = manager.rehydrate_route_reservation_projection()
    active = manager.list_active_route_reservations()

    assert restored[0]["reservation_id"] == "durable-active"
    assert cache.values[manager.ROUTE_RESERVATIONS_KEY]["durable-active"]
    assert active[0]["reservation_id"] == "durable-active"
