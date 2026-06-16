import pytest

from backend.app.services import agent_runner
from backend.app.services.agent_runner_prompt_builder import AgentPromptBuilder
from backend.app.services.llm_providers import LLMProvider, LLMProviderManager


def test_agent_runner_public_exports_remain_on_facade():
    assert agent_runner.AgentPromptBuilder is AgentPromptBuilder
    assert agent_runner.LLMProvider is LLMProvider
    assert agent_runner.LLMProviderManager is LLMProviderManager
    assert callable(agent_runner.call_llm)
    assert callable(agent_runner.build_prompt)


@pytest.mark.asyncio
async def test_run_agent_delegates_to_single_execution_seam(monkeypatch):
    observed = {}

    async def fake_run_agent(runner, profile_id, request):
        observed["runner"] = runner
        observed["profile_id"] = profile_id
        observed["request"] = request
        return "result"

    monkeypatch.setattr(agent_runner, "_run_agent", fake_run_agent)

    runner = agent_runner.AgentRunner.__new__(agent_runner.AgentRunner)
    request = object()
    result = await runner.run_agent("profile-1", request)

    assert result == "result"
    assert observed == {
        "runner": runner,
        "profile_id": "profile-1",
        "request": request,
    }


@pytest.mark.asyncio
async def test_suggest_work_scene_delegates_with_facade_llm_hooks(monkeypatch):
    observed = {}

    async def fake_suggest_work_scene(**kwargs):
        observed.update(kwargs)
        return {"suggested_scene_id": "daily_planning"}

    async def fake_call_llm(**kwargs):
        return {"text": "{}"}

    def fake_build_prompt(**kwargs):
        return [{"role": "user", "content": "prompt"}]

    monkeypatch.setattr(agent_runner, "_suggest_work_scene", fake_suggest_work_scene)
    monkeypatch.setattr(agent_runner, "call_llm", fake_call_llm)
    monkeypatch.setattr(agent_runner, "build_prompt", fake_build_prompt)

    runner = agent_runner.AgentRunner.__new__(agent_runner.AgentRunner)
    runner._llm_manager = object()
    result = await runner.suggest_work_scene("profile-1", "plan the day")

    assert result == {"suggested_scene_id": "daily_planning"}
    assert observed["profile_id"] == "profile-1"
    assert observed["task"] == "plan the day"
    assert observed["llm_provider"] is runner._llm_manager
    assert observed["call_llm_func"] is fake_call_llm
    assert observed["build_prompt_func"] is fake_build_prompt
