import asyncio
import json
import urllib.request

import pytest

from backend.app.services.external_agents.bridge.host_ws_client import HostBridgeWSClient


def test_host_ws_client_switches_to_polling_after_repeated_403(monkeypatch, tmp_path):
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

    class _Forbidden(Exception):
        status_code = 403

    assert client._should_fallback_to_polling(_Forbidden()) is False
    assert client._should_fallback_to_polling(_Forbidden()) is False
    assert client._should_fallback_to_polling(_Forbidden()) is True

def test_host_ws_client_treats_transport_denial_errors_as_polling_candidates(
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

    error = RuntimeError("did not receive a valid HTTP response")

    assert client._should_fallback_to_polling(error) is False
    assert client._should_fallback_to_polling(error) is False
    assert client._should_fallback_to_polling(error) is True

def test_host_ws_client_treats_ws_open_timeout_as_polling_candidate(
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

    error = RuntimeError("timed out during opening handshake")

    assert client._should_fallback_to_polling(error) is False
    assert client._should_fallback_to_polling(error) is False
    assert client._should_fallback_to_polling(error) is True

def test_host_ws_client_polling_reserve_backoff_grows_and_caps(monkeypatch, tmp_path):
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

    delays = [
        client._polling_reserve_failure_delay(attempt)
        for attempt in range(1, 8)
    ]

    assert delays == [1.0, 2.0, 4.0, 8.0, 16.0, 30.0, 30.0]

@pytest.mark.asyncio
async def test_host_ws_client_handles_polled_dispatch_via_rest(monkeypatch, tmp_path):
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setenv("HOME", str(home_dir))

    async def _fake_task_handler(message):
        assert message["execution_id"] == "exec-1"
        return {
            "status": "completed",
            "output": "ok",
            "files_created": ["persona_operating_system.md"],
            "metadata": {"runtime_id": "runtime-codex-1"},
        }

    client = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
        client_id="client-1",
        task_handler=_fake_task_handler,
    )

    acknowledged: list[tuple[str, str]] = []
    submitted: list[dict[str, object]] = []

    def _fake_ack(execution_id: str, lease_id: str):
        acknowledged.append((execution_id, lease_id))
        return {"acknowledged": True}

    async def _fake_submit(message, *, queue_on_failure=True):
        submitted.append(message)
        return True

    monkeypatch.setattr(client, "_ack_reserved_task_via_rest_sync", _fake_ack)
    monkeypatch.setattr(client, "_submit_result_via_rest", _fake_submit)

    await client._handle_polled_dispatch(
        {
            "execution_id": "exec-1",
            "lease_id": "lease-1",
            "task": "Create deliverable",
        }
    )

    assert acknowledged == [("exec-1", "lease-1")]
    assert submitted[0]["execution_id"] == "exec-1"
    assert submitted[0]["lease_id"] == "lease-1"
    assert submitted[0]["metadata"]["transport"] == "polling"

@pytest.mark.asyncio
async def test_host_ws_client_acks_queued_ws_dispatches_without_blocking_receive_loop(
    monkeypatch, tmp_path
):
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setenv("HOME", str(home_dir))
    monkeypatch.setenv(
        "MINDSCAPE_RESULT_SPOOL_PATH",
        str(tmp_path / "host-ws-client-spool.json"),
    )

    allow_first_finish = asyncio.Event()
    first_started = asyncio.Event()
    second_started = asyncio.Event()
    completed: list[str] = []
    sent_messages: list[dict[str, object]] = []

    async def _fake_task_handler(message):
        execution_id = message["execution_id"]
        if execution_id == "exec-1":
            first_started.set()
            await allow_first_finish.wait()
        else:
            second_started.set()
        completed.append(execution_id)
        return {
            "status": "completed",
            "output": execution_id,
        }

    client = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
        client_id="client-1",
        task_handler=_fake_task_handler,
    )

    async def _fake_send(message):
        sent_messages.append(message)

    async def _fake_deliver_result(execution_id, result_message):
        sent_messages.append(
            {
                "type": "result",
                "execution_id": execution_id,
                "status": result_message["status"],
            }
        )
        return "ws_push"

    monkeypatch.setattr(client, "_send", _fake_send)
    monkeypatch.setattr(client, "_deliver_result", _fake_deliver_result)

    await client._handle_dispatch({"execution_id": "exec-1", "task": "first"})
    await asyncio.wait_for(first_started.wait(), timeout=1)

    await client._handle_dispatch({"execution_id": "exec-2", "task": "second"})
    await asyncio.sleep(0)

    acked_ids = [
        message["execution_id"]
        for message in sent_messages
        if message.get("type") == "ack"
    ]
    assert acked_ids == ["exec-1", "exec-2"]
    assert not second_started.is_set()

    allow_first_finish.set()
    await asyncio.wait_for(second_started.wait(), timeout=1)

    for _ in range(20):
        if completed == ["exec-1", "exec-2"]:
            break
        await asyncio.sleep(0.01)

    assert completed == ["exec-1", "exec-2"]

def test_host_ws_client_dispatch_lock_binds_to_running_loop(monkeypatch, tmp_path):
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setenv("HOME", str(home_dir))

    client = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
        client_id="client-1",
    )

    assert client._dispatch_lock is None
    assert client._dispatch_lock_loop is None

    async def _bind_lock():
        lock = client._get_dispatch_lock()
        assert lock is client._get_dispatch_lock()
        assert client._dispatch_lock is lock
        assert client._dispatch_lock_loop is asyncio.get_running_loop()

    asyncio.run(_bind_lock())

def test_host_ws_client_rest_result_payload_includes_attachments(monkeypatch, tmp_path):
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
    monkeypatch.setenv("MINDSCAPE_BACKEND_API_URL", "http://backend.test")

    captured = {}

    class _FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps({"accepted": True}).encode("utf-8")

    def _fake_urlopen(request, timeout=0):
        captured["url"] = request.full_url
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return _FakeResponse()

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)

    response = client._submit_result_via_rest_sync(
        {
            "execution_id": "exec-1",
            "status": "completed",
            "output": "ok",
            "lease_id": "lease-1",
            "attachments": [
                {
                    "filename": "persona_operating_system.md",
                    "content": "# Persona\n",
                }
            ],
            "metadata": {
                "effective_sandbox_path": "/tmp/ws",
                "transport": "polling",
            },
        }
    )

    assert response["accepted"] is True
    assert captured["url"] == "http://backend.test/api/v1/mcp/agent/result"
    assert captured["payload"]["lease_id"] == "lease-1"
    assert captured["payload"]["attachments"] == [
        {
            "filename": "persona_operating_system.md",
            "content": "# Persona\n",
        }
    ]
    assert captured["payload"]["metadata"]["transport"] == "polling"
