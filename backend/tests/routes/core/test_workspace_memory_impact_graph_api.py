from pathlib import Path
import asyncio
import importlib.util

import httpx
from fastapi import APIRouter, FastAPI


def _load_workspace_governance_module():
    module_path = (
        Path(__file__).resolve().parents[3]
        / "app"
        / "routes"
        / "core"
        / "workspace_governance.py"
    )
    spec = importlib.util.spec_from_file_location(
        "workspace_governance_impact_graph_test_module", module_path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


class StubMemoryImpactGraphReadModel:
    def __init__(self):
        self.calls = []

    def build_for_workspace(
        self,
        workspace_id,
        *,
        session_id=None,
        execution_id=None,
        thread_id=None,
    ):
        self.calls.append(
            {
                "workspace_id": workspace_id,
                "session_id": session_id,
                "execution_id": execution_id,
                "thread_id": thread_id,
            }
        )
        return {
            "workspace_id": workspace_id,
            "session_id": session_id or "sess-1",
            "focus": {
                "workspace_id": workspace_id,
                "session_id": session_id or "sess-1",
                "focus_node_id": f"meeting_session:{session_id or 'sess-1'}",
                "project_id": "proj-1",
                "thread_id": thread_id,
                "execution_id": execution_id,
                "execution_ids": ["exec-1"],
            },
            "packet_summary": {
                "selected_node_count": 2,
                "route_sections": ["core", "episodic_evidence"],
                "counts_by_type": {"session": 1, "memory_item": 2},
                "selection": {"workspace_mode": "meeting"},
            },
            "nodes": [
                {
                    "id": f"meeting_session:{session_id or 'sess-1'}",
                    "type": "session",
                    "label": "Meeting Session",
                    "subtitle": "planning",
                    "status": "closed",
                    "metadata": {},
                },
                {
                    "id": "memory_item:mem-1",
                    "type": "memory_item",
                    "label": "Canonical Memory",
                    "subtitle": None,
                    "status": "candidate",
                    "metadata": {},
                },
            ],
            "edges": [
                {
                    "id": "selected_for_context:meeting_session:sess-1->memory_item:mem-1:explicit",
                    "from_node_id": f"meeting_session:{session_id or 'sess-1'}",
                    "to_node_id": "memory_item:mem-1",
                    "kind": "selected_for_context",
                    "provenance": "explicit",
                    "metadata": {},
                }
            ],
            "warnings": [],
        }


def test_workspace_memory_impact_graph_api_returns_route_payload(monkeypatch):
    module = _load_workspace_governance_module()
    read_model = StubMemoryImpactGraphReadModel()
    monkeypatch.setattr(module, "_get_memory_impact_graph_read_model", lambda: read_model)

    app = FastAPI()
    workspace_router = APIRouter(prefix="/api/v1/workspaces")
    workspace_router.include_router(module.router)
    app.include_router(workspace_router)
    client = ASGIAsyncTestClient(app)

    response = client.get(
        "/api/v1/workspaces/ws-1/governance/memory-impact-graph",
        params={"session_id": "sess-1", "execution_id": "exec-1", "thread_id": "thread-1"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["workspace_id"] == "ws-1"
    assert data["session_id"] == "sess-1"
    assert data["packet_summary"]["selected_node_count"] == 2
    assert data["nodes"][0]["type"] == "session"
    assert read_model.calls == [
        {
            "workspace_id": "ws-1",
            "session_id": "sess-1",
            "execution_id": "exec-1",
            "thread_id": "thread-1",
        }
    ]


def test_workspace_memory_impact_graph_api_returns_404_when_session_missing(monkeypatch):
    module = _load_workspace_governance_module()

    class MissingReadModel:
        def build_for_workspace(self, workspace_id, **kwargs):
            raise LookupError("Memory impact graph session not found")

    monkeypatch.setattr(
        module,
        "_get_memory_impact_graph_read_model",
        lambda: MissingReadModel(),
    )

    app = FastAPI()
    workspace_router = APIRouter(prefix="/api/v1/workspaces")
    workspace_router.include_router(module.router)
    app.include_router(workspace_router)
    client = ASGIAsyncTestClient(app)

    response = client.get("/api/v1/workspaces/ws-1/governance/memory-impact-graph")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"]
