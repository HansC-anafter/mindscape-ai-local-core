from types import SimpleNamespace

import pytest

from backend.app.services.intent.llm_matcher import LLMBasedIntentMatcher
from backend.app.services.intent.models import InteractionType, TaskDomain
from backend.app.services.intent.playbook_selector import PlaybookSelector
from backend.app.services.project.project_assignment_agent import ProjectAssignmentAgent
from backend.app.services.project.project_detector import ProjectDetector
from backend.app.shared.llm_provider_helper import get_model_name_from_chat_model


@pytest.mark.asyncio
async def test_llm_matcher_requires_explicit_model():
    class _Provider:
        async def chat_completion(self, *args, **kwargs):
            raise AssertionError("chat_completion should not run without explicit model")

    matcher = LLMBasedIntentMatcher(llm_provider=_Provider(), model_name=None)
    interaction_type, confidence = await matcher.determine_interaction_type("hello")

    assert interaction_type == InteractionType.UNKNOWN
    assert confidence == 0.0


@pytest.mark.asyncio
async def test_playbook_selector_requires_explicit_model():
    class _Provider:
        async def chat_completion(self, *args, **kwargs):
            raise AssertionError("chat_completion should not run without explicit model")

    class _PlaybookService:
        async def list_playbooks(self, **kwargs):
            return [
                SimpleNamespace(
                    playbook_code="pb.demo",
                    name="Demo",
                    description="desc",
                    tags=[],
                )
            ]

    selector = PlaybookSelector(
        playbook_service=_PlaybookService(),
        llm_provider=_Provider(),
        model_name=None,
    )

    selected, confidence, plan = await selector.select_playbook(
        task_domain=TaskDomain.UNKNOWN,
        user_input="do something",
    )

    assert selected is None
    assert confidence == 0.0
    assert plan is None


@pytest.mark.asyncio
async def test_project_assignment_agent_skips_without_explicit_backend():
    agent = ProjectAssignmentAgent()
    workspace = SimpleNamespace(
        resolved_executor_runtime=None,
        executor_runtime=None,
        mode="general",
        title="WS",
    )

    provider, model_name = agent._resolve_generation_backend(workspace)

    assert provider is None
    assert model_name is None

    result = await agent.assign_project_for_message(
        message="continue this project",
        workspace_id="ws-1",
        project_candidates=[{"id": "p1"}],
        last_project_id="p1",
    )

    assert result["relation"] == "ambiguous"
    assert result["project_id"] == "p1"
    assert result["confidence"] == 0.0


@pytest.mark.asyncio
async def test_project_detector_skips_without_explicit_backend():
    detector = ProjectDetector()
    workspace = SimpleNamespace(
        resolved_executor_runtime=None,
        executor_runtime=None,
        mode="general",
        default_locale="zh-TW",
        id="ws-1",
    )

    provider, model_name = detector._resolve_generation_backend(workspace)
    assert provider is None
    assert model_name is None

    result = await detector.detect(
        message="幫我規劃一個新專案",
        conversation_context=[],
        workspace=workspace,
        available_playbooks=[],
    )

    assert result is None


def test_get_model_name_from_chat_model_does_not_use_default(monkeypatch):
    class _Store:
        def get_setting(self, key):
            assert key == "chat_model"
            return None

    monkeypatch.setattr(
        "backend.app.services.system_settings_store.SystemSettingsStore",
        lambda: _Store(),
    )

    assert get_model_name_from_chat_model(default="gpt-4o-mini") is None
