import time

from backend.app.services.queue_position_cache import QueuePositionCache


def test_get_total_falls_back_to_raw_queue_shard_key():
    cache = QueuePositionCache()
    cache._eligible_totals["custom_lane"] = 7
    cache._updated = time.monotonic()

    assert cache.get_total(" custom_lane ") == 7


def test_get_total_keeps_cold_cache_unknown():
    cache = QueuePositionCache()

    assert cache.get_total("custom_lane") is None
    assert cache.total is None
