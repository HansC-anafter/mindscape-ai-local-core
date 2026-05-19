from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from backend.app.models.workspace import TaskStatus
from backend.app.services.conversation import suggestion_card_creator as facade_module
from backend.app.services.conversation.suggestion_card_creator import (
    SuggestionCardCreator,
)
from backend.app.services.conversation.suggestion_card_creator_core import (
    duplicates,
    preferences,
    runtime,
    validation,
)


class FakeTaskStore:
    def __init__(self, existing_tasks=None):
        self.created = []
        self.existing_tasks = existing_tasks or []
        self.find_calls = []

    def find_existing_suggestion_tasks(self, **kwargs):
        self.find_calls.append(kwargs)
        return self.existing_tasks

    def create_task(self, task):
        self.created.append(task)
        return task


class FakeEmitter:
    def __init__(self):
        self.events = []

    def emit_task_created(self, **kwargs):
        self.events.append(kwargs)


def test_suggestion_card_creator_method_surface():
    for name in ["create_suggestion_card", "create_playbook_suggestion"]:
        assert hasattr(SuggestionCardCreator, name)


@pytest.mark.asyncio
async def test_suggestion_card_creator_facade_delegates(monkeypatch):
    creator = SuggestionCardCreator.__new__(SuggestionCardCreator)
    observed = {}

    async def fake_create_suggestion_card(**kwargs):
        observed["suggestion"] = kwargs
        return {"task_id": "task_1"}

    async def fake_create_playbook_suggestion(**kwargs):
        observed["playbook"] = kwargs
        return {"task_id": "task_2"}

    monkeypatch.setattr(
        facade_module,
        "create_suggestion_card_helper",
        fake_create_suggestion_card,
    )
    monkeypatch.setattr(
        facade_module,
        "create_playbook_suggestion_helper",
        fake_create_playbook_suggestion,
    )

    suggestion = await creator.create_suggestion_card(
        task_plan=SimpleNamespace(pack_id="pack.alpha"),
        workspace_id="ws_1",
        message_id="msg_1",
        event_emitter=Mock(),
    )
    playbook = await creator.create_playbook_suggestion(
        playbook_code="pack.beta",
        playbook_context={},
        workspace_id="ws_1",
        message_id="msg_2",
        event_emitter=Mock(),
    )

    assert suggestion == {"task_id": "task_1"}
    assert playbook == {"task_id": "task_2"}
    assert observed["suggestion"]["creator"] is creator
    assert observed["playbook"]["creator"] is creator


@pytest.mark.asyncio
async def test_validate_playbook_uses_single_validation_order():
    empty = await validation.validate_playbook(
        pack_id="",
        workspace_id="ws_1",
        registry_factory=lambda: Mock(),
    )
    assert empty == {"is_valid": False, "reason": "empty_pack_id"}

    playbook_service = SimpleNamespace(get_playbook=AsyncMock(return_value={"code": "p"}))
    playbook = await validation.validate_playbook(
        pack_id="pack.playbook",
        workspace_id="ws_1",
        playbook_service=playbook_service,
        registry_factory=lambda: Mock(),
    )
    assert playbook == {"is_valid": True, "reason": None}
    playbook_service.get_playbook.assert_awaited_once()

    registry = SimpleNamespace(get_execution_method=Mock(return_value="pack_executor"))
    capability = await validation.validate_playbook(
        pack_id="pack.capability",
        workspace_id="ws_1",
        registry_factory=lambda: registry,
    )
    assert capability == {"is_valid": True, "reason": None}
    registry.get_execution_method.assert_called_once_with("pack.capability")

    special = await validation.validate_playbook(
        pack_id="semantic_seeds",
        workspace_id="ws_1",
        registry_factory=lambda: SimpleNamespace(
            get_execution_method=Mock(return_value=None)
        ),
    )
    assert special == {"is_valid": True, "reason": None}


@pytest.mark.asyncio
async def test_check_user_preference_honors_disabled_preference():
    class FakeWorkspaceStore:
        async def get_workspace(self, workspace_id):
            return SimpleNamespace(owner_user_id="user_1")

    class FakePreferenceStore:
        def __init__(self):
            self.calls = []

        def should_auto_suggest(self, **kwargs):
            self.calls.append(kwargs)
            return False

    preference_store = FakePreferenceStore()
    result = await preferences.check_user_preference(
        task_plan=SimpleNamespace(pack_id="pack.alpha", task_type="task.alpha"),
        workspace_id="ws_1",
        workspace_store_factory=FakeWorkspaceStore,
        preference_store_factory=lambda: preference_store,
    )

    assert result == {"should_auto_suggest": False}
    assert preference_store.calls == [
        {
            "workspace_id": "ws_1",
            "user_id": "user_1",
            "pack_id": "pack.alpha",
            "task_type": "task.alpha",
        }
    ]


def test_duplicate_detection_matches_source_and_files():
    existing = SimpleNamespace(
        id="task_existing",
        params={"source": "source_a", "files": ["a.md", "b.md"]},
    )
    task_plan = SimpleNamespace(
        pack_id="pack.alpha",
        params={"source": "source_a", "files": ["b.md", "a.md"]},
    )

    assert duplicates.should_create_new_suggestion_task([existing], task_plan) is False


@pytest.mark.asyncio
async def test_runtime_create_suggestion_card_skips_invalid_pack(monkeypatch):
    async def fake_validate_playbook(**kwargs):
        return {"is_valid": False, "reason": "invalid_playbook_code"}

    monkeypatch.setattr(runtime, "validate_playbook", fake_validate_playbook)
    creator = SimpleNamespace(
        tasks_store=FakeTaskStore(),
        playbook_service=None,
        default_locale="en",
    )

    result = await runtime.create_suggestion_card(
        creator=creator,
        task_plan=SimpleNamespace(pack_id="pack.invalid", task_type="task", params={}),
        workspace_id="ws_1",
        message_id="msg_1",
        event_emitter=FakeEmitter(),
    )

    assert result == {
        "task_id": None,
        "timeline_item_id": None,
        "pack_id": "pack.invalid",
        "skipped": True,
        "reason": "invalid_playbook_code",
    }
    assert creator.tasks_store.created == []


@pytest.mark.asyncio
async def test_runtime_create_suggestion_card_reuses_duplicate(monkeypatch):
    async def fake_validate_playbook(**kwargs):
        return {"is_valid": True, "reason": None}

    async def fake_check_user_preference(**kwargs):
        return {"should_auto_suggest": True}

    monkeypatch.setattr(runtime, "validate_playbook", fake_validate_playbook)
    monkeypatch.setattr(runtime, "check_user_preference", fake_check_user_preference)
    existing = SimpleNamespace(
        id="task_existing",
        params={"source": "source_a", "files": ["input.txt"]},
    )
    creator = SimpleNamespace(
        tasks_store=FakeTaskStore(existing_tasks=[existing]),
        playbook_service=None,
        default_locale="en",
    )

    result = await runtime.create_suggestion_card(
        creator=creator,
        task_plan=SimpleNamespace(
            pack_id="pack.alpha",
            task_type="task.alpha",
            params={"source": "source_a", "files": ["input.txt"]},
        ),
        workspace_id="ws_1",
        message_id="msg_1",
        event_emitter=FakeEmitter(),
    )

    assert result == {
        "task_id": "task_existing",
        "timeline_item_id": None,
        "pack_id": "pack.alpha",
        "is_duplicate": True,
    }
    assert creator.tasks_store.created == []


@pytest.mark.asyncio
async def test_runtime_create_playbook_suggestion_builds_pending_task(monkeypatch):
    monkeypatch.setattr(
        "backend.app.services.i18n_service.get_i18n_service",
        lambda default_locale: SimpleNamespace(t=lambda *args, **kwargs: "Add"),
    )
    tasks_store = FakeTaskStore()
    emitter = FakeEmitter()
    creator = SimpleNamespace(
        tasks_store=tasks_store,
        playbook_service=None,
        default_locale="en",
    )

    result = await runtime.create_playbook_suggestion(
        creator=creator,
        playbook_code="habit_learning",
        playbook_context={"context": {"llm_analysis": {"confidence": 0.7}}},
        workspace_id="ws_1",
        message_id="msg_1",
        event_emitter=emitter,
    )

    assert result["status"] == "suggestion"
    assert result["playbook_code"] == "habit_learning"
    assert result["task_id"] == tasks_store.created[0].id
    assert tasks_store.created[0].status == TaskStatus.PENDING
    assert tasks_store.created[0].result["llm_analysis"]["is_background"] is True
    assert emitter.events == [
        {
            "task_id": tasks_store.created[0].id,
            "pack_id": "habit_learning",
            "status": "pending",
            "task_type": "suggestion",
            "workspace_id": "ws_1",
        }
    ]
