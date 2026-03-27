import asyncio

import pytest

from backend.app.services.external_agents.bridge.runtime_adapter import (
    HostBridgeRuntimeAdapter,
)
from backend.app.services.external_agents.core.base_adapter import RuntimeExecRequest


class _ConnectedWsManager:
    def has_connections(self, workspace_id=None, surface_type=None):
        return True

    async def dispatch_and_wait(self, **kwargs):
        raise asyncio.CancelledError("request scope cancelled")


@pytest.mark.asyncio
async def test_execute_via_ws_converts_cancelled_error_to_failure_response():
    adapter = HostBridgeRuntimeAdapter(
        strategy="ws",
        ws_manager=_ConnectedWsManager(),
    )
    request = RuntimeExecRequest(
        task="test",
        sandbox_path="/tmp/sandbox",
        workspace_id="ws-test",
        max_duration_seconds=300,
    )

    response = await adapter._execute_via_ws(request, "exec-123")

    assert response.success is False
    assert response.exit_code == -1
    assert response.agent_metadata["status"] == "cancelled"
    assert response.agent_metadata["transport"] == "ws_push"
    assert response.agent_metadata["execution_id"] == "exec-123"
    assert "cancelled" in (response.error or "").lower()


@pytest.mark.asyncio
async def test_execute_handles_cancelled_error_from_strategy_handler(monkeypatch):
    adapter = HostBridgeRuntimeAdapter(
        strategy="ws",
        ws_manager=_ConnectedWsManager(),
    )
    request = RuntimeExecRequest(
        task="test",
        sandbox_path="/tmp/sandbox",
        workspace_id="ws-test",
        max_duration_seconds=300,
    )

    async def _raise_cancelled(request, execution_id):
        raise asyncio.CancelledError("outer cancel")

    monkeypatch.setattr(adapter, "_execute_via_ws", _raise_cancelled)

    response = await adapter.execute(request)

    assert response.success is False
    assert response.exit_code == -1
    assert response.agent_metadata["status"] == "cancelled"
    assert response.agent_metadata["transport"] == "ws"
    assert "cancelled" in (response.error or "").lower()
