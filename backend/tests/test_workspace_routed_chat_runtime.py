from types import SimpleNamespace

import pytest

from backend.app.services.llm import workspace_routed_chat
from backend.app.services.llm.workspace_routed_chat import (
    chat_completion_with_workspace_route,
)


class _FailingProvider:
    async def chat_completion(self, messages, **kwargs):
        raise AssertionError("managed provider must not be called")


class _Provider:
    def __init__(self):
        self.calls = []

    async def chat_completion(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        return "provider-output"


class _FakeRoutingPolicy:
    def resolve_chat_default(self):
        return SimpleNamespace(model_name="gpt-5.4", provider="openai")

    def resolve_registered_model(self, *, model_name, model_type=None, source="requested_model"):
        return SimpleNamespace(
            model_name=model_name,
            provider="openai",
            metadata={},
            source=source,
        )

    def resolve_profile_model(self, *, profile, scope="local", model_type=None):
        return SimpleNamespace(
            model_name=None,
            provider=None,
            metadata={},
            source=f"system_settings.profile_model_bindings.{scope}.{profile}",
        )


@pytest.fixture(autouse=True)
def _registry_policy(monkeypatch):
    monkeypatch.setattr(
        "backend.app.services.model_routing_policy_service.ModelRoutingPolicyService",
        _FakeRoutingPolicy,
    )


@pytest.mark.asyncio
async def test_workspace_routed_chat_codex_uses_core_pool_route(monkeypatch):
    calls = []

    async def fake_load_workspace(workspace_id):
        return SimpleNamespace(id=workspace_id, resolved_executor_runtime="codex_cli")

    class FakeWorkspaceAgentExecutor:
        def __init__(self, workspace):
            self.workspace = workspace

        async def check_agent_available(self, agent_id):
            calls.append(("available", self.workspace.id, agent_id))
            return True

        async def execute(self, **kwargs):
            raise AssertionError("codex_cli chat route must not use bridge executor")

    async def fake_core_llm_call(**kwargs):
        calls.append(("core_llm_call", kwargs))
        return "runtime-output"

    monkeypatch.setattr(workspace_routed_chat, "_load_workspace", fake_load_workspace)
    monkeypatch.setattr(
        "backend.app.services.llm.core_llm.core_llm_call",
        fake_core_llm_call,
    )
    monkeypatch.setattr(
        "backend.app.services.workspace_agent_executor.WorkspaceAgentExecutor",
        FakeWorkspaceAgentExecutor,
    )

    response = await chat_completion_with_workspace_route(
        messages=[{"role": "user", "content": "Return a plan"}],
        workspace_id="ws-test",
        provider=_FailingProvider(),
        route_context={"executor_runtime": "codex_cli"},
        purpose="playbook_tool_loop.post_tool_results",
    )

    assert response == "runtime-output"
    assert calls[0][0] == "core_llm_call"
    assert calls[0][1]["executor_runtime"] == "codex_cli"
    assert calls[0][1]["purpose"] == "workspace_routed_chat"


@pytest.mark.asyncio
async def test_workspace_routed_chat_non_codex_uses_executor_bridge(monkeypatch):
    calls = []

    async def fake_load_workspace(workspace_id):
        return SimpleNamespace(id=workspace_id, resolved_executor_runtime="gemini_cli")

    class FakeWorkspaceAgentExecutor:
        def __init__(self, workspace):
            self.workspace = workspace

        async def check_agent_available(self, agent_id):
            calls.append(("available", self.workspace.id, agent_id))
            return True

        async def execute(self, **kwargs):
            calls.append(("execute", kwargs))
            return SimpleNamespace(success=True, output="runtime-output", error=None)

    monkeypatch.setattr(workspace_routed_chat, "_load_workspace", fake_load_workspace)
    monkeypatch.setattr(
        "backend.app.services.workspace_agent_executor.WorkspaceAgentExecutor",
        FakeWorkspaceAgentExecutor,
    )

    response = await chat_completion_with_workspace_route(
        messages=[{"role": "user", "content": "Return a plan"}],
        workspace_id="ws-test",
        provider=_FailingProvider(),
        route_context={"executor_runtime": "gemini_cli"},
        purpose="playbook_tool_loop.post_tool_results",
    )

    assert response == "runtime-output"
    assert calls[0] == ("available", "ws-test", "gemini_cli")
    assert calls[1][0] == "execute"
    assert calls[1][1]["agent_id"] == "gemini_cli"


@pytest.mark.asyncio
async def test_workspace_routed_chat_builds_registry_provider_without_runtime(monkeypatch):
    caller_provider = _Provider()
    registry_provider = _Provider()

    def fake_build_managed_llm_provider(**kwargs):
        return registry_provider, SimpleNamespace(**kwargs)

    monkeypatch.setattr(
        "backend.app.shared.llm_provider_helper.build_managed_llm_provider",
        fake_build_managed_llm_provider,
    )

    response = await chat_completion_with_workspace_route(
        messages=[{"role": "user", "content": "Return a plan"}],
        workspace_id="ws-test",
        provider=caller_provider,
        route_context={},
        purpose="playbook_tool_loop.post_tool_results",
    )

    assert response == "provider-output"
    assert len(caller_provider.calls) == 0
    assert len(registry_provider.calls) == 1


@pytest.mark.asyncio
async def test_workspace_routed_chat_fails_closed_without_workspace(monkeypatch):
    async def fake_load_workspace(workspace_id):
        return None

    monkeypatch.setattr(workspace_routed_chat, "_load_workspace", fake_load_workspace)

    with pytest.raises(RuntimeError, match="workspace context is unavailable"):
        await chat_completion_with_workspace_route(
            messages=[{"role": "user", "content": "Return a plan"}],
            workspace_id="ws-test",
            provider=_FailingProvider(),
            route_context={"executor_runtime": "codex_cli"},
            purpose="playbook_tool_loop.post_tool_results",
        )
