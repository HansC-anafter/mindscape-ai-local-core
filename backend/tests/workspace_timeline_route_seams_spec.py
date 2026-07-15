from pathlib import Path
from datetime import datetime, timezone

import pytest

from backend.features.workspace.timeline import event_stream_generator


ROOT = Path(__file__).resolve().parents[2]
TIMELINE_PATH = ROOT / "backend" / "features" / "workspace" / "timeline.py"
STREAM_PATH = ROOT / "backend" / "features" / "workspace" / "timeline_core" / "stream.py"
CATCHUP_PATH = ROOT / "backend" / "features" / "workspace" / "timeline_core" / "catchup.py"
SUBSCRIPTION_PATH = ROOT / "backend" / "features" / "workspace" / "timeline_core" / "subscription.py"
LIFECYCLE_PATH = ROOT / "backend" / "app" / "services" / "workspace_event_lifecycle.py"
EVENTS_PATH = ROOT / "backend" / "features" / "workspace" / "timeline_core" / "events.py"
ITEMS_PATH = ROOT / "backend" / "features" / "workspace" / "timeline_core" / "items.py"


@pytest.mark.asyncio
async def test_event_stream_compat_export_stops_before_db_poll_when_disconnected():
    class Store:
        def get_events_after_cursor(self, *_args, **_kwargs):
            raise AssertionError("disconnected streams must not poll the database")

    class Subscription:
        subscribed_at = datetime.now(timezone.utc)

        async def close(self):
            return None

    async def disconnected() -> bool:
        return True

    stream = event_stream_generator(
        workspace_id="workspace-test",
        store=Store(),
        subscription=Subscription(),
        client_disconnected=disconnected,
    )

    first_chunk = await stream.__anext__()
    assert '"type": "connected"' in first_chunk

    with pytest.raises(StopAsyncIteration):
        await stream.__anext__()


def test_timeline_route_facade_keeps_public_paths_and_no_polling_loop():
    source = TIMELINE_PATH.read_text()

    assert '@router.get("/{workspace_id}/events", response_model=EventsListResponse)' in source
    assert '@router.get("/{workspace_id}/timeline", response_model=TimelineListResponse)' in source
    assert '@router.get("/{workspace_id}/events/stream")' in source
    assert 'media_type="text/event-stream"' in source
    assert '"Cache-Control": "no-cache, no-transform"' in source
    assert "while True" not in source
    assert "event_stream_generator" in source
    assert 'alias="Last-Event-ID"' in source
    assert "last_event_id_header or last_event_id" in source
    assert "open_workspace_event_subscription" in source
    assert 'status_code=503' in source
    assert '"Retry-After": "15"' in source


def test_stream_helper_preserves_resource_bounds():
    source = STREAM_PATH.read_text()

    assert "HEARTBEAT_INTERVAL = 15" in source
    assert "get_events_by_workspace" not in source
    assert "asyncio.sleep" not in source
    assert "meeting_stream_channel" not in source
    assert "should_stop_event_stream" in source
    assert "CATCHUP_PAGE_SIZE = 50" in CATCHUP_PATH.read_text()
    assert "MAX_CATCHUP_PAGES = 20" in CATCHUP_PATH.read_text()
    assert "workspace_event_channel" in SUBSCRIPTION_PATH.read_text()
    assert "MAX_WORKSPACE_EVENT_BYTES = 150_000" in LIFECYCLE_PATH.read_text()


def test_timeline_seam_files_stay_below_line_gate():
    paths = [
        TIMELINE_PATH,
        STREAM_PATH,
        CATCHUP_PATH,
        SUBSCRIPTION_PATH,
        LIFECYCLE_PATH,
        EVENTS_PATH,
        ITEMS_PATH,
        Path(__file__),
    ]

    for path in paths:
        assert len(path.read_text().splitlines()) <= 500, path
