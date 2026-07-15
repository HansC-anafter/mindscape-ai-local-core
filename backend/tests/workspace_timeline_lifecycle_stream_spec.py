from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import backend.features.workspace.timeline as timeline_module
from backend.app.services.workspace_event_lifecycle import (
    publish_committed_workspace_event,
    serialize_mind_event_cloud_event,
    validate_workspace_lifecycle_event,
)
from backend.features.workspace.timeline_core.catchup import (
    load_workspace_event_catchup,
)
from backend.features.workspace.timeline_core.stream import event_stream_generator
from backend.features.workspace.timeline_core.subscription import (
    WorkspaceEventStreamUnavailable,
)


def _event(index: int, *, workspace_id: str = "workspace-stream") -> SimpleNamespace:
    return SimpleNamespace(
        id=f"event-{index:03d}",
        timestamp=datetime(2026, 7, 15, tzinfo=timezone.utc)
        + timedelta(seconds=index),
        actor="system",
        channel="workspace",
        profile_id="profile-1",
        project_id="project-1",
        workspace_id=workspace_id,
        thread_id="thread-1",
        event_type="message_created",
        payload={"index": index},
        entity_ids=[],
        metadata={"aggregate_id": "thread-1", "aggregate_version": index + 1},
    )


class ForwardStore:
    def __init__(self, events: list[SimpleNamespace], cursor: SimpleNamespace | None):
        self.events = events
        self.cursor = cursor
        self.page_calls: list[dict] = []

    def get_event(self, event_id: str):
        if self.cursor and self.cursor.id == event_id:
            return self.cursor
        return next((event for event in self.events if event.id == event_id), None)

    def get_events_after_cursor(
        self,
        workspace_id: str,
        *,
        after_id: str | None,
        start_time: datetime | None,
        limit: int,
    ):
        self.page_calls.append(
            {
                "workspace_id": workspace_id,
                "after_id": after_id,
                "start_time": start_time,
                "limit": limit,
            }
        )
        rows = self.events
        if after_id:
            if self.cursor and after_id == self.cursor.id:
                start_index = 0
            else:
                start_index = next(
                    index + 1 for index, event in enumerate(rows) if event.id == after_id
                )
            rows = rows[start_index:]
        elif start_time:
            rows = [event for event in rows if event.timestamp >= start_time]
        return rows[:limit]


@pytest.mark.asyncio
async def test_125_event_gap_uses_exact_50_50_25_forward_pages():
    cursor = _event(0)
    events = [_event(index) for index in range(1, 126)]
    store = ForwardStore(events, cursor)

    result = await load_workspace_event_catchup(
        store=store,
        workspace_id="workspace-stream",
        after_id=cursor.id,
        start_time=None,
    )

    assert result.page_sizes == [50, 50, 25]
    assert len(result.events) == 125
    assert result.last_event_id == "event-125"
    assert result.truncated is False
    assert [call["limit"] for call in store.page_calls] == [50, 50, 50]


@pytest.mark.asyncio
async def test_idle_heartbeat_does_not_issue_periodic_db_queries():
    class Store:
        calls = 0

        def get_events_after_cursor(self, *_args, **_kwargs):
            self.calls += 1
            return []

    class Subscription:
        subscribed_at = datetime.now(timezone.utc)
        closed = False

        async def next_payload(self, *, timeout_seconds: float):
            assert timeout_seconds == 15
            return None

        async def close(self):
            self.closed = True

    store = Store()
    subscription = Subscription()
    stream = event_stream_generator(
        workspace_id="workspace-idle",
        store=store,
        subscription=subscription,
    )

    assert "event: connected" in await stream.__anext__()
    assert await stream.__anext__() == ": heartbeat\n\n"
    assert store.calls == 1
    await stream.aclose()
    assert subscription.closed is True


@pytest.mark.asyncio
async def test_route_prefers_native_last_event_id_header(monkeypatch):
    captured: dict = {}

    class Subscription:
        pass

    async def open_subscription(workspace_id: str):
        captured["opened_workspace_id"] = workspace_id
        return Subscription()

    def generator(**kwargs):
        captured.update(kwargs)

        async def body():
            yield ": ready\n\n"

        return body()

    monkeypatch.setattr(
        timeline_module,
        "open_workspace_event_subscription",
        open_subscription,
    )
    monkeypatch.setattr(timeline_module, "event_stream_generator", generator)
    response = await timeline_module.stream_workspace_events(
        request=SimpleNamespace(is_disconnected=None),
        workspace_id="workspace-header",
        event_types=None,
        project_id=None,
        start_time=None,
        last_event_id="query-cursor",
        last_event_id_header="header-cursor",
        workspace=SimpleNamespace(id="workspace-header"),
        store=object(),
    )

    assert response.status_code == 200
    assert captured["opened_workspace_id"] == "workspace-header"
    assert captured["last_event_id"] == "header-cursor"


@pytest.mark.asyncio
async def test_route_returns_503_and_retry_after_when_redis_unavailable(monkeypatch):
    async def unavailable(_workspace_id: str):
        raise WorkspaceEventStreamUnavailable("workspace_event_redis_unavailable")

    monkeypatch.setattr(
        timeline_module,
        "open_workspace_event_subscription",
        unavailable,
    )
    with pytest.raises(HTTPException) as exc_info:
        await timeline_module.stream_workspace_events(
            request=SimpleNamespace(is_disconnected=None),
            workspace_id="workspace-unavailable",
            event_types=None,
            project_id=None,
            start_time=None,
            last_event_id=None,
            last_event_id_header=None,
            workspace=SimpleNamespace(id="workspace-unavailable"),
            store=object(),
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.headers == {"Retry-After": "15"}


def test_workspace_event_checksum_detects_domain_payload_mutation():
    event = serialize_mind_event_cloud_event(_event(1))
    validate_workspace_lifecycle_event(event, workspace_id="workspace-stream")
    event["data"]["payload"]["index"] = 99

    with pytest.raises(ValueError, match="checksum_mismatch"):
        validate_workspace_lifecycle_event(event, workspace_id="workspace-stream")


def test_committed_event_publisher_uses_dedicated_event_channel(monkeypatch):
    observed: dict = {}

    class Cache:
        def publish(self, channel: str, payload: str) -> bool:
            observed.update({"channel": channel, "payload": payload})
            return True

    monkeypatch.setattr(
        "backend.app.services.workspace_event_lifecycle.get_cache_service",
        lambda: Cache(),
    )
    assert publish_committed_workspace_event(_event(2)) is True
    assert observed["channel"] == "workspace:workspace-stream:events:v1"
    assert '"specversion":"1.0"' in observed["payload"]


def test_oversized_committed_event_is_not_published_or_raised(monkeypatch):
    event = _event(3)
    event.payload = {"oversized": "x" * 150_000}

    def unexpected_cache_read():
        raise AssertionError("oversized event must not reach Redis")

    monkeypatch.setattr(
        "backend.app.services.workspace_event_lifecycle.get_cache_service",
        unexpected_cache_read,
    )
    assert publish_committed_workspace_event(event) is False
