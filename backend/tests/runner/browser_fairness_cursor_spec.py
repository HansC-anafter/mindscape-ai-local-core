import asyncio

import pytest

from backend.app.runner.browser_fairness_cursor import (
    CURSOR_TTL_SECONDS,
    browser_fairness_cursor_key,
    read_browser_fairness_cursor,
    write_browser_fairness_cursor,
)


class FakeCursorClient:
    def __init__(self, value=None):
        self.value = value
        self.setex_calls = []

    async def get(self, key):
        return self.value

    async def setex(self, key, ttl_seconds, value):
        self.setex_calls.append((key, ttl_seconds, value))
        return True


def test_cursor_key_is_queue_shard_scoped():
    assert (
        browser_fairness_cursor_key("browser_local")
        == "mindscape:runner:browser_fair_cursor:v1:browser_local"
    )
    with pytest.raises(ValueError, match="queue_shard_required"):
        browser_fairness_cursor_key("  ")


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
