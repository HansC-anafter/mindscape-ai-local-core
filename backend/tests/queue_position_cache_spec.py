from backend.app.services.queue_position_cache import QueuePositionCache


def test_get_total_falls_back_to_raw_queue_shard_key():
    cache = QueuePositionCache()
    cache._eligible_totals["custom_lane"] = 7

    assert cache.get_total(" custom_lane ") == 7
