import asyncio
import json

import pytest

from backend.app.routes.agent_dispatch.dispatch_manager import AgentDispatchManager
from backend.app.routes.agent_dispatch.db_fallback import DbFallbackMixin
from backend.app.routes.agent_dispatch.models import AgentClient, InflightTask


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
async def test_handle_result_ack_is_not_blocked_by_slow_landing(monkeypatch):
    manager = AgentDispatchManager()
    client = AgentClient(
        websocket=_FakeWebSocket(),
        client_id="client-1",
        workspace_id="ws-1",
        surface_type="codex_cli",
        authenticated=True,
    )
    result_future = asyncio.get_running_loop().create_future()
    manager._inflight["exec-1"] = InflightTask(
        execution_id="exec-1",
        workspace_id="ws-1",
        client_id="client-1",
        result_future=result_future,
        thread_id="thread-1",
        project_id="project-1",
    )

    landing_started = asyncio.Event()
    landing_release = asyncio.Event()

    monkeypatch.setattr(manager, "_persist_ws_result_to_db", lambda *args: None)

    async def _slow_land(*args, **kwargs):
        landing_started.set()
        await landing_release.wait()

    monkeypatch.setattr(manager, "_land_ws_result", _slow_land)

    response = manager._handle_result(
        client,
        {
            "type": "result",
            "execution_id": "exec-1",
            "status": "completed",
            "output": "done",
        },
    )

    assert response == {"type": "result_ack", "execution_id": "exec-1"}
    assert result_future.done() is True
    assert result_future.result()["output"] == "done"
    assert "exec-1" in manager._completed

    await asyncio.wait_for(landing_started.wait(), timeout=0.1)
    assert landing_release.is_set() is False

    landing_release.set()
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_handle_result_merges_dispatch_transport_inputs_into_result():
    manager = AgentDispatchManager()
    client = AgentClient(
        websocket=_FakeWebSocket(),
        client_id="client-1",
        workspace_id="ws-1",
        surface_type="codex_cli",
        authenticated=True,
    )
    result_future = asyncio.get_running_loop().create_future()
    manager._inflight["exec-transport-1"] = InflightTask(
        execution_id="exec-transport-1",
        workspace_id="ws-1",
        client_id="client-1",
        result_future=result_future,
        payload={
            "context": {
                "inputs": {
                    "deliverable_id": "D2",
                    "deliverable_name": "Week 1 calendar",
                    "deliverable_path": "instagram_week1_calendar.md",
                }
            }
        },
    )

    manager._persist_ws_result_to_db = lambda *args: None

    response = manager._handle_result(
        client,
        {
            "type": "result",
            "execution_id": "exec-transport-1",
            "status": "completed",
            "output": "done",
        },
    )

    assert response == {"type": "result_ack", "execution_id": "exec-transport-1"}
    resolved = result_future.result()
    assert resolved["deliverable_path"] == "instagram_week1_calendar.md"
    assert resolved["context"]["inputs"]["deliverable_id"] == "D2"


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
        *,
        target_client_id=None,
        surface_type=None,
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


def test_stale_disconnect_does_not_evict_reconnected_client():
    manager = AgentDispatchManager()
    unregister_calls = []
    manager._db_unregister_connection = lambda client_id: unregister_calls.append(
        client_id
    )

    old_client = AgentClient(
        websocket=_FakeWebSocket(),
        client_id="codex-client",
        workspace_id="ws-1",
        surface_type="codex_cli",
        authenticated=True,
    )
    new_client = AgentClient(
        websocket=_FakeWebSocket(),
        client_id="codex-client",
        workspace_id="ws-1",
        surface_type="codex_cli",
        authenticated=True,
    )

    manager._clients["ws-1"]["codex-client"] = old_client
    manager.disconnect(old_client)
    assert unregister_calls == ["codex-client"]

    manager._clients["ws-1"]["codex-client"] = new_client
    manager.disconnect(old_client)

    assert (
        manager.get_client("ws-1", "codex-client", surface_type="codex_cli")
        is new_client
    )
    assert unregister_calls == ["codex-client"]


@pytest.mark.asyncio
async def test_resume_state_returns_replayed_completions_and_duplicates():
    manager = AgentDispatchManager()
    client = AgentClient(
        websocket=_FakeWebSocket(),
        client_id="client-1",
        workspace_id="ws-1",
        surface_type="codex_cli",
        authenticated=True,
    )
    manager._completed["exec-old"] = {
        "execution_id": "exec-old",
        "completed_at": 10.0,
        "completed_at_monotonic": 1.0,
        "status": "completed",
        "landing_succeeded": True,
    }
    manager._completed["exec-new"] = {
        "execution_id": "exec-new",
        "completed_at": 20.0,
        "completed_at_monotonic": 2.0,
        "status": "completed",
        "landing_succeeded": False,
    }
    manager._inflight["exec-live"] = InflightTask(
        execution_id="exec-live",
        workspace_id="ws-1",
        client_id="client-2",
    )

    response = await manager.handle_message(
        client,
        {
            "type": "resume_state",
            "recent_execution_ids": ["exec-old"],
            "pending_rest_execution_ids": [],
            "last_completed_at": 0.0,
        },
    )

    assert response["type"] == "resume_sync"
    assert response["duplicates_to_ignore"] == ["exec-old"]
    assert response["tasks_to_requeue"] == [
        {"execution_id": "exec-live", "client_id": "client-2", "acked": False}
    ]
    assert response["replayed_completions"] == [
        {
            "execution_id": "exec-new",
            "completed_at": 20.0,
            "status": "completed",
            "landing_succeeded": False,
            "acceptance_state": None,
        }
    ]


@pytest.mark.asyncio
async def test_handle_result_marks_task_failed_when_landing_contract_fails(monkeypatch):
    manager = AgentDispatchManager()
    client = AgentClient(
        websocket=_FakeWebSocket(),
        client_id="client-1",
        workspace_id="ws-1",
        surface_type="codex_cli",
        authenticated=True,
    )
    result_future = asyncio.get_running_loop().create_future()
    manager._inflight["exec-landing-1"] = InflightTask(
        execution_id="exec-landing-1",
        workspace_id="ws-1",
        client_id="client-1",
        result_future=result_future,
    )

    monkeypatch.setattr(manager, "_persist_ws_result_to_db", lambda *args: None)

    async def _failing_land(*args, **kwargs):
        return {
            "success": False,
            "landing_failure": {
                "error_code": "deliverable_file_missing",
                "message": "missing markdown deliverable",
            },
        }

    monkeypatch.setattr(manager, "_land_ws_result", _failing_land)
    observed = {}
    observed_event = asyncio.Event()

    def _record_failure(**kwargs):
        observed.update(kwargs)
        observed_event.set()

    monkeypatch.setattr(
        manager,
        "_mark_ws_result_failed_after_landing",
        _record_failure,
    )

    response = manager._handle_result(
        client,
        {
            "type": "result",
            "execution_id": "exec-landing-1",
            "status": "completed",
            "output": "done",
        },
    )

    assert response == {"type": "result_ack", "execution_id": "exec-landing-1"}
    await asyncio.wait_for(observed_event.wait(), timeout=0.2)
    assert observed["execution_id"] == "exec-landing-1"
    assert observed["governance_result"]["landing_failure"]["error_code"] == (
        "deliverable_file_missing"
    )


def test_build_pending_dispatch_route_filter_limits_rows_to_local_routes():
    sql, params = DbFallbackMixin._build_pending_dispatch_route_filter(
        local_client_ids=["client-1"],
        workspace_surface_pairs=[("ws-1", "codex_cli")],
    )

    assert "target_client_id = ANY(%s)" in sql
    assert "target_client_id IS NULL" in sql
    assert "workspace_id = %s" in sql
    assert "(surface_type IS NULL OR surface_type = %s)" in sql
    assert params == [["client-1"], "ws-1", "codex_cli"]


@pytest.mark.asyncio
async def test_cross_worker_dispatch_via_db_receives_target_client_and_surface():
    manager = AgentDispatchManager()
    manager._redis_pubsub_enabled = lambda: False

    observed = {}

    async def fake_db_fallback(
        workspace_id: str,
        message,
        execution_id: str,
        timeout: float = 600.0,
        *,
        target_client_id=None,
        surface_type=None,
    ):
        observed.update(
            {
                "workspace_id": workspace_id,
                "execution_id": execution_id,
                "target_client_id": target_client_id,
                "surface_type": surface_type,
            }
        )
        return {
            "execution_id": execution_id,
            "status": "completed",
            "output": "db-fallback",
        }

    manager._cross_worker_dispatch_via_db = fake_db_fallback

    result = await manager._cross_worker_dispatch(
        workspace_id="ws-1",
        message={
            "type": "dispatch",
            "workspace_id": "ws-1",
            "agent_id": "codex_cli",
            "task": "hello",
        },
        execution_id="exec-db-route",
        timeout=5.0,
        target_client_id="client-1",
        surface_type="codex_cli",
    )

    assert result["status"] == "completed"
    assert observed == {
        "workspace_id": "ws-1",
        "execution_id": "exec-db-route",
        "target_client_id": "client-1",
        "surface_type": "codex_cli",
    }


@pytest.mark.asyncio
async def test_db_consumer_dispatches_to_matching_target_client(monkeypatch):
    manager = AgentDispatchManager()
    websocket = _FakeWebSocket()
    client = AgentClient(
        websocket=websocket,
        client_id="client-1",
        workspace_id="ws-1",
        surface_type="codex_cli",
        authenticated=True,
    )
    manager._clients["ws-1"]["client-1"] = client

    observed = {"pick_args": None, "written_result": None}
    call_count = {"value": 0}

    def fake_pick(limit, local_client_ids, workspace_surface_pairs):
        observed["pick_args"] = (
            limit,
            list(local_client_ids),
            list(workspace_surface_pairs),
        )
        if call_count["value"] > 0:
            return []
        call_count["value"] += 1
        return [
            {
                "execution_id": "exec-1",
                "workspace_id": "ws-1",
                "target_client_id": "client-1",
                "surface_type": "codex_cli",
                "payload": {
                    "type": "dispatch",
                    "workspace_id": "ws-1",
                    "agent_id": "codex_cli",
                    "task": "hello",
                },
            }
        ]

    async def fake_await_result(
        execution_id,
        result_future,
        timeout,
        context_label,
    ):
        return {
            "execution_id": execution_id,
            "status": "completed",
            "output": "done",
        }

    def fake_write_pending_result(execution_id, result):
        observed["written_result"] = (execution_id, result)

    monkeypatch.setattr(manager, "_db_pick_pending_dispatches", fake_pick)
    monkeypatch.setattr(manager, "_await_inflight_result", fake_await_result)
    monkeypatch.setattr(manager, "_db_write_pending_result", fake_write_pending_result)
    monkeypatch.setattr(manager, "_db_update_pending_status", lambda *args: None)

    consumer_task = asyncio.create_task(manager.consume_pending_dispatches())
    await _wait_until(lambda: bool(websocket.messages))
    consumer_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await consumer_task

    assert websocket.messages[0]["task"] == "hello"
    assert observed["pick_args"] == (
        5,
        ["client-1"],
        [("ws-1", "codex_cli")],
    )
    assert observed["written_result"] == (
        "exec-1",
        {
            "execution_id": "exec-1",
            "status": "completed",
            "output": "done",
        },
    )
