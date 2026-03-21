import importlib
import importlib.util
import os
import sys

import pytest

_repo_root = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
)
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)
_backend_root = os.path.join(_repo_root, "backend")
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

_cloud_root = os.path.abspath(os.path.join(_repo_root, "..", "mindscape-ai-cloud"))
if os.path.isdir(_cloud_root) and _cloud_root not in sys.path:
    sys.path.insert(0, _cloud_root)

pytestmark = pytest.mark.skipif(
    not os.path.isdir(_cloud_root),
    reason="mindscape-ai-cloud sibling repo required for bridge contract tests",
)


def _load_module(module_name: str, relative_path: str):
    module_path = os.path.join(_repo_root, relative_path)
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class _StubResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


@pytest.mark.asyncio
async def test_local_core_remote_dispatch_matches_cloud_start_schema(monkeypatch):
    connector_module = importlib.import_module(
        "backend.app.services.cloud_connector.connector"
    )
    cloud_execution_control = importlib.import_module("api.v1.execution_control")

    captured = {}

    class StubClient:
        async def post(self, url, json):
            captured["url"] = url
            captured["json"] = json
            return _StubResponse({"id": json["execution_id"], "state": "pending"})

    connector = connector_module.CloudConnector(
        cloud_ws_url="ws://cloud.test/api/v1/executor/ws",
        device_id="gpu-vm-01",
        tenant_id="tenant-1",
    )
    monkeypatch.setattr(connector, "_get_http_client", lambda: StubClient())

    result = await connector.start_remote_execution(
        tenant_id="tenant-1",
        playbook_code="ig_batch_pin_references",
        request_payload={"inputs": {"batch_id": "b-1"}},
        workspace_id="ws-1",
        execution_id="11111111-1111-4111-8111-111111111111",
        trace_id="trace-1",
        job_type="playbook",
        callback_payload={"mode": "local_core_terminal_event"},
    )

    validated = cloud_execution_control.StartExecutionRequest.model_validate(
        captured["json"]
    )

    assert captured["url"] == "/api/v1/executions"
    assert result["id"] == "11111111-1111-4111-8111-111111111111"
    assert validated.tenant_id == "tenant-1"
    assert validated.execution_id == "11111111-1111-4111-8111-111111111111"
    assert validated.trace_id == "trace-1"
    assert validated.job_type == "playbook"
    assert validated.callback_payload["mode"] == "local_core_terminal_event"


@pytest.mark.asyncio
async def test_cloud_terminal_callback_matches_local_core_schema(monkeypatch):
    local_callback_module = _load_module(
        "test_remote_execution_callbacks_contract_module",
        "backend/app/routes/core/remote_execution_callbacks.py",
    )
    cloud_local_core_client = importlib.import_module("services.local_core_client")

    captured = {}

    class StubAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, endpoint, json, headers):
            captured["endpoint"] = endpoint
            captured["json"] = json
            captured["headers"] = headers
            return _StubResponse({"success": True, "execution_id": json["execution_id"]})

    monkeypatch.setattr(cloud_local_core_client.httpx, "AsyncClient", StubAsyncClient)

    client = cloud_local_core_client.LocalCoreClient(
        base_url="http://local-core.test",
        timeout_seconds=5,
    )
    result = await client.report_remote_execution_terminal_event(
        tenant_id="tenant-1",
        workspace_id="ws-1",
        execution_id="11111111-1111-4111-8111-111111111111",
        trace_id="trace-1",
        playbook_code="ig_batch_pin_references",
        status="succeeded",
        result_payload={"outputs": {"artifact": "x"}},
        provider_metadata={"cloud_state": "completed"},
        callback_secret="secret-1",
    )

    validated = local_callback_module.RemoteTerminalEventRequest.model_validate(
        captured["json"]
    )

    assert (
        captured["endpoint"]
        == "http://local-core.test/api/v1/executions/remote-terminal-events"
    )
    assert captured["headers"]["Authorization"] == "Bearer secret-1"
    assert result["execution_id"] == "11111111-1111-4111-8111-111111111111"
    assert validated.execution_id == "11111111-1111-4111-8111-111111111111"
    assert validated.trace_id == "trace-1"
    assert validated.status == "succeeded"
