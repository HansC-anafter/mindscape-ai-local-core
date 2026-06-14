from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import httpx
import yaml
from fastapi import FastAPI

from backend.app.models.workspace import Workspace

_ROUTE_PATH = (
    Path(__file__).resolve().parents[3]
    / "app"
    / "routes"
    / "core"
    / "workspace"
    / "composition_graph.py"
)
_ROUTE_SPEC = importlib.util.spec_from_file_location(
    "composition_graph_route_under_test",
    _ROUTE_PATH,
)
assert _ROUTE_SPEC is not None and _ROUTE_SPEC.loader is not None
composition_graph = importlib.util.module_from_spec(_ROUTE_SPEC)
_ROUTE_SPEC.loader.exec_module(composition_graph)


class MemoryArtifactsStore:
    def __init__(self):
        self.items = {}

    def create_artifact(self, artifact):
        self.items[artifact.id] = artifact
        return artifact

    def get_artifact(self, artifact_id):
        return self.items.get(artifact_id)

    def update_artifact(self, artifact_id, **kwargs):
        artifact = self.items.get(artifact_id)
        if artifact is None:
            return False
        self.items[artifact_id] = artifact.model_copy(update=kwargs)
        return True

    def get_by_thread(self, workspace_id, thread_id, limit=100):
        return [
            artifact
            for artifact in self.items.values()
            if artifact.workspace_id == workspace_id and artifact.thread_id == thread_id
        ][:limit]

    def list_artifacts_by_workspace(self, workspace_id, limit=None, offset=0):
        artifacts = [
            artifact
            for artifact in self.items.values()
            if artifact.workspace_id == workspace_id
        ]
        return artifacts[offset : offset + limit if limit else None]


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

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)

    def put(self, url, **kwargs):
        return self.request("PUT", url, **kwargs)


def write_demo_manifest(root: Path):
    cap_dir = root / "backend" / "app" / "capabilities" / "demo"
    cap_dir.mkdir(parents=True)
    manifest = {
        "id": "demo",
        "code": "demo",
        "name": "Demo",
        "version": "0.1.0",
        "composition_graph": {
            "enabled": True,
            "contract_version": "1.0.0",
            "accepted_object_roles": ["reference"],
            "node_types": [
                {
                    "id": "guidance_card",
                    "label": "Guidance Card",
                    "input_ports": [
                        {
                            "id": "object",
                            "direction": "input",
                            "data_type": "object_ref",
                            "required": True,
                        }
                    ],
                    "output_ports": [
                        {
                            "id": "guidance",
                            "direction": "output",
                            "data_type": "guidance",
                        }
                    ],
                    "payload_schema": {
                        "type": "object",
                        "required": ["intent"],
                        "properties": {"intent": {"type": "string"}},
                    },
                }
            ],
            "edge_types": [
                {
                    "id": "default",
                    "label": "Default",
                    "source_data_type": "any",
                    "target_data_type": "any",
                }
            ],
            "compile": {
                "backend": "capabilities.demo.services.compile:compile_graph",
                "output_mode": "meeting_command_envelope",
            },
        },
    }
    (cap_dir / "manifest.yaml").write_text(
        yaml.safe_dump(manifest, sort_keys=False),
        encoding="utf-8",
    )


def build_app(monkeypatch, tmp_path):
    write_demo_manifest(tmp_path)
    store = SimpleNamespace(artifacts=MemoryArtifactsStore())
    app = FastAPI()
    app.include_router(composition_graph.router, prefix="/api/v1/workspaces")
    app.dependency_overrides[composition_graph.get_store] = lambda: store
    app.dependency_overrides[composition_graph.get_workspace] = lambda: Workspace(
        id="ws",
        title="Workspace",
        owner_user_id="user",
    )
    monkeypatch.setattr(composition_graph, "_resolve_local_core_root", lambda: tmp_path)
    monkeypatch.setattr(composition_graph, "_get_installed_pack_ids", lambda: ["demo"])
    return app


def install_compile_module(monkeypatch):
    capabilities = types.ModuleType("capabilities")
    demo = types.ModuleType("capabilities.demo")
    services = types.ModuleType("capabilities.demo.services")
    compile_module = types.ModuleType("capabilities.demo.services.compile")

    def compile_graph(**kwargs):
        return {
            "command_envelope": {
                "meeting_id": kwargs["meeting_id"],
                "thread_id": kwargs["thread_id"],
                "intent_text": kwargs["command"],
                "requested_action": {
                    "verb": "demo_compile",
                    "pack_code": "demo",
                    "parameters": kwargs["action_parameters"],
                },
            }
        }

    compile_module.compile_graph = compile_graph
    monkeypatch.setitem(sys.modules, "capabilities", capabilities)
    monkeypatch.setitem(sys.modules, "capabilities.demo", demo)
    monkeypatch.setitem(sys.modules, "capabilities.demo.services", services)
    monkeypatch.setitem(sys.modules, "capabilities.demo.services.compile", compile_module)


def graph_payload():
    return {
        "selected_primary_pack": "demo",
        "nodes": [
            {
                "id": "ref",
                "type": "object_reference",
                "payload": {
                    "ref": {
                        "uri": "mindscape://demo/reference/ref_1",
                        "owner_pack": "demo",
                        "object_kind": "reference",
                        "object_id": "ref_1",
                        "workspace_id": "ws",
                    }
                },
            },
            {
                "id": "guidance",
                "type": "guidance_card",
                "payload": {"intent": "Clarify decision."},
            },
        ],
        "edges": [
            {
                "id": "e1",
                "source": "ref",
                "source_port": "object",
                "target": "guidance",
                "target_port": "object",
            }
        ],
    }


def test_composition_graph_routes_cover_contracts_draft_import_export_and_compile(
    monkeypatch,
    tmp_path,
):
    install_compile_module(monkeypatch)
    client = ASGIAsyncTestClient(build_app(monkeypatch, tmp_path))

    contracts = client.get("/api/v1/workspaces/ws/composition-graph/contracts")
    assert contracts.status_code == 200
    assert contracts.json()["contracts"][0]["capability_code"] == "demo"

    draft_response = client.post(
        "/api/v1/workspaces/ws/composition-graph/drafts",
        json={
            "title": "Route draft",
            "meeting_id": "mtg",
            "thread_id": "thread",
            **graph_payload(),
        },
    )
    assert draft_response.status_code == 200
    draft_id = draft_response.json()["draft"]["id"]

    listed = client.get(
        "/api/v1/workspaces/ws/composition-graph/drafts?thread_id=thread"
    )
    assert listed.status_code == 200
    assert listed.json()["drafts"][0]["id"] == draft_id

    exported = client.get(
        f"/api/v1/workspaces/ws/composition-graph/drafts/{draft_id}/export"
    )
    assert exported.status_code == 200
    assert exported.json()["metadata"]["export_checksum"]

    imported = client.post(
        "/api/v1/workspaces/ws/composition-graph/import",
        json={
            "thread_id": "thread",
            "graph": {
                "graph_id": "portable",
                "title": "Portable",
                **graph_payload(),
            },
        },
    )
    assert imported.status_code == 200
    assert imported.json()["valid"] is True

    compiled = client.post(
        "/api/v1/workspaces/ws/composition-graph/compile",
        json={
            "draft_id": draft_id,
            "meeting_id": "mtg",
            "thread_id": "thread",
            "command": "Compile graph",
            "action_parameters": {"mode": "review"},
        },
    )
    assert compiled.status_code == 200
    payload = compiled.json()
    assert payload["status"] == "succeeded"
    assert payload["command_envelope"]["requested_action"]["pack_code"] == "demo"


def test_composition_graph_import_returns_diagnostics(monkeypatch, tmp_path):
    client = ASGIAsyncTestClient(build_app(monkeypatch, tmp_path))

    response = client.post(
        "/api/v1/workspaces/ws/composition-graph/import",
        json={
            "graph": {
                "graph_id": "invalid",
                "nodes": [{"id": "bad", "type": "unknown"}],
                "edges": [],
            }
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["valid"] is False
    assert payload["diagnostics"][0]["code"] == "unknown_node_type"


def test_composition_graph_run_exposes_run_harness_observation(monkeypatch, tmp_path):
    client = ASGIAsyncTestClient(build_app(monkeypatch, tmp_path))

    run_response = client.post(
        "/api/v1/workspaces/ws/composition-graph/run",
        json={
            "graph_id": "graph-observation",
            "command": "Observe run harness state",
            "nodes": [],
            "edges": [],
        },
    )
    assert run_response.status_code == 200
    run_id = run_response.json()["run"]["id"]

    observation = client.get(
        f"/api/v1/workspaces/ws/composition-graph/runs/{run_id}/run-harness-observation"
    )

    assert observation.status_code == 200
    payload = observation.json()
    assert payload["workspace_id"] == "ws"
    assert payload["episode"]["episode_id"] == f"composition-graph-episode:{run_id}"
    assert payload["result"]["run_id"] == run_id
    assert payload["result"]["harness_kind"] == "composition_graph"
    assert payload["source"] == "composition_graph_run"
