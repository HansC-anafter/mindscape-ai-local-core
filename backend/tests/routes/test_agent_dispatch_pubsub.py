import asyncio
import json

import pytest

from backend.app.routes.agent_dispatch.dispatch_manager import AgentDispatchManager
from backend.app.routes.agent_dispatch.models import AgentClient


class _FakeWebSocket:
    def __init__(self):
        self.messages = []

    async def send_text(self, payload: str) -> None:
        self.messages.append(json.loads(payload))


async def _wait_until(predicate, timeout: float = 1.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("condition not met before timeout")


def _wire_pubsub(origin: AgentDispatchManager, owner: AgentDispatchManager) -> None:
    origin._ensure_worker_identity = lambda: "origin-worker"
    owner._ensure_worker_identity = lambda: "owner-worker"
    origin.start_pubsub_listener = lambda: None
    owner.start_pubsub_listener = lambda: None
    origin._redis_pubsub_enabled = lambda: True
    owner._redis_pubsub_enabled = lambda: True

    async def publish_from_origin(target_worker_id: str, envelope):
        if target_worker_id == "owner-worker":
            await owner._handle_pubsub_envelope(envelope)
            return True
        if target_worker_id == "origin-worker":
            await origin._handle_pubsub_envelope(envelope)
            return True
        return False

    async def publish_from_owner(target_worker_id: str, envelope):
        if target_worker_id == "origin-worker":
            await origin._handle_pubsub_envelope(envelope)
            return True
        if target_worker_id == "owner-worker":
            await owner._handle_pubsub_envelope(envelope)
            return True
        return False

    origin._publish_pubsub_message = publish_from_origin
    owner._publish_pubsub_message = publish_from_owner


@pytest.mark.asyncio
async def test_pubsub_dispatch_relays_progress_and_result():
    origin = AgentDispatchManager()
    owner = AgentDispatchManager()
    _wire_pubsub(origin, owner)

    websocket = _FakeWebSocket()
    client = AgentClient(
        websocket=websocket,
        client_id="client-1",
        workspace_id="ws-1",
        surface_type="gemini_cli",
        authenticated=True,
    )
    owner._clients["ws-1"]["client-1"] = client

    origin._db_get_dispatch_target = lambda workspace_id, client_id=None, surface_type=None: {
        "workspace_id": workspace_id,
        "client_id": "client-1",
        "worker_instance_id": "owner-worker",
        "worker_pid": 200,
        "surface_type": "gemini_cli",
    }

    message = {
        "type": "dispatch",
        "workspace_id": "ws-1",
        "task": "test task",
        "context": {"thread_id": "thread-1"},
    }

    dispatch_task = asyncio.create_task(
        origin.dispatch_and_wait(
            workspace_id="ws-1",
            message=message,
            execution_id="exec-1",
            timeout=5.0,
        )
    )

    await _wait_until(lambda: bool(websocket.messages))
    assert websocket.messages == [message]

    owner._handle_progress(
        client,
        {
            "type": "progress",
            "execution_id": "exec-1",
            "progress": {"percent": 55, "message": "halfway"},
        },
    )
    await asyncio.sleep(0)

    origin_inflight = origin._inflight["exec-1"]
    assert origin_inflight.last_progress_pct == 55
    assert origin_inflight.last_progress_msg == "halfway"

    owner._handle_result(
        client,
        {
            "type": "result",
            "execution_id": "exec-1",
            "status": "completed",
            "output": "done",
            "metadata": {"source": "test"},
        },
    )
    await asyncio.sleep(0)

    result = await dispatch_task
    assert result["status"] == "completed"
    assert result["output"] == "done"
    assert "exec-1" in origin._completed


@pytest.mark.asyncio
async def test_pubsub_disconnect_falls_back_to_db_transport():
    origin = AgentDispatchManager()
    owner = AgentDispatchManager()
    _wire_pubsub(origin, owner)

    websocket = _FakeWebSocket()
    client = AgentClient(
        websocket=websocket,
        client_id="client-1",
        workspace_id="ws-1",
        surface_type="gemini_cli",
        authenticated=True,
    )
    owner._clients["ws-1"]["client-1"] = client

    origin._db_get_dispatch_target = lambda workspace_id, client_id=None, surface_type=None: {
        "workspace_id": workspace_id,
        "client_id": "client-1",
        "worker_instance_id": "owner-worker",
        "worker_pid": 200,
        "surface_type": "gemini_cli",
    }

    async def fake_db_fallback(
        workspace_id: str,
        message,
        execution_id: str,
        timeout: float = 600.0,
    ):
        return {
            "execution_id": execution_id,
            "status": "completed",
            "output": "db-fallback",
        }

    origin._cross_worker_dispatch_via_db = fake_db_fallback

    dispatch_task = asyncio.create_task(
        origin.dispatch_and_wait(
            workspace_id="ws-1",
            message={
                "type": "dispatch",
                "workspace_id": "ws-1",
                "task": "retry me",
            },
            execution_id="exec-2",
            timeout=5.0,
        )
    )

    await _wait_until(lambda: bool(websocket.messages))
    owner.disconnect(client)
    await asyncio.sleep(0)

    result = await dispatch_task
    assert result["status"] == "completed"
    assert result["output"] == "db-fallback"


@pytest.mark.asyncio
async def test_local_ack_timeout_evicts_stale_client_and_retries_shared_transport():
    manager = AgentDispatchManager()
    manager.ACK_DEADLINE_SECONDS = 0.01
    manager.WAIT_SLICE_SECONDS = 0.01
    manager._db_unregister_connection = lambda client_id: None

    websocket = _FakeWebSocket()
    client = AgentClient(
        websocket=websocket,
        client_id="codex-client",
        workspace_id="ws-1",
        surface_type="codex_cli",
        authenticated=True,
    )
    manager._clients["ws-1"]["codex-client"] = client

    async def fake_cross_worker_dispatch(
        workspace_id: str,
        message,
        execution_id: str,
        timeout: float = 600.0,
        target_client_id=None,
        surface_type=None,
    ):
        assert workspace_id == "ws-1"
        assert execution_id == "exec-ack-timeout"
        assert surface_type == "codex_cli"
        return {
            "execution_id": execution_id,
            "status": "completed",
            "output": "shared-transport-retry",
        }

    manager._cross_worker_dispatch = fake_cross_worker_dispatch

    message = {
        "type": "dispatch",
        "workspace_id": "ws-1",
        "agent_id": "codex_cli",
        "task": "retry this stale local client",
    }

    result = await manager.dispatch_and_wait(
        workspace_id="ws-1",
        message=message,
        execution_id="exec-ack-timeout",
        timeout=1.0,
    )

    assert websocket.messages == [message]
    assert result["status"] == "completed"
    assert result["output"] == "shared-transport-retry"
    assert manager.get_client("ws-1", "codex-client", surface_type="codex_cli") is None
    assert manager._pending_queue["ws-1"] == []
