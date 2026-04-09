import asyncio
import urllib.error

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


def test_result_ack_timeout_can_be_overridden_via_env(monkeypatch):
    monkeypatch.setenv("MINDSCAPE_RESULT_ACK_TIMEOUT", "42.5")

    client = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
    )

    assert client.RESULT_ACK_TIMEOUT == pytest.approx(42.5)


def test_ws_open_timeout_can_be_overridden_via_env(monkeypatch):
    monkeypatch.setenv("MINDSCAPE_WS_OPEN_TIMEOUT", "27.5")

    client = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
    )

    assert client.WS_OPEN_TIMEOUT == pytest.approx(27.5)


def test_ws_pong_timeout_can_be_overridden_via_env(monkeypatch):
    monkeypatch.setenv("MINDSCAPE_WS_PONG_TIMEOUT", "91")

    client = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
    )

    assert client.PONG_TIMEOUT == pytest.approx(91.0)


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


def test_recent_disconnect_grace_keeps_surface_available(monkeypatch):
    timeline = iter([100.0, 101.0])
    manager = _FakeWSManager([True, False])
    adapter = HostBridgeRuntimeAdapter(strategy="ws", ws_manager=manager)
    adapter.WS_AVAILABLE_CACHE_TTL = 0.0
    monkeypatch.setattr(
        "backend.app.services.external_agents.bridge.runtime_adapter.time.monotonic",
        lambda: next(timeline),
    )

    first = adapter.get_availability_detail(workspace_id="ws-1")
    second = adapter.get_availability_detail(workspace_id="ws-1")

    assert first == {
        "available": True,
        "transport": "ws",
        "reason": "ws_connected",
    }
    assert second == {
        "available": True,
        "transport": "ws",
        "reason": "recent_reconnect_grace",
    }


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


@pytest.mark.asyncio
async def test_stale_connection_recovers_pending_result_acks_via_rest(monkeypatch):
    client = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
    )

    loop = asyncio.get_running_loop()
    waiter = loop.create_future()
    client._result_ack_waiters["exec-1"] = waiter
    client._remember_result("exec-1", {"execution_id": "exec-1", "status": "completed"})

    fallback_calls = []

    async def _fake_submit(result_message, *, queue_on_failure=True):
        fallback_calls.append((result_message["execution_id"], queue_on_failure))
        return True

    monkeypatch.setattr(client, "_submit_result_via_rest", _fake_submit)

    await client._recover_pending_result_acks_due_to_stale_connection()

    assert waiter.done() is True
    assert client._result_ack_waiters == {}
    assert fallback_calls == [("exec-1", True)]


@pytest.mark.asyncio
async def test_rest_fallback_queues_result_after_repeated_transient_failure(monkeypatch):
    client = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
    )
    client.RESULT_REST_RETRY_ATTEMPTS = 2
    client.RESULT_REST_RETRY_BASE_DELAY = 0.01

    def _always_fail(_result_message):
        raise urllib.error.URLError("backend restarting")

    monkeypatch.setattr(client, "_submit_result_via_rest_sync", _always_fail)

    delivered = await client._submit_result_via_rest({"execution_id": "exec-queued"})

    assert delivered is False
    assert client._pending_rest_results["exec-queued"]["execution_id"] == "exec-queued"


@pytest.mark.asyncio
async def test_flush_pending_results_drains_queue_on_success(monkeypatch):
    client = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
    )
    client._remember_pending_rest_result("exec-1", {"execution_id": "exec-1"})

    delivered = []

    async def _fake_submit(result_message, *, queue_on_failure=True):
        delivered.append((result_message["execution_id"], queue_on_failure))
        return True

    monkeypatch.setattr(client, "_submit_result_via_rest", _fake_submit)

    await client._flush_pending_results()

    assert delivered == [("exec-1", False)]
    assert client._pending_rest_results == {}


@pytest.mark.asyncio
async def test_welcome_schedules_pending_result_flush(monkeypatch):
    client = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
    )
    client._remember_pending_rest_result("exec-1", {"execution_id": "exec-1"})
    flushed = asyncio.Event()

    async def _fake_flush():
        flushed.set()

    monkeypatch.setattr(client, "_flush_pending_results", _fake_flush)

    await client._handle_message({"type": "welcome", "client_id": "c-1", "flushed_tasks": 0})
    await asyncio.wait_for(flushed.wait(), timeout=0.1)


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
