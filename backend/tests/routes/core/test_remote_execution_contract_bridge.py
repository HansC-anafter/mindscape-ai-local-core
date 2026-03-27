import importlib
import importlib.util
import ast
import os
import sys
import types
from pathlib import Path
from typing import Any, Dict, Optional

import pytest
from pydantic import BaseModel, Field

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

_site_hub_root = os.path.abspath(os.path.join(_repo_root, "..", "site-hub"))
_site_hub_api_root = os.path.join(_site_hub_root, "site-hub-api")
_site_hub_common_root = os.path.join(_site_hub_root, "site-hub-common")
for _path in (_site_hub_api_root, _site_hub_common_root):
    if os.path.isdir(_path) and _path not in sys.path:
        sys.path.insert(0, _path)

pytestmark = pytest.mark.skipif(
    not (os.path.isdir(_cloud_root) and os.path.isdir(_site_hub_root)),
    reason="mindscape-ai-cloud and site-hub sibling repos required for bridge contract tests",
)


def _load_module(module_name: str, relative_path: str):
    module_path = os.path.join(_repo_root, relative_path)
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _load_site_hub_execution_control(monkeypatch):
    module_path = Path(_site_hub_api_root) / "v1" / "execution_control.py"
    tree = ast.parse(module_path.read_text(), filename=str(module_path))
    start_request = None
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "StartExecutionRequest":
            start_request = node
            break
    assert start_request is not None, "StartExecutionRequest not found in site-hub execution_control.py"

    isolated_module = ast.Module(body=[start_request], type_ignores=[])
    namespace = {
        "BaseModel": BaseModel,
        "Field": Field,
        "Optional": Optional,
        "Dict": Dict,
        "Any": Any,
    }
    exec(compile(isolated_module, str(module_path), "exec"), namespace)
    return namespace["StartExecutionRequest"]


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
    site_hub_execution_control = _load_site_hub_execution_control(monkeypatch)

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

    validated = site_hub_execution_control.model_validate(captured["json"])

    assert captured["url"] == "/api/v1/executions"
    assert result["id"] == "11111111-1111-4111-8111-111111111111"
    assert validated.tenant_id == "tenant-1"
    assert validated.execution_id == "11111111-1111-4111-8111-111111111111"
    assert validated.trace_id == "trace-1"
    assert validated.job_type == "playbook"
    assert validated.site_key == "tenant-1"
    assert validated.callback_payload["mode"] == "local_core_terminal_event"


@pytest.mark.asyncio
async def test_local_core_tool_dispatch_matches_cloud_start_schema(monkeypatch):
    connector_module = importlib.import_module(
        "backend.app.services.cloud_connector.connector"
    )
    site_hub_execution_control = _load_site_hub_execution_control(monkeypatch)

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
        request_payload={
            "tool_name": "ig.batch_vision",
            "inputs": {"batch_items": [{"image_url": "https://example.com/a.jpg"}]},
        },
        workspace_id="ws-1",
        capability_code="ig",
        execution_id="11111111-1111-4111-8111-111111111111",
        trace_id="trace-1",
        job_type="tool",
        callback_payload={"mode": "local_core_terminal_event"},
    )

    validated = site_hub_execution_control.model_validate(captured["json"])

    assert captured["url"] == "/api/v1/executions"
    assert result["id"] == "11111111-1111-4111-8111-111111111111"
    assert validated.tenant_id == "tenant-1"
    assert validated.execution_id == "11111111-1111-4111-8111-111111111111"
    assert validated.trace_id == "trace-1"
    assert validated.job_type == "tool"
    assert validated.capability_code == "ig"
    assert validated.site_key == "tenant-1"
    assert validated.request_payload["tool_name"] == "ig.batch_vision"
    assert validated.callback_payload["mode"] == "local_core_terminal_event"


@pytest.mark.asyncio
async def test_local_core_tool_dispatch_can_target_remote_device(monkeypatch):
    connector_module = importlib.import_module(
        "backend.app.services.cloud_connector.connector"
    )
    site_hub_execution_control = _load_site_hub_execution_control(monkeypatch)

    captured = {}

    class StubClient:
        async def post(self, url, json):
            captured["url"] = url
            captured["json"] = json
            return _StubResponse({"id": json["execution_id"], "state": "pending"})

    connector = connector_module.CloudConnector(
        cloud_ws_url="ws://cloud.test/api/v1/executor/ws",
        device_id="caller-local-core",
        tenant_id="tenant-1",
    )
    monkeypatch.setattr(connector, "_get_http_client", lambda: StubClient())

    monkeypatch.setenv("SITE_KEY", "site-alpha")

    await connector.start_remote_execution(
        tenant_id="tenant-1",
        playbook_code="core_llm.multimodal_analyze",
        request_payload={
            "tool_name": "core_llm.multimodal_analyze",
            "inputs": {"prompt": "analyze this"},
        },
        workspace_id="ws-1",
        capability_code="core_llm",
        execution_id="11111111-1111-4111-8111-111111111111",
        trace_id="trace-1",
        job_type="tool",
        target_device_id="gpu-vm-01",
    )

    validated = site_hub_execution_control.model_validate(captured["json"])

    assert captured["url"] == "/api/v1/executions"
    assert validated.device_id == "gpu-vm-01"
    assert validated.site_key == "site-alpha"


def test_cloud_connector_prefers_site_hub_api_env_over_cloud_api_url(monkeypatch):
    connector_module = importlib.import_module(
        "backend.app.services.cloud_connector.connector"
    )

    monkeypatch.setenv("CLOUD_API_URL", "https://old-cloud.example")
    monkeypatch.setenv("SITE_HUB_API_URL", "https://site-hub.example")
    monkeypatch.delenv("EXECUTION_CONTROL_API_URL", raising=False)

    connector = connector_module.CloudConnector(
        cloud_ws_url="ws://cloud.test/api/v1/executor/ws",
        device_id="gpu-vm-01",
        tenant_id="tenant-1",
    )

    client = connector._get_http_client()
    try:
        assert str(client.base_url).rstrip("/") == "https://site-hub.example"
    finally:
        import asyncio

        asyncio.run(client.aclose())


def test_cloud_connector_prefers_execution_control_api_env(monkeypatch):
    connector_module = importlib.import_module(
        "backend.app.services.cloud_connector.connector"
    )

    monkeypatch.setenv("CLOUD_API_URL", "https://old-cloud.example")
    monkeypatch.setenv("SITE_HUB_API_URL", "https://site-hub.example")
    monkeypatch.setenv("EXECUTION_CONTROL_API_URL", "https://control-plane.example")

    connector = connector_module.CloudConnector(
        cloud_ws_url="ws://cloud.test/api/v1/executor/ws",
        device_id="gpu-vm-01",
        tenant_id="tenant-1",
    )

    client = connector._get_http_client()
    try:
        assert str(client.base_url).rstrip("/") == "https://control-plane.example"
    finally:
        import asyncio

        asyncio.run(client.aclose())


class _FakeField:
    def __eq__(self, other):
        return ("eq", other)

    def __ne__(self, other):
        return ("ne", other)

    def is_(self, other):
        return ("is", other)

    def isnot(self, other):
        return ("isnot", other)

    def desc(self):
        return self


class _FakeRuntimeEnvironmentModel:
    id = _FakeField()
    supports_dispatch = _FakeField()
    config_url = _FakeField()
    auth_type = _FakeField()
    recommended_for_dispatch = _FakeField()
    is_default = _FakeField()
    updated_at = _FakeField()


class _FakeQuery:
    def __init__(self, result):
        self._result = result

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def first(self):
        return self._result


class _FakeSession:
    def __init__(self, results):
        self._results = list(results)

    def query(self, model):
        result = self._results.pop(0) if self._results else None
        return _FakeQuery(result)

    def close(self):
        return None


def _install_fake_runtime_modules(monkeypatch, results):
    fake_db_module = types.ModuleType("app.database")

    def _get_db_postgres():
        yield _FakeSession(results)

    fake_db_module.get_db_postgres = _get_db_postgres
    fake_runtime_module = types.ModuleType("app.models.runtime_environment")
    fake_runtime_module.RuntimeEnvironment = _FakeRuntimeEnvironmentModel

    monkeypatch.setitem(sys.modules, "app.database", fake_db_module)
    monkeypatch.setitem(sys.modules, "app.models.runtime_environment", fake_runtime_module)


def test_cloud_connector_uses_site_hub_runtime_config_url_from_db(monkeypatch):
    connector_module = importlib.import_module(
        "backend.app.services.cloud_connector.connector"
    )

    monkeypatch.delenv("EXECUTION_CONTROL_API_URL", raising=False)
    monkeypatch.delenv("SITE_HUB_API_URL", raising=False)
    monkeypatch.delenv("CLOUD_API_URL", raising=False)

    runtime = types.SimpleNamespace(id="site-hub", config_url="https://agent.anafter.co")
    _install_fake_runtime_modules(monkeypatch, [runtime])

    connector = connector_module.CloudConnector(
        cloud_ws_url="ws://cloud.test/api/v1/executor/ws",
        device_id="gpu-vm-01",
        tenant_id="tenant-1",
    )

    client = connector._get_http_client()
    try:
        assert str(client.base_url).rstrip("/") == "https://agent.anafter.co"
    finally:
        import asyncio

        asyncio.run(client.aclose())


def test_cloud_connector_omits_empty_authorization_header(monkeypatch):
    connector_module = importlib.import_module(
        "backend.app.services.cloud_connector.connector"
    )

    monkeypatch.delenv("EXECUTION_CONTROL_API_URL", raising=False)
    monkeypatch.delenv("SITE_HUB_API_URL", raising=False)
    monkeypatch.delenv("CLOUD_API_URL", raising=False)
    monkeypatch.delenv("CLOUD_API_KEY", raising=False)
    monkeypatch.delenv("CLOUD_PROVIDER_TOKEN", raising=False)

    site_hub_runtime = types.SimpleNamespace(
        id="site-hub",
        config_url="https://agent.anafter.co",
    )
    _install_fake_runtime_modules(monkeypatch, [site_hub_runtime])

    resolved = connector_module.CloudConnector._resolve_cloud_base_url()

    assert resolved == "https://agent.anafter.co"

    connector = connector_module.CloudConnector(
        cloud_ws_url="ws://cloud.test/api/v1/executor/ws",
        device_id="gpu-vm-01",
        tenant_id="tenant-1",
    )
    client = connector._get_http_client()
    try:
        assert "Authorization" not in client.headers
        assert client.headers["X-Device-Id"] == "gpu-vm-01"
    finally:
        import asyncio

        asyncio.run(client.aclose())


@pytest.mark.asyncio
async def test_cloud_connector_waits_for_terminal_result(monkeypatch):
    connector_module = importlib.import_module(
        "backend.app.services.cloud_connector.connector"
    )

    calls = []

    class StubClient:
        async def get(self, url, params=None):
            calls.append((url, params))
            if url.endswith("/result"):
                return _StubResponse(
                    {
                        "id": "11111111-1111-4111-8111-111111111111",
                        "state": "completed",
                        "result_payload": {"result": {"status": "completed"}},
                        "error_message": None,
                    }
                )
            state = "pending" if len(calls) == 1 else "completed"
            return _StubResponse(
                {
                    "id": "11111111-1111-4111-8111-111111111111",
                    "state": state,
                }
            )

    connector = connector_module.CloudConnector(
        cloud_ws_url="ws://cloud.test/api/v1/executor/ws",
        device_id="caller-local-core",
        tenant_id="tenant-1",
    )
    monkeypatch.setattr(connector, "_get_http_client", lambda: StubClient())

    result = await connector.wait_for_remote_execution_terminal_result(
        "11111111-1111-4111-8111-111111111111",
        tenant_id="tenant-1",
        timeout_seconds=5,
        poll_interval_seconds=0.01,
    )

    assert result["status"] == "completed"
    assert result["result_payload"]["result"]["status"] == "completed"
    assert calls[0][0] == "/api/v1/executions/11111111-1111-4111-8111-111111111111"
    assert calls[-1][0] == "/api/v1/executions/11111111-1111-4111-8111-111111111111/result"


@pytest.mark.asyncio
async def test_cloud_terminal_callback_matches_local_core_schema(monkeypatch):
    local_callback_module = _load_module(
        "test_remote_execution_callbacks_contract_module",
        "backend/app/routes/core/remote_execution_callbacks.py",
    )
    cloud_local_core_client = _load_module(
        "test_cloud_local_core_client_contract_module",
        "../mindscape-ai-cloud/services/local_core_client.py",
    )

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
    callback_signing_key = "fixture-callback-key-1"
    result = await client.report_remote_execution_terminal_event(
        tenant_id="tenant-1",
        workspace_id="ws-1",
        execution_id="11111111-1111-4111-8111-111111111111",
        trace_id="trace-1",
        job_type="tool",
        capability_code="ig",
        playbook_code="ig_batch_pin_references",
        status="succeeded",
        result_payload={"outputs": {"artifact": "x"}},
        provider_metadata={"cloud_state": "completed"},
        callback_secret=callback_signing_key,
    )

    validated = local_callback_module.RemoteTerminalEventRequest.model_validate(
        captured["json"]
    )

    assert (
        captured["endpoint"]
        == "http://local-core.test/api/v1/executions/remote-terminal-events"
    )
    assert captured["headers"]["Authorization"] == f"Bearer {callback_signing_key}"
    assert result["execution_id"] == "11111111-1111-4111-8111-111111111111"
    assert validated.execution_id == "11111111-1111-4111-8111-111111111111"
    assert validated.trace_id == "trace-1"
    assert validated.job_type == "tool"
    assert validated.capability_code == "ig"
    assert validated.status == "succeeded"
