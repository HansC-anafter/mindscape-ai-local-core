import asyncio
import importlib.util
import sys
from types import SimpleNamespace
import types
from pathlib import Path

import httpx
from fastapi import FastAPI

from backend.app.models.workspace import Workspace


BACKEND_ROOT = Path(__file__).resolve().parents[3]


def _load_chat_model_preference_module():
    original_workspace_dependencies = sys.modules.get(
        "backend.app.routes.workspace_dependencies"
    )
    original_mindscape_store = sys.modules.get(
        "backend.app.services.mindscape_store"
    )

    fake_workspace_dependencies_module = types.ModuleType(
        "backend.app.routes.workspace_dependencies"
    )

    async def fake_get_workspace():
        return None

    async def fake_get_orchestrator():
        return None

    fake_workspace_dependencies_module.get_workspace = fake_get_workspace
    fake_workspace_dependencies_module.get_orchestrator = fake_get_orchestrator
    sys.modules["backend.app.routes.workspace_dependencies"] = (
        fake_workspace_dependencies_module
    )

    fake_mindscape_store_module = types.ModuleType(
        "backend.app.services.mindscape_store"
    )

    class FakeMindscapeStore:
        def __init__(self, *args, **kwargs):
            self.db_path = "postgres://test"

        async def update_workspace(self, workspace):
            return workspace

    fake_mindscape_store_module.MindscapeStore = FakeMindscapeStore
    sys.modules["backend.app.services.mindscape_store"] = fake_mindscape_store_module

    module_path = (
        BACKEND_ROOT
        / "app"
        / "routes"
        / "core"
        / "workspace"
        / "chat_model_preference.py"
    )
    spec = importlib.util.spec_from_file_location(
        "workspace_chat_model_preference_test_module",
        module_path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    finally:
        if original_workspace_dependencies is not None:
            sys.modules["backend.app.routes.workspace_dependencies"] = (
                original_workspace_dependencies
            )
        else:
            sys.modules.pop("backend.app.routes.workspace_dependencies", None)

        if original_mindscape_store is not None:
            sys.modules["backend.app.services.mindscape_store"] = (
                original_mindscape_store
            )
        else:
            sys.modules.pop("backend.app.services.mindscape_store", None)
    return module


module = _load_chat_model_preference_module()


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

    def put(self, url, **kwargs):
        return self.request("PUT", url, **kwargs)


def _make_workspace(executor_runtime: str | None = None) -> Workspace:
    return Workspace(
        id="ws-chat-model-001",
        title="Chat Model Workspace",
        owner_user_id="user-001",
        executor_runtime=executor_runtime,
        metadata={},
    )


def _install_test_doubles(monkeypatch, workspace: Workspace):
    class FakeModelStore:
        def get_all_models(self, model_type=None, enabled=None, provider=None):
            return [
                SimpleNamespace(
                    model_name="gpt-5.4",
                    provider_name="openai",
                    display_name="GPT-5.4",
                ),
                SimpleNamespace(
                    model_name="qwen3:8b",
                    provider_name="ollama",
                    display_name="Qwen 3 8B",
                ),
                SimpleNamespace(
                    model_name="llama3.1:8b",
                    provider_name="ollama",
                    display_name="Llama 3.1 8B",
                ),
            ]

        def initialize_default_models(self):
            return None

    class FakeAdapter:
        def __init__(self, available=True, reason=None):
            self.available = available
            self.reason = reason

        def get_availability_detail(self, workspace_id=None):
            return {
                "available": self.available,
                "reason": self.reason,
                "transport": "host_session",
            }

    class FakeRegistry:
        def discover_agents(self):
            return None

        def get_adapter(self, runtime_id):
            if runtime_id == workspace.resolved_executor_runtime:
                return FakeAdapter(available=True, reason=None)
            return None

    updated_workspaces = []

    class FakeStore:
        db_path = "postgres://test"

        async def update_workspace(self, updated_workspace):
            updated_workspaces.append(updated_workspace)
            return updated_workspace

    def fake_get_llm_provider_manager(profile_id=None, db_path=None):
        return SimpleNamespace(profile_id=profile_id, db_path=db_path)

    def fake_get_llm_provider(
        model_name,
        llm_provider_manager=None,
        profile_id=None,
        db_path=None,
    ):
        if model_name == "gpt-5.4":
            raise ValueError(
                "Provider 'openai' not available for model 'gpt-5.4'. Available providers: ['ollama']"
            )
        return (
            SimpleNamespace(
                is_model_available=lambda requested_model: (
                    requested_model == "llama3.1:8b",
                    None
                    if requested_model == "llama3.1:8b"
                    else f"Ollama model '{requested_model}' is not installed locally. Installed models: llama3.1:8b",
                )
            ),
            "OllamaProvider",
        )

    monkeypatch.setattr(module, "ModelConfigStore", FakeModelStore)
    monkeypatch.setattr(module, "get_runtime_registry", lambda: FakeRegistry())
    monkeypatch.setattr(
        module,
        "get_llm_provider_manager",
        fake_get_llm_provider_manager,
    )
    monkeypatch.setattr(module, "get_llm_provider", fake_get_llm_provider)
    monkeypatch.setattr(module, "store", FakeStore())

    app = FastAPI()
    app.include_router(module.router)
    app.dependency_overrides[module.get_workspace] = lambda: workspace
    return ASGIAsyncTestClient(app), updated_workspaces


def test_get_chat_model_preference_returns_runtime_scoped_options(monkeypatch):
    workspace = _make_workspace(executor_runtime="codex_cli")
    client, _ = _install_test_doubles(monkeypatch, workspace)

    response = client.get(f"/{workspace.id}/chat-model-preference")

    assert response.status_code == 200
    payload = response.json()
    assert payload["resolved_executor_runtime"] == "codex_cli"
    assert payload["current_selection"] is None
    assert payload["available_models"][0]["label"] == "GPT-5.4 via codex_cli"
    assert payload["available_models"][0]["available"] is True


def test_get_chat_model_preference_has_no_implicit_default(monkeypatch):
    workspace = _make_workspace(executor_runtime=None)
    client, _ = _install_test_doubles(monkeypatch, workspace)

    response = client.get(f"/{workspace.id}/chat-model-preference")

    assert response.status_code == 200
    payload = response.json()
    assert payload["available_models"][0]["id"] == "direct_llm:openai:gpt-5.4"
    assert payload["available_models"][0]["available"] is False
    assert "not available" in payload["available_models"][0]["disabled_reason"]
    assert payload["available_models"][1]["id"] == "direct_llm:ollama:qwen3:8b"
    assert payload["available_models"][1]["available"] is False
    assert "not installed locally" in payload["available_models"][1]["disabled_reason"]
    assert payload["available_models"][2]["id"] == "direct_llm:ollama:llama3.1:8b"
    assert payload["available_models"][2]["available"] is True
    assert payload["current_selection"] is None


def test_put_chat_model_preference_persists_workspace_metadata(monkeypatch):
    workspace = _make_workspace(executor_runtime=None)
    client, updated_workspaces = _install_test_doubles(monkeypatch, workspace)

    response = client.put(
        f"/{workspace.id}/chat-model-preference",
        json={"selection_id": "direct_llm:ollama:llama3.1:8b"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["current_selection"]["id"] == "direct_llm:ollama:llama3.1:8b"
    assert updated_workspaces
    persisted = updated_workspaces[-1].metadata["preferred_chat_model"]
    assert persisted["id"] == "direct_llm:ollama:llama3.1:8b"
    assert persisted["model_name"] == "llama3.1:8b"
    assert persisted["source_kind"] == "direct_llm"


def test_get_chat_model_preference_returns_explicit_workspace_selection(monkeypatch):
    workspace = _make_workspace(executor_runtime=None)
    workspace.metadata = {
        "preferred_chat_model": {
            "id": "direct_llm:ollama:llama3.1:8b",
            "model_name": "llama3.1:8b",
            "provider": "ollama",
            "source_kind": "direct_llm",
            "runtime_id": None,
        }
    }
    client, _ = _install_test_doubles(monkeypatch, workspace)

    response = client.get(f"/{workspace.id}/chat-model-preference")

    assert response.status_code == 200
    payload = response.json()
    assert payload["current_selection"]["id"] == "direct_llm:ollama:llama3.1:8b"


def test_put_chat_model_preference_rejects_unavailable_model(monkeypatch):
    workspace = _make_workspace(executor_runtime=None)
    client, updated_workspaces = _install_test_doubles(monkeypatch, workspace)

    response = client.put(
        f"/{workspace.id}/chat-model-preference",
        json={"selection_id": "direct_llm:ollama:qwen3:8b"},
    )

    assert response.status_code == 400
    assert "not installed locally" in response.json()["detail"]
    assert not updated_workspaces
