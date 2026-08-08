import asyncio
import json
import time

import pytest

from backend.app.services.external_agents.bridge.host_ws_client import HostBridgeWSClient


def test_resume_state_uses_exact_result_identity_without_timestamp_sweep(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv(
        "MINDSCAPE_RESULT_SPOOL_PATH",
        str(tmp_path / "resume-result-spool.json"),
    )
    client = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
        client_id="client-1",
        task_handler=lambda _: None,
    )
    client._recent_results["recent-execution"] = (
        time.monotonic(),
        time.time(),
        {"type": "result", "execution_id": "recent-execution"},
    )
    client._pending_rest_results["pending-execution"] = {
        "type": "result",
        "execution_id": "pending-execution",
    }

    message = client._build_resume_state_message()

    assert message == {
        "type": "resume_state",
        "recent_execution_ids": ["recent-execution"],
        "pending_rest_execution_ids": ["pending-execution"],
        "last_completed_at": None,
    }


@pytest.mark.asyncio
async def test_run_uses_websocket_as_readiness_probe_without_http_preflight(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("MINDSCAPE_BACKEND_API_URL", "http://localhost:8220")
    monkeypatch.setenv(
        "MINDSCAPE_RESULT_SPOOL_PATH",
        str(tmp_path / "run-result-spool.json"),
    )
    client = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
        client_id="client-1",
        task_handler=lambda _: None,
    )
    connected: list[str] = []

    async def _connect_once():
        connected.append(client.ws_url)
        client._running = False

    def _unexpected_http_preflight(*_args, **_kwargs):
        raise AssertionError("per-client HTTP readiness probe must not run")

    monkeypatch.setattr(client, "_connect_and_listen", _connect_once)
    monkeypatch.setattr(
        client,
        "_should_auto_register_host_session_runtime",
        lambda: False,
    )
    monkeypatch.setattr(
        "backend.app.services.external_agents.bridge.host_ws_client_core.transport_mixin.urllib.request.urlopen",
        _unexpected_http_preflight,
    )

    await client.run()

    assert connected == [client.ws_url]


def test_temporary_websocket_failure_does_not_downgrade_to_polling(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv(
        "MINDSCAPE_RESULT_SPOOL_PATH",
        str(tmp_path / "timeout-result-spool.json"),
    )
    client = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
        client_id="client-1",
        task_handler=lambda _: None,
    )
    client._ws_forbidden_count = client.WS_FORBIDDEN_POLLING_THRESHOLD - 1

    assert not client._should_fallback_to_polling(
        TimeoutError("timed out during opening handshake")
    )
    assert client._ws_forbidden_count == 0


def test_explicit_websocket_403_keeps_existing_polling_fallback(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv(
        "MINDSCAPE_RESULT_SPOOL_PATH",
        str(tmp_path / "forbidden-result-spool.json"),
    )
    client = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
        client_id="client-1",
        task_handler=lambda _: None,
    )

    assert not client._should_fallback_to_polling(RuntimeError("HTTP 403"))
    assert not client._should_fallback_to_polling(RuntimeError("HTTP 403"))
    assert client._should_fallback_to_polling(RuntimeError("HTTP 403"))


def test_failed_connection_backoff_spreads_idle_clients_across_fleet_window(
    monkeypatch, tmp_path
):
    monkeypatch.setenv(
        "MINDSCAPE_RESULT_SPOOL_PATH",
        str(tmp_path / "idle-backoff-result-spool.json"),
    )
    monkeypatch.setattr("random.uniform", lambda _start, _end: 0.0)
    client = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
        client_id="idle-client-1",
        task_handler=lambda _: None,
    )

    delay = client._backoff_delay()

    assert delay == pytest.approx(
        client.RECONNECT_BASE_DELAY
        + client._stable_client_offset(client.CLEAN_IDLE_RECONNECT_SPREAD)
    )
    assert client._reconnect_attempt == 1


def test_failed_connection_backoff_preserves_narrow_busy_client_window(
    monkeypatch, tmp_path
):
    monkeypatch.setenv(
        "MINDSCAPE_RESULT_SPOOL_PATH",
        str(tmp_path / "busy-backoff-result-spool.json"),
    )
    monkeypatch.setattr("random.uniform", lambda _start, _end: 0.0)
    client = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
        client_id="busy-client-1",
        task_handler=lambda _: None,
    )
    client._active_tasks = 1

    delay = client._backoff_delay()

    assert delay == pytest.approx(
        client.RECONNECT_BASE_DELAY
        + client._stable_client_offset(client.CLEAN_BUSY_RECONNECT_SPREAD)
    )
    assert delay <= (
        client.RECONNECT_BASE_DELAY + client.CLEAN_BUSY_RECONNECT_SPREAD
    )


@pytest.mark.asyncio
async def test_heartbeat_loop_closes_ws_when_send_raises(monkeypatch):
    class _BrokenWS:
        def __init__(self):
            self.closed = False

        async def send(self, _payload):
            raise RuntimeError("boom")

        async def close(self):
            self.closed = True

    client = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
        client_id="client-1",
        task_handler=lambda _: None,
    )
    client.HEARTBEAT_INTERVAL = 0
    client._ws = _BrokenWS()

    async def _stop_after_first_sleep(_seconds):
        return None

    monkeypatch.setattr(asyncio, "sleep", _stop_after_first_sleep)

    await client._heartbeat_loop()

    assert client._ws.closed is True


@pytest.mark.asyncio
async def test_heartbeat_loop_keeps_idle_socket_when_application_pong_lags(
    monkeypatch, tmp_path
):
    monkeypatch.setenv(
        "MINDSCAPE_RESULT_SPOOL_PATH",
        str(tmp_path / "heartbeat-result-spool.json"),
    )

    class _SlowPongWS:
        def __init__(self):
            self.closed = False
            self.sent: list[str] = []

        async def send(self, payload):
            self.sent.append(payload)

        async def close(self):
            self.closed = True

    client = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
        client_id="client-1",
        task_handler=lambda _: None,
    )
    ws = _SlowPongWS()
    client._ws = ws

    async def _no_delay(_seconds):
        return None

    async def _timeout_once(awaitable, *, timeout):
        assert timeout == client.PONG_TIMEOUT
        awaitable.close()
        client._ws = None
        raise asyncio.TimeoutError

    monkeypatch.setattr(asyncio, "sleep", _no_delay)
    monkeypatch.setattr(asyncio, "wait_for", _timeout_once)

    await client._heartbeat_loop()

    assert len(ws.sent) == 1
    assert ws.closed is False
    assert client._ws is None


@pytest.mark.asyncio
async def test_connect_and_listen_recreates_pong_event_per_connection(monkeypatch):
    stale_event = asyncio.Event()

    class _FakeWS:
        def __init__(self):
            self._delivered = False

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self._delivered:
                raise StopAsyncIteration
            self._delivered = True
            assert client._pong_received is not stale_event
            return json.dumps({"type": "pong"})

    class _FakeConnect:
        def __init__(self):
            self.ws = _FakeWS()

        async def __aenter__(self):
            return self.ws

        async def __aexit__(self, exc_type, exc, tb):
            return False

    client = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
        client_id="client-1",
        task_handler=lambda _: None,
    )
    client._pong_received = stale_event

    monkeypatch.setattr(
        "backend.app.services.external_agents.bridge.host_ws_client_core.transport_mixin.websockets.connect",
        lambda *args, **kwargs: _FakeConnect(),
    )

    await client._connect_and_listen()

    assert client._pong_received is None


@pytest.mark.asyncio
async def test_host_ws_client_skips_duplicate_registration_when_payload_unchanged(
    monkeypatch, tmp_path
):
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    codex_primary = home_dir / ".codex"
    codex_primary.mkdir()
    (codex_primary / "auth.json").write_text(
        json.dumps({"auth_mode": "host_session", "tokens": {"access_token": "seed"}}),
        encoding="utf-8",
    )

    monkeypatch.setenv("HOME", str(home_dir))
    monkeypatch.setenv("CODEX_HOME", str(codex_primary))

    client = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
        client_id="client-1",
        task_handler=lambda _: None,
    )

    calls: list[list[dict[str, object]]] = []

    def _fake_register(payloads=None):
        calls.append(payloads or [])
        return {"registered": True, "runtime_id": "runtime-codex-1"}

    monkeypatch.setattr(client, "_register_host_session_runtime_sync", _fake_register)

    await client._maybe_register_host_session_runtime()
    await client._maybe_register_host_session_runtime()

    assert len(calls) == 1

@pytest.mark.asyncio
async def test_host_ws_client_unknown_execution_error_triggers_rest_recovery(
    monkeypatch, tmp_path
):
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setenv("HOME", str(home_dir))

    client = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
        client_id="client-1",
        task_handler=lambda _: None,
    )

    execution_id = "11111111-2222-3333-4444-555555555555"
    result_message = {
        "type": "result",
        "execution_id": execution_id,
        "status": "completed",
        "output": "ok",
    }
    client._remember_result(execution_id, result_message)
    waiter = asyncio.get_running_loop().create_future()
    client._result_ack_waiters[execution_id] = waiter

    recovered: list[str] = []

    async def _fake_submit(message, *, queue_on_failure=True):
        recovered.append(message["execution_id"])
        return True

    monkeypatch.setattr(client, "_submit_result_via_rest", _fake_submit)

    await client._handle_message(
        {"type": "error", "error": f"Unknown execution {execution_id}"}
    )
    await asyncio.sleep(0)

    assert recovered == [execution_id]
    assert execution_id not in client._result_ack_waiters
