import asyncio

import pytest

from backend.app.runner.browser_fairness_cursor import (
    CURSOR_TTL_SECONDS,
    browser_fairness_cursor_key,
    browser_fairness_scan_cursor_key,
    claim_browser_fairness_scan_offset,
    read_browser_fairness_cursor,
    write_browser_fairness_cursor,
)


class FakeCursorClient:
    def __init__(self, value=None):
        self.value = value
        self.setex_calls = []
        self.counters = {}
        self.expire_calls = []

    async def get(self, key):
        return self.value

    async def setex(self, key, ttl_seconds, value):
        self.setex_calls.append((key, ttl_seconds, value))
        return True

    async def incrby(self, key, amount):
        next_value = int(self.counters.get(key) or 0) + int(amount)
        self.counters[key] = next_value
        return next_value

    async def expire(self, key, ttl_seconds):
        self.expire_calls.append((key, ttl_seconds))
        return True


def test_cursor_key_is_queue_shard_scoped():
    assert (
        browser_fairness_cursor_key("browser_local")
        == "mindscape:runner:browser_fair_cursor:v1:browser_local"
    )
    with pytest.raises(ValueError, match="queue_shard_required"):
        browser_fairness_cursor_key("  ")


def test_scan_cursor_key_is_queue_scoped():
    assert browser_fairness_scan_cursor_key("browser_local", "pending:browser_local") == (
        "mindscape:runner:browser_fair_scan_cursor:v1:browser_local:"
        "pending:browser_local"
    )
    with pytest.raises(ValueError, match="queue_name_required"):
        browser_fairness_scan_cursor_key("browser_local", "  ")


def test_cursor_read_normalizes_bytes_and_missing_value():
    assert (
        asyncio.run(
            read_browser_fairness_cursor(
                FakeCursorClient(b"ig_pin_post_detail"),
                queue_shard="browser_local",
            )
        )
        == "ig_pin_post_detail"
    )
    assert (
        asyncio.run(
            read_browser_fairness_cursor(
                FakeCursorClient(),
                queue_shard="browser_local",
            )
        )
        is None
    )


def test_cursor_write_uses_bounded_ttl_and_rejects_empty_lane():
    client = FakeCursorClient()
    assert asyncio.run(
        write_browser_fairness_cursor(
            client,
            queue_shard="browser_local",
            lane_key="ig_analyze_following",
        )
    )
    assert client.setex_calls == [
        (
            "mindscape:runner:browser_fair_cursor:v1:browser_local",
            CURSOR_TTL_SECONDS,
            "ig_analyze_following",
        )
    ]

    empty_client = FakeCursorClient()
    assert not asyncio.run(
        write_browser_fairness_cursor(
            empty_client,
            queue_shard="browser_local",
            lane_key="  ",
        )
    )
    assert empty_client.setex_calls == []


def test_scan_cursor_claims_consecutive_bounded_windows_and_wraps():
    client = FakeCursorClient()

    assert asyncio.run(
        claim_browser_fairness_scan_offset(
            client,
            queue_shard="browser_local",
            queue_name="pending:browser_local",
            queue_length=125,
            scan_limit=50,
        )
    ) == 0
    assert asyncio.run(
        claim_browser_fairness_scan_offset(
            client,
            queue_shard="browser_local",
            queue_name="pending:browser_local",
            queue_length=125,
            scan_limit=50,
        )
    ) == 50
    assert asyncio.run(
        claim_browser_fairness_scan_offset(
            client,
            queue_shard="browser_local",
            queue_name="pending:browser_local",
            queue_length=125,
            scan_limit=50,
        )
    ) == 100
    assert asyncio.run(
        claim_browser_fairness_scan_offset(
            client,
            queue_shard="browser_local",
            queue_name="pending:browser_local",
            queue_length=125,
            scan_limit=50,
        )
    ) == 25
    assert client.expire_calls[-1][1] == CURSOR_TTL_SECONDS


def test_scan_cursor_preserves_full_queue_order_when_limit_covers_queue():
    client = FakeCursorClient()

    assert asyncio.run(
        claim_browser_fairness_scan_offset(
            client,
            queue_shard="browser_local",
            queue_name="pending:browser_local",
            queue_length=10,
            scan_limit=50,
        )
    ) == 0
    assert client.counters == {}
