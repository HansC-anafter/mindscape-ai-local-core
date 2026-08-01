from unittest.mock import AsyncMock

import pytest

from backend.app.services.host_runtime_sessions.connection_lifecycle import (
    close_host_runtime_websocket,
)


@pytest.mark.asyncio
async def test_close_host_runtime_websocket_attempts_explicit_close():
    websocket = AsyncMock()

    await close_host_runtime_websocket(websocket)

    websocket.close.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_close_host_runtime_websocket_tolerates_already_closed_transport():
    websocket = AsyncMock()
    websocket.close.side_effect = RuntimeError("transport already closed")

    await close_host_runtime_websocket(websocket)

    websocket.close.assert_awaited_once_with()
