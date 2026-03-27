import asyncio
import inspect
import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.params import Query as QueryParam
from starlette.websockets import WebSocketDisconnect

from backend.app.routes.agent_dispatch import rest_endpoints, ws_endpoints


class ASGIAsyncTestClient:
    def __init__(self, app):
        self.app = app
        self.base_url = "http://testserver"

    def request(self, method, url, **kwargs):
        async def _request():
            transport = httpx.ASGITransport(app=self.app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url=self.base_url,
            ) as client:
                return await client.request(method, url, **kwargs)

        return asyncio.run(_request())

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)


class _FakeLeaseManager:
    def __init__(self):
        self.calls = []
        self._task_events = {}

    def reserve_pending_tasks(
        self,
        workspace_id: str,
        client_id: str,
        surface_type=None,
        limit: int = 5,
        lease_seconds: float = 60.0,
    ):
        self.calls.append(
            {
                "workspace_id": workspace_id,
                "client_id": client_id,
                "surface_type": surface_type,
                "limit": limit,
                "lease_seconds": lease_seconds,
            }
        )
        return []


class _FakeSocket:
    def __init__(self):
        self.messages = []

    async def send_text(self, payload: str):
        self.messages.append(json.loads(payload))

    async def receive_text(self):
        raise WebSocketDisconnect(code=1000)


class _FakeWebSocketManager:
    def __init__(self):
        self.connect_calls = []
        self.disconnect_calls = []
        self.background_started = 0

    async def connect(self, **kwargs):
        self.connect_calls.append(kwargs)
        return SimpleNamespace(
            authenticated=True,
            client_id=kwargs.get("client_id") or "generated-client",
            workspace_id=kwargs["workspace_id"],
        )

    def start_background_services(self):
        self.background_started += 1

    async def flush_pending(self, workspace_id, client):
        return 0

    def disconnect(self, client):
        self.disconnect_calls.append(client)


def _rest_app() -> FastAPI:
    app = FastAPI()
    app.include_router(rest_endpoints.router)
    return app


def test_pending_endpoint_omits_surface_filter_when_query_missing(monkeypatch):
    manager = _FakeLeaseManager()
    monkeypatch.setattr(rest_endpoints, "get_agent_dispatch_manager", lambda: manager)

    client = ASGIAsyncTestClient(_rest_app())
    response = client.get(
        "/api/v1/mcp/agent/pending",
        params={"workspace_id": "ws-1", "client_id": "client-1"},
    )

    assert response.status_code == 200
    assert response.json() == {"tasks": [], "count": 0}
    assert manager.calls == [
        {
            "workspace_id": "ws-1",
            "client_id": "client-1",
            "surface_type": None,
            "limit": 5,
            "lease_seconds": 60.0,
        }
    ]


def test_pending_endpoint_preserves_explicit_surface_filter(monkeypatch):
    manager = _FakeLeaseManager()
    monkeypatch.setattr(rest_endpoints, "get_agent_dispatch_manager", lambda: manager)

    client = ASGIAsyncTestClient(_rest_app())
    response = client.get(
        "/api/v1/mcp/agent/pending",
        params={
            "workspace_id": "ws-1",
            "client_id": "client-1",
            "surface": "codex_cli",
        },
    )

    assert response.status_code == 200
    assert manager.calls[0]["surface_type"] == "codex_cli"


def test_agent_websocket_declares_surface_as_required_query():
    parameter = inspect.signature(ws_endpoints.agent_websocket).parameters["surface"]

    assert isinstance(parameter.default, QueryParam)
    assert parameter.default.is_required()


@pytest.mark.asyncio
async def test_agent_websocket_passes_explicit_surface(monkeypatch):
    manager = _FakeWebSocketManager()
    monkeypatch.setattr(ws_endpoints, "get_agent_dispatch_manager", lambda: manager)

    websocket = _FakeSocket()
    await ws_endpoints.agent_websocket(
        websocket,
        workspace_id="ws-1",
        client_id="client-1",
        surface="codex_cli",
    )

    assert manager.background_started == 1
    assert len(manager.connect_calls) == 1
    assert manager.connect_calls[0]["workspace_id"] == "ws-1"
    assert manager.connect_calls[0]["client_id"] == "client-1"
    assert manager.connect_calls[0]["surface_type"] == "codex_cli"
    assert websocket.messages == [
        {
            "type": "welcome",
            "client_id": "client-1",
            "workspace_id": "ws-1",
            "flushed_tasks": 0,
        }
    ]
    assert len(manager.disconnect_calls) == 1
