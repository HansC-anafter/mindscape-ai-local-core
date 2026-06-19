from datetime import timedelta

import pytest

from backend.app.services.host_runtime_sessions.bridge_registry import (
    HostRuntimeBridgeRegistry,
)
from backend.app.services.host_runtime_sessions.models import utc_now


@pytest.mark.asyncio
async def test_select_bridge_prefers_latest_workspace_specific_connection() -> None:
    registry = HostRuntimeBridgeRegistry()
    older = await registry.register(
        bridge_id="bridge-old",
        websocket=object(),
        runtime_surface="codex_cli",
        runtime_id="codex_cli",
        workspace_ids=["ws-1"],
    )
    newer = await registry.register(
        bridge_id="bridge-new",
        websocket=object(),
        runtime_surface="codex_cli",
        runtime_id="codex_cli",
        workspace_ids=["ws-1"],
    )
    now = utc_now()
    older.last_heartbeat_at = now - timedelta(seconds=60)
    newer.last_heartbeat_at = now

    selected = await registry.select_bridge(
        workspace_id="ws-1",
        runtime_surface="codex_cli",
        runtime_id="codex_cli",
    )

    assert selected is newer


@pytest.mark.asyncio
async def test_select_bridge_prefers_workspace_specific_over_global_connection() -> None:
    registry = HostRuntimeBridgeRegistry()
    global_bridge = await registry.register(
        bridge_id="bridge-global",
        websocket=object(),
        runtime_surface="codex_cli",
        runtime_id="codex_cli",
        workspace_ids=[],
    )
    workspace_bridge = await registry.register(
        bridge_id="bridge-workspace",
        websocket=object(),
        runtime_surface="codex_cli",
        runtime_id="codex_cli",
        workspace_ids=["ws-1"],
    )
    now = utc_now()
    global_bridge.last_heartbeat_at = now + timedelta(seconds=60)
    workspace_bridge.last_heartbeat_at = now

    selected = await registry.select_bridge(
        workspace_id="ws-1",
        runtime_surface="codex_cli",
        runtime_id="codex_cli",
    )

    assert selected is workspace_bridge
