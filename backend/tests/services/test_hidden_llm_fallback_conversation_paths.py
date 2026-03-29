from types import SimpleNamespace

import pytest

import backend.app.services.intent_llm_extractor as intent_llm_extractor_module
import backend.app.services.conversation.message_generator as message_generator_module
from backend.app.capabilities.semantic_seeds.services.seed_extractor import (
    SeedExtractor,
)
from backend.app.services.conversation.intent_steward import IntentStewardService
from backend.app.services.conversation.message_generator import MessageGenerator
from backend.app.services.conversation.plan_builder import PlanBuilder
from backend.app.services.conversation.special_pack_executors import (
    SpecialPackExecutors,
)
from backend.app.services.intent_llm_extractor import IntentLLMExtractor
from backend.app.services.workspace_seed_service import WorkspaceSeedService


@pytest.mark.asyncio
async def test_intent_llm_extractor_skips_without_explicit_backend(monkeypatch):
    async def _boom(*args, **kwargs):
        raise AssertionError("LLM should not be called without explicit backend")

    monkeypatch.setattr(intent_llm_extractor_module, "llm_generate", _boom)

    extractor = IntentLLMExtractor(default_locale="en")
    result = await extractor.extract(message="plan my week", context="context")

    assert result == {"intents": [], "themes": []}


@pytest.mark.asyncio
async def test_message_generator_uses_template_fallback_without_explicit_backend(
    monkeypatch,
):
    async def _boom(*args, **kwargs):
        raise AssertionError("LLM should not be called without explicit backend")

    monkeypatch.setattr(message_generator_module, "llm_generate", _boom)

    generator = MessageGenerator(default_locale="en")
    result = await generator.generate_confirmation_message(
        action_type="publish_to_wordpress",
        action_params={"title": "Hello"},
        timeline_item={"title": "Draft", "summary": "Summary"},
        locale="en",
    )

    assert "message" in result
    assert len(result["confirm_buttons"]) == 2
    assert result["confirm_buttons"][0]["confirm"] is True


@pytest.mark.asyncio
async def test_special_pack_executors_skip_seed_extraction_without_explicit_backend():
    executors = SpecialPackExecutors(
        tasks_store=SimpleNamespace(),
        timeline_items_store=SimpleNamespace(),
        store=SimpleNamespace(),
        config_store=SimpleNamespace(),
    )

    result = await executors._extract_intents_from_message(
        profile_id="profile-1",
        message_id="message-1",
        message="Need a content calendar",
    )

    assert result == []


@pytest.mark.asyncio
async def test_workspace_seed_service_uses_fallback_digest_without_explicit_backend():
    service = WorkspaceSeedService(store=SimpleNamespace())
    service.workspaces_store = SimpleNamespace(
        get_workspace=lambda workspace_id: None,
    )

    async def _get_workspace(_workspace_id):
        return SimpleNamespace(owner_user_id="profile-1")

    service.workspaces_store = SimpleNamespace(get_workspace=_get_workspace)

    digest = await service._generate_digest(
        text_content="seed text",
        locale="en",
        workspace_id="workspace-1",
        seed_type="text",
    )

    assert digest["starter_kit_type"] == "custom"
    assert "Workspace created from text seed" in digest["brief"]


@pytest.mark.asyncio
async def test_intent_steward_skips_llm_analysis_without_explicit_backend():
    steward = IntentStewardService(store=SimpleNamespace())

    result = await steward._llm_analyze_signals(
        filtered_signals=[],
        context=SimpleNamespace(current_intent_cards=[]),
    )

    assert result is None


@pytest.mark.asyncio
async def test_plan_builder_uses_rule_based_path_without_explicit_backend(
    monkeypatch,
):
    monkeypatch.setattr(
        "backend.app.services.config_store.ConfigStore",
        lambda: SimpleNamespace(),
    )

    builder = PlanBuilder(store=SimpleNamespace())

    result = await builder._generate_llm_plan(
        message="summarize this workspace",
        files=[],
        workspace_id="workspace-1",
        profile_id="profile-1",
        available_packs=["daily_planning"],
    )

    assert result == []


@pytest.mark.asyncio
async def test_seed_extractor_skips_without_explicit_model_name():
    extractor = SeedExtractor(llm_provider=object(), model_name=None)

    result = await extractor.extract_seeds_from_content(
        user_id="profile-1",
        content="Need help planning",
        source_type="conversation",
        source_id="message-1",
    )

    assert result == []
