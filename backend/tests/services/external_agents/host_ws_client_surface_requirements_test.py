import asyncio

import pytest

from backend.app.services.external_agents.bridge.host_ws_client import (
    HostBridgeWSClient,
)
from backend.app.services.external_agents.bridge.runtime_adapter import (
    HostBridgeRuntimeAdapter,
)


def test_host_bridge_ws_client_requires_surface():
    with pytest.raises(ValueError, match="surface is required"):
        HostBridgeWSClient(workspace_id="ws-1", host="localhost:8200", surface="")


def test_codex_surface_preflight_does_not_require_gemini_bridge(monkeypatch):
    monkeypatch.delenv("GEMINI_CLI_RUNTIME_CMD", raising=False)
    monkeypatch.setenv("MINDSCAPE_BACKEND_API_URL", "http://localhost:8200")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    client = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
    )

    client._preflight_check()


class _FakeWSManager:
    def __init__(self, results):
        self._results = list(results)
        self.calls = 0

    def has_connections(self, workspace_id=None, surface_type=None):
        self.calls += 1
        if not self._results:
            return False
        if len(self._results) == 1:
            return self._results[0]
        return self._results.pop(0)


def test_unavailable_availability_cache_expires_quickly_after_reconnect(monkeypatch):
    timeline = iter([100.0, 102.2])
    manager = _FakeWSManager([False, True])
    adapter = HostBridgeRuntimeAdapter(strategy="ws", ws_manager=manager)
    monkeypatch.setattr(
        "backend.app.services.external_agents.bridge.runtime_adapter.time.monotonic",
        lambda: next(timeline),
    )

    first = adapter.get_availability_detail(workspace_id="ws-1")
    second = adapter.get_availability_detail(workspace_id="ws-1")

    assert first == {
        "available": False,
        "transport": None,
        "reason": "no_ws_client",
    }
    assert second == {
        "available": True,
        "transport": "ws",
        "reason": "ws_connected",
    }
    assert manager.calls == 2


@pytest.mark.asyncio
async def test_result_ack_wait_avoids_rest_fallback_when_ack_arrives_in_time(monkeypatch):
    client = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
    )
    client.RESULT_ACK_TIMEOUT = 0.05

    fallback_calls = []

    async def _fake_submit(result_message):
        fallback_calls.append(result_message)

    monkeypatch.setattr(client, "_submit_result_via_rest", _fake_submit)

    waiter = asyncio.get_running_loop().create_future()

    async def _resolve_ack():
        await asyncio.sleep(0.01)
        waiter.set_result(True)

    asyncio.create_task(_resolve_ack())
    await client._wait_for_result_ack_or_fallback(
        "exec-1",
        waiter,
        {"execution_id": "exec-1"},
    )

    assert fallback_calls == []


@pytest.mark.asyncio
async def test_result_ack_wait_falls_back_after_timeout(monkeypatch):
    client = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
    )
    client.RESULT_ACK_TIMEOUT = 0.01

    fallback_calls = []

    async def _fake_submit(result_message):
        fallback_calls.append(result_message)

    monkeypatch.setattr(client, "_submit_result_via_rest", _fake_submit)

    waiter = asyncio.get_running_loop().create_future()
    result_message = {"execution_id": "exec-timeout"}

    await client._wait_for_result_ack_or_fallback(
        "exec-timeout",
        waiter,
        result_message,
    )

    assert fallback_calls == [result_message]


def test_pending_result_ack_counts_as_transport_work():
    client = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
    )

    loop = asyncio.new_event_loop()
    try:
        waiter = loop.create_future()
        client._result_ack_waiters["exec-1"] = waiter

        assert client._has_pending_transport_work() is True

        waiter.set_result(True)

        assert client._has_pending_transport_work() is False
    finally:
        loop.close()
