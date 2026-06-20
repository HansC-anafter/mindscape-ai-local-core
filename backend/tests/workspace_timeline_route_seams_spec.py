from pathlib import Path

import pytest

from backend.features.workspace.timeline import event_stream_generator


ROOT = Path(__file__).resolve().parents[2]
TIMELINE_PATH = ROOT / "backend" / "features" / "workspace" / "timeline.py"
STREAM_PATH = ROOT / "backend" / "features" / "workspace" / "timeline_core" / "stream.py"
EVENTS_PATH = ROOT / "backend" / "features" / "workspace" / "timeline_core" / "events.py"
ITEMS_PATH = ROOT / "backend" / "features" / "workspace" / "timeline_core" / "items.py"


@pytest.mark.asyncio
async def test_event_stream_compat_export_stops_before_db_poll_when_disconnected():
    class Store:
        def get_events_by_workspace(self, **_kwargs):
            raise AssertionError("disconnected streams must not poll the database")

    async def disconnected() -> bool:
        return True

    stream = event_stream_generator(
        workspace_id="workspace-test",
        store=Store(),
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


def test_stream_helper_preserves_resource_bounds():
    source = STREAM_PATH.read_text()

    assert "HEARTBEAT_INTERVAL = 30" in source
    assert "limit=100" in source
    assert "range(50)" in source
    assert "timeout=0.01" in source
    assert "await asyncio.sleep(1)" in source
    assert "await asyncio.sleep(5)" in source
    assert "should_stop_event_stream" in source


def test_timeline_seam_files_stay_below_line_gate():
    paths = [
        TIMELINE_PATH,
        STREAM_PATH,
        EVENTS_PATH,
        ITEMS_PATH,
        Path(__file__),
    ]

    for path in paths:
        assert len(path.read_text().splitlines()) <= 500, path
