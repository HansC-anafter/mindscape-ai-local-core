from backend.app.services.host_resources import manager


class _MemoryCache:
    def __init__(self):
        self.values = {}

    def get_json(self, key):
        return self.values.get(key)

    def set_json(self, key, value, ttl=None):
        self.values[key] = value
        return True


def test_route_reservation_is_written_to_ttl_state(monkeypatch):
    cache = _MemoryCache()
    monkeypatch.setattr(manager, "get_cache_service", lambda: cache)
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
