import logging

import pytest

from backend.features.workspace.event_stream_lifecycle import should_stop_event_stream
from backend.features.workspace.timeline import event_stream_generator


@pytest.mark.asyncio
async def test_should_stop_event_stream_returns_false_without_probe():
    assert (
        await should_stop_event_stream(
            None,
            logger=logging.getLogger("test"),
            workspace_id="workspace-test",
        )
        is False
    )


@pytest.mark.asyncio
async def test_should_stop_event_stream_uses_disconnect_probe():
    async def disconnected() -> bool:
        return True

    assert (
        await should_stop_event_stream(
            disconnected,
            logger=logging.getLogger("test"),
            workspace_id="workspace-test",
        )
        is True
    )


@pytest.mark.asyncio
async def test_should_stop_event_stream_keeps_stream_when_probe_fails():
    async def failing_probe() -> bool:
        raise RuntimeError("probe unavailable")

    assert (
        await should_stop_event_stream(
            failing_probe,
            logger=logging.getLogger("test"),
            workspace_id="workspace-test",
        )
        is False
    )


@pytest.mark.asyncio
async def test_event_stream_generator_stops_before_db_poll_when_client_disconnected():
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
