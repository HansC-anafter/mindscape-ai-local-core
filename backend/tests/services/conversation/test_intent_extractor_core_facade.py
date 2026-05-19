import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.app.models.mindscape import IntentSource, IntentTagStatus
from backend.app.services.conversation import intent_extractor
from backend.app.services.conversation.intent_extractor import IntentExtractor
from backend.app.services.conversation.intent_extractor_core.auto_execution import (
    build_auto_execution_timeline_item,
)
from backend.app.services.conversation.intent_extractor_core.intent_tags import (
    create_candidate_intent_tags,
)
from backend.app.services.conversation.intent_extractor_core.metadata import (
    update_event_metadata,
)


class FakeI18n:
    def t(self, _namespace, _key, **kwargs):
        return kwargs["default"]


def test_intent_extractor_preserves_public_method_surface():
    required = [
        "extract_and_create_timeline_item",
        "update_event_metadata",
        "confirm_intent",
        "reject_intent",
        "extract_intents",
        "extract_intents_with_ctx",
    ]

    assert [name for name in required if not hasattr(IntentExtractor, name)] == []


@pytest.mark.asyncio
async def test_extract_and_create_timeline_item_delegates_to_runtime(monkeypatch):
    called = {}

    async def fake_extract_and_create_timeline_item(**kwargs):
        called.update(kwargs)
        return "timeline-item"

    monkeypatch.setattr(
        intent_extractor,
        "extract_and_create_timeline_item",
        fake_extract_and_create_timeline_item,
    )
    extractor = IntentExtractor.__new__(IntentExtractor)
    ctx = SimpleNamespace(workspace_id="workspace-1", actor_id="profile-1")

    result = await IntentExtractor.extract_and_create_timeline_item(
        extractor,
        ctx=ctx,
        message="Capture this direction",
        message_id="message-1",
        locale="en",
        thread_id="thread-1",
    )

    assert result == "timeline-item"
    assert called["extractor"] is extractor
    assert called["ctx"] is ctx
    assert called["message_id"] == "message-1"
    assert called["thread_id"] == "thread-1"


def test_create_candidate_intent_tags_handles_dict_and_string_intents():
    class FakeIntentTagsStore:
        def __init__(self):
            self.created = []

        def create_intent_tag(self, tag):
            self.created.append(tag)

    store = FakeIntentTagsStore()
    ctx = SimpleNamespace(workspace_id="workspace-1", actor_id="profile-1")

    ids = create_candidate_intent_tags(
        intent_tags_store=store,
        ctx=ctx,
        message_id="message-1",
        intents=[
            {"title": "Draft launch copy", "confidence": 0.72},
            "Build image direction",
        ],
        confidence=0.61,
        llm_analysis={"model": "test"},
    )

    assert ids == [tag.id for tag in store.created]
    assert [tag.label for tag in store.created] == [
        "Draft launch copy",
        "Build image direction",
    ]
    assert store.created[0].confidence == 0.72
    assert store.created[1].confidence == 0.61
    assert all(tag.status == IntentTagStatus.CANDIDATE for tag in store.created)
    assert all(tag.source == IntentSource.LLM for tag in store.created)


def test_auto_execution_timeline_item_uses_intents_created_count():
    ctx = SimpleNamespace(workspace_id="workspace-1")

    item = build_auto_execution_timeline_item(
        ctx=ctx,
        message_id="message-1",
        action_task_id="task-1",
        i18n=FakeI18n(),
        intents_list=[{"title": "Draft"}],
        themes_list=["launch"],
        intents_created=2,
        thread_id="thread-1",
    )

    assert item.task_id == "task-1"
    assert item.title == "Added 2 intent(s) to Mindscape"
    assert item.summary == "Auto-added 2 intent(s) from message"
    assert item.data["intents_added"] == 2
    assert item.data["thread_id"] == "thread-1"


@pytest.mark.asyncio
async def test_update_event_metadata_updates_existing_event():
    event = SimpleNamespace(metadata=None)

    class FakeStore:
        def __init__(self):
            self.updated = None

        def get_event(self, event_id):
            return event if event_id == "event-1" else None

        def update_event(self, event_id, metadata):
            self.updated = (event_id, metadata)

    store = FakeStore()

    result = await update_event_metadata(
        store=store,
        event_id="event-1",
        intents=[{"title": "Draft"}],
        themes=["launch"],
    )

    assert result is True
    assert event.metadata["llm_extracted_intents"] == [{"title": "Draft"}]
    assert event.metadata["llm_extracted_themes"] == ["launch"]
    assert store.updated == ("event-1", event.metadata)


@pytest.mark.asyncio
async def test_update_event_metadata_returns_false_for_missing_event():
    class FakeStore:
        def get_event(self, _event_id):
            return None

    result = await update_event_metadata(
        store=FakeStore(),
        event_id="missing",
        intents=[],
        themes=[],
    )

    assert result is False
