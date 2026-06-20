import json

import httpx
import pytest

from backend.app.services.cloud_connector.connector import CloudConnector
from backend.app.services.cloud_connector.remote_execution_client import (
    RemoteExecutionControlClient,
)


@pytest.mark.asyncio
async def test_remote_execution_client_dispatches_canonical_payload(monkeypatch):
    monkeypatch.delenv("SITE_KEY", raising=False)
    captured_requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        return httpx.Response(
            200,
            json={"id": "remote-exec-1", "state": "pending"},
        )

    http_client = httpx.AsyncClient(
        base_url="https://control.example",
        transport=httpx.MockTransport(handler),
    )
    client = RemoteExecutionControlClient(
        device_id="device-1",
        resolve_base_url=lambda: "https://control.example",
        http_client=http_client,
    )

    try:
        result = await client.start_remote_execution(
            tenant_id="tenant-1",
            playbook_code="playbook-a",
            request_payload={
                "_governance": {"site_key": "site-from-governance"},
                "input": 1,
            },
            workspace_id="workspace-1",
            capability_code="capability-a",
            execution_id="exec-1",
            trace_id="trace-1",
            job_type="tool",
            callback_payload={"mode": "local_core_terminal_event"},
            target_device_id="device-target",
        )
    finally:
        await http_client.aclose()

    assert result == {"id": "remote-exec-1", "state": "pending"}
    assert len(captured_requests) == 1
    request = captured_requests[0]
    assert request.method == "POST"
    assert request.url.path == "/api/v1/executions"
    payload = json.loads(request.content.decode("utf-8"))
    assert payload == {
        "tenant_id": "tenant-1",
        "execution_id": "exec-1",
        "trace_id": "trace-1",
        "job_type": "tool",
        "playbook_code": "playbook-a",
        "request_payload": {
            "_governance": {"site_key": "site-from-governance"},
            "input": 1,
        },
        "workspace_id": "workspace-1",
        "capability_code": "capability-a",
        "device_id": "device-target",
        "site_key": "site-from-governance",
        "callback_payload": {"mode": "local_core_terminal_event"},
    }


@pytest.mark.asyncio
async def test_connector_facade_delegates_terminal_wait_arguments():
    class FakeRemoteExecutionClient:
        def __init__(self):
            self.wait_call = None

        async def wait_for_terminal_result(
            self,
            execution_id,
            *,
            tenant_id=None,
            timeout_seconds=900.0,
            poll_interval_seconds=2.0,
        ):
            self.wait_call = {
                "execution_id": execution_id,
                "tenant_id": tenant_id,
                "timeout_seconds": timeout_seconds,
                "poll_interval_seconds": poll_interval_seconds,
            }
            return {"status": "completed"}

    connector = CloudConnector(
        cloud_ws_url="ws://control.example/api/v1/executor/ws",
        device_id="device-1",
        tenant_id="tenant-1",
    )
    fake_client = FakeRemoteExecutionClient()
    connector._remote_execution_client = fake_client

    result = await connector.wait_for_remote_execution_terminal_result(
        "exec-1",
        tenant_id="tenant-2",
        timeout_seconds=5.0,
        poll_interval_seconds=0.25,
    )

    assert result == {"status": "completed"}
    assert fake_client.wait_call == {
        "execution_id": "exec-1",
        "tenant_id": "tenant-2",
        "timeout_seconds": 5.0,
        "poll_interval_seconds": 0.25,
    }
