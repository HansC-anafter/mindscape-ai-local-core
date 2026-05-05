import pytest
from pathlib import Path

from backend.app.services.llm.governed_stage_router import resolve_governed_stage_route
from backend.app.services.llm.core_llm import core_llm_call


REPO_ROOT = Path(__file__).resolve().parents[2]


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
    ]
    paths = [
        REPO_ROOT / "backend/app/services/llm/governed_stage_router.py",
        REPO_ROOT / "backend/app/services/llm/core_llm.py",
        REPO_ROOT / "backend/app/services/llm/workspace_routed_chat.py",
        REPO_ROOT / "backend/app/shared/llm_provider_helper.py",
        REPO_ROOT / "backend/app/services/multi_ai_collaboration.py",
    ]

    for path in paths:
        text = path.read_text()
        for token in forbidden:
            assert token not in text, f"{token} reintroduced in {path}"
