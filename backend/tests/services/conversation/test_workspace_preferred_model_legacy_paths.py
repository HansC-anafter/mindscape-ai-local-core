import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock


def test_intent_extractor_build_context_builder_prefers_workspace_model(monkeypatch):
    from backend.app.services.conversation import intent_extractor as module

    captured = {}

    class FakeIntentTagsStore:
        def create_intent_tag(self, tag):
            return tag

    class FakeContextBuilder:
        def __init__(self, store=None, timeline_items_store=None, model_name=None):
            captured["model_name"] = model_name

    class FakeStore:
        db_path = "postgres://test"

        async def get_workspace(self, workspace_id):
            return SimpleNamespace(
                id=workspace_id,
                metadata={
                    "preferred_chat_model": {
                        "model_name": "qwen3:8b",
                        "provider": "ollama",
                    }
                },
            )

    monkeypatch.setattr(module, "IntentTagsStore", FakeIntentTagsStore)
    monkeypatch.setattr(module, "ContextBuilder", FakeContextBuilder)

    extractor = module.IntentExtractor(
        store=FakeStore(),
        timeline_items_store=MagicMock(),
        intent_registry=MagicMock(),
    )

    context_builder, workspace = asyncio.run(extractor._build_context_builder("ws-1"))

    assert isinstance(context_builder, FakeContextBuilder)
    assert workspace.id == "ws-1"
    assert captured["model_name"] == "qwen3:8b"


def test_qa_response_generator_runtime_prefers_workspace_model(monkeypatch):
    from backend.app.services.conversation import qa_response_generator as module
    from backend.features.workspace.chat.utils import llm_provider as provider_module

    class FakeStore:
        db_path = "postgres://test"

        async def get_workspace(self, workspace_id):
            return SimpleNamespace(
                id=workspace_id,
                metadata={
                    "preferred_chat_model": {
                        "model_name": "qwen3:8b",
                        "provider": "ollama",
                    }
                },
            )

    fake_provider = object()
    monkeypatch.setattr(
        provider_module,
        "get_llm_provider_manager",
        lambda profile_id=None, db_path=None: "manager",
    )
    monkeypatch.setattr(
        provider_module,
        "get_llm_provider",
        lambda model_name, llm_provider_manager=None, profile_id=None, db_path=None: (
            fake_provider,
            "FakeProvider",
        ),
    )

    generator = module.QAResponseGenerator(
        store=FakeStore(),
        timeline_items_store=MagicMock(),
    )

    workspace, model_name, llm_provider = asyncio.run(
        generator._resolve_generation_runtime(
            workspace_id="ws-2",
            profile_id="profile-1",
        )
    )

    assert workspace.id == "ws-2"
    assert model_name == "qwen3:8b"
    assert llm_provider is fake_provider


def test_workspace_welcome_selection_prefers_workspace_model(monkeypatch):
    from backend.app.services import workspace_welcome_service as module
    from backend.features.workspace.chat.utils import llm_provider as provider_module

    workspace = SimpleNamespace(
        id="ws-3",
        metadata={
            "preferred_chat_model": {
                "model_name": "qwen3:8b",
                "provider": "ollama",
            }
        },
    )

    fake_provider = object()
    monkeypatch.setattr(
        provider_module,
        "get_llm_provider_manager",
        lambda profile_id=None, db_path=None: "manager",
    )
    monkeypatch.setattr(
        provider_module,
        "get_llm_provider",
        lambda model_name, llm_provider_manager=None, profile_id=None, db_path=None: (
            fake_provider,
            "FakeProvider",
        ),
    )

    model_name, llm_provider = asyncio.run(
        module._resolve_workspace_llm_selection(
            workspace=workspace,
            store=SimpleNamespace(db_path="postgres://test"),
            profile_id="profile-2",
        )
    )

    assert model_name == "qwen3:8b"
    assert llm_provider is fake_provider


def test_chat_orchestrator_legacy_llm_path_prefers_workspace_model(monkeypatch):
    from backend.app.services.chat_orchestrator_service import ChatOrchestratorService

    orchestrator = SimpleNamespace(store=SimpleNamespace(db_path="postgres://test"))
    service = ChatOrchestratorService(orchestrator=orchestrator)

    workspace = SimpleNamespace(
        metadata={
            "preferred_chat_model": {
                "model_name": "qwen3:8b",
                "provider": "ollama",
            }
        }
    )
    request = SimpleNamespace(model_name=None)

    resolved = service._resolve_llm_path_model_name(request, workspace)

    assert resolved == "qwen3:8b"
