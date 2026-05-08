import pytest
from pathlib import Path
from types import SimpleNamespace

from backend.app.services.llm.governed_stage_router import resolve_governed_stage_route
from backend.app.services.llm.core_llm import core_llm_call
import backend.app.services.llm.core_llm as core_llm_module


REPO_ROOT = Path(__file__).resolve().parents[2]


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
async def test_json_response_keeps_workspace_runtime_route():
    decision = await resolve_governed_stage_route(
        workspace_id="ws-test",
        route_context={"executor_runtime": "codex_cli"},
        stage_name="generic_generation",
        purpose="core_llm_call",
        response_format="json",
        requested_model="gpt-5.4",
    )

    assert decision.route_mode == "workspace_runtime"
    assert decision.executor_runtime == "codex_cli"
    assert decision.provider_name == "openai"
    assert decision.decision_reason == "workspace_runtime_stage"


@pytest.mark.asyncio
async def test_managed_stage_keeps_workspace_runtime_route():
    decision = await resolve_governed_stage_route(
        workspace_id="ws-test",
        route_context={"executor_runtime": "gemini_cli"},
        stage_name="tool_call_generation",
        purpose="tool_loop",
        response_format="text",
        requested_model="gpt-5.4",
    )

    assert decision.route_mode == "workspace_runtime"
    assert decision.executor_runtime == "gemini_cli"
    assert decision.provider_name == "openai"
    assert decision.decision_reason == "workspace_runtime_stage"


@pytest.mark.asyncio
async def test_no_workspace_runtime_uses_managed_provider():
    decision = await resolve_governed_stage_route(
        workspace_id="ws-test",
        route_context={},
        stage_name="generic_generation",
        purpose="core_llm_call",
        response_format="json",
        requested_model="gpt-5.4",
    )

    assert decision.route_mode == "managed_provider"
    assert decision.executor_runtime is None
    assert decision.provider_name == "openai"
    assert decision.decision_reason == "no_workspace_runtime"


@pytest.mark.asyncio
async def test_core_llm_fails_closed_when_runtime_route_has_no_workspace():
    with pytest.raises(RuntimeError, match="workspace context is unavailable"):
        await core_llm_call(
            user_message="Return JSON",
            response_format="json",
            executor_runtime="codex_cli",
            model="gpt-5.4",
        )


@pytest.mark.asyncio
async def test_core_llm_codex_runtime_uses_pool_path_without_env_flag(monkeypatch):
    calls = []

    async def fake_direct_codex_runtime(**kwargs):
        calls.append(kwargs)
        return {"ok": True}

    class FailingWorkspaceAgentExecutor:
        def __init__(self, workspace):
            self.workspace = workspace

        async def execute(self, **kwargs):
            raise AssertionError("codex_cli core_llm_call must not use the bridge path")

    monkeypatch.delenv("MINDSCAPE_CODEX_DIRECT", raising=False)
    monkeypatch.delenv("MINDSCAPE_MEETING_CODEX_DIRECT", raising=False)
    monkeypatch.delenv("MINDSCAPE_CODEX_CLI_DIRECT_SUBPROCESS", raising=False)
    monkeypatch.delenv("MINDSCAPE_BACKEND_ROLE", raising=False)
    monkeypatch.setattr(
        core_llm_module,
        "_call_via_direct_codex_runtime",
        fake_direct_codex_runtime,
    )
    monkeypatch.setattr(
        "backend.app.services.workspace_agent_executor.WorkspaceAgentExecutor",
        FailingWorkspaceAgentExecutor,
    )

    result = await core_llm_module._call_via_runtime(
        workspace=SimpleNamespace(id="ws-test"),
        executor_runtime="codex_cli",
        system_prompt="Return compact JSON",
        user_message="probe",
        response_format="json",
        model="gpt-5.4",
    )

    assert result == {"ok": True}
    assert calls and calls[0]["response_format"] == "json"


@pytest.mark.asyncio
async def test_core_llm_codex_runtime_uses_host_bridge_inside_backend_container(monkeypatch):
    calls = []

    async def fake_direct_codex_runtime(**kwargs):
        raise AssertionError("containerized backend must not spawn Codex directly")

    class BridgeWorkspaceAgentExecutor:
        def __init__(self, workspace):
            self.workspace = workspace

        async def execute(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(success=True, output='{"ok": true}', error="")

    monkeypatch.setenv("MINDSCAPE_BACKEND_ROLE", "execution")
    monkeypatch.setattr(
        core_llm_module,
        "_call_via_direct_codex_runtime",
        fake_direct_codex_runtime,
    )
    monkeypatch.setattr(
        "backend.app.services.workspace_agent_executor.WorkspaceAgentExecutor",
        BridgeWorkspaceAgentExecutor,
    )

    result = await core_llm_module._call_via_runtime(
        workspace=SimpleNamespace(id="ws-test"),
        executor_runtime="codex_cli",
        system_prompt="Return compact JSON",
        user_message="probe",
        response_format="json",
        model="gpt-5.4",
    )

    assert result == {"ok": True}
    assert calls and calls[0]["agent_id"] == "codex_cli"


def test_route_bypass_strings_are_not_reintroduced():
    forbidden = [
        "agentic_runtime_structured_stage",
        "agentic_runtime_managed_stage",
        "_MANAGED_ONLY_STAGES",
        "allow_with_executor_runtime=True",
        "allow_with_executor_runtime = True",
        "trying direct provider",
        "current executor runtimes are agentic CLI surfaces",
        "remaining managed path",
        "allow_fallback",
        "fallback_model",
        "workspace.fallback_model",
        "determine_provider_from_model",
        "FALLBACK_CHAIN",
        "select_best_model",
        "def get_available_providers",
        "model=\"gpt-4o-mini\"",
        "model = \"gpt-4o-mini\"",
        "openai.AsyncOpenAI",
        "OLLAMA_CHAT_MODEL",
        "OLLAMA_HOST",
        "using direct client",
    ]
    paths = [
        REPO_ROOT / "backend/app/services/llm/governed_stage_router.py",
        REPO_ROOT / "backend/app/services/llm/core_llm.py",
        REPO_ROOT / "backend/app/services/llm/workspace_routed_chat.py",
        REPO_ROOT / "backend/app/shared/llm_provider_helper.py",
        REPO_ROOT / "backend/app/services/multi_ai_collaboration.py",
        REPO_ROOT / "backend/app/routes/core/cli_token.py",
        REPO_ROOT / "backend/app/services/codex_pool_service.py",
        REPO_ROOT / "backend/app/services/gca_pool_service.py",
        REPO_ROOT / "backend/app/services/executor_binding_service.py",
        REPO_ROOT / "backend/app/routes/core/system_settings/assistant.py",
        REPO_ROOT / "backend/app/services/personal_governance/digest_extraction.py",
        REPO_ROOT / "backend/app/services/workspace_seed_service.py",
        REPO_ROOT / "backend/app/services/llm_providers/vertex.py",
        REPO_ROOT / "backend/app/capabilities/semantic_seeds/services/suggestion_generator.py",
        REPO_ROOT / "backend/features/workspace/chat/streaming/llm_streaming.py",
        REPO_ROOT / "backend/features/workspace/chat/streaming/execution_plan.py",
        REPO_ROOT / "backend/features/workspace/chat/utils/llm_provider.py",
    ]

    for path in paths:
        text = path.read_text()
        for token in forbidden:
            assert token not in text, f"{token} reintroduced in {path}"


def test_workspace_chat_provider_resolution_uses_registry_policy():
    from backend.features.workspace.chat.utils.llm_provider import (
        resolve_registered_provider_for_model,
    )

    assert resolve_registered_provider_for_model("qwen2.5:7b") == "openai"
