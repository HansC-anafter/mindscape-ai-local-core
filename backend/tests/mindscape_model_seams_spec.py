import sys
from pathlib import Path

from backend.app.models.mindscape import (
    AgentResponse,
    CommunicationStyle,
    Entity,
    EntityTag,
    EntityType,
    EventActor,
    EventType,
    IntentCard,
    IntentLayoutPlan,
    IntentLog,
    IntentSignal,
    IntentSource,
    IntentStatus,
    IntentTag,
    IntentTagStatus,
    MindEvent,
    MindscapeProfile,
    PriorityLevel,
    ResponseLength,
    Tag,
    TagCategory,
    UserPreferences,
)


def test_public_facade_preserves_representative_imports():
    assert IntentStatus.ACTIVE.value == "active"
    assert PriorityLevel.CRITICAL.value == "critical"
    assert CommunicationStyle.CASUAL.value == "casual"
    assert ResponseLength.MEDIUM.value == "medium"
    assert EventType.MEMORY_WRITEBACK.value == "memory_writeback"
    assert EventActor.PERSONA.value == "persona"
    assert EntityType.ARTIFACT.value == "artifact"
    assert TagCategory.RISK.value == "risk"
    assert IntentSource.IDE.value == "ide"
    assert IntentTagStatus.CONFIRMED.value == "confirmed"


def test_app_model_facade_import_path_remains_compatible():
    backend_root = Path(__file__).resolve().parents[1]
    backend_path = str(backend_root)
    if backend_path not in sys.path:
        sys.path.insert(0, backend_path)

    from app.models.mindscape import IntentCard as AppIntentCard
    from app.models.mindscape import MindEvent as AppMindEvent

    assert AppIntentCard.__name__ == IntentCard.__name__
    assert AppMindEvent.model_fields.keys() == MindEvent.model_fields.keys()


def test_model_defaults_and_serialization_are_preserved():
    profile = MindscapeProfile(id="profile-a", name="Profile A")
    assert profile.preferences.preferred_ui_language == "zh-TW"
    assert profile.preferences.communication_style is CommunicationStyle.CASUAL

    intent = IntentCard(
        id="intent-a",
        profile_id="profile-a",
        title="Plan launch",
        description="Prepare launch plan",
    )
    assert intent.status is IntentStatus.ACTIVE
    assert intent.priority is PriorityLevel.MEDIUM
    assert intent.model_dump(mode="json")["created_at"].endswith("Z") is False

    response = AgentResponse(execution_id="run-a", status="completed")
    assert response.metadata == {}


def test_mind_event_payload_cleaning_preserves_sqlite_row_guard():
    class RowLike:
        def keys(self):
            return ["value"]

    event = MindEvent(
        id="event-a",
        actor=EventActor.SYSTEM,
        channel="api",
        profile_id="profile-a",
        event_type=EventType.MESSAGE,
        payload={"keep": "value", "drop": RowLike()},
    )
    assert event.payload == {"keep": "value"}

    row_payload = MindEvent(
        id="event-b",
        actor=EventActor.SYSTEM,
        channel="api",
        profile_id="profile-a",
        event_type=EventType.MESSAGE,
        payload=RowLike(),
    )
    assert row_payload.payload == {}


def test_entity_and_intent_analysis_models_remain_constructible():
    entity = Entity(
        id="entity-a",
        entity_type=EntityType.PROJECT,
        name="Project",
        profile_id="profile-a",
    )
    tag = Tag(id="tag-a", name="Risk", category=TagCategory.RISK, profile_id="profile-a")
    link = EntityTag(entity_id=entity.id, tag_id=tag.id, value="high")

    signal = IntentSignal(
        id="signal-a",
        workspace_id="workspace-a",
        profile_id="profile-a",
        label="Launch",
    )
    tag_model = IntentTag(
        id="tag-intent-a",
        workspace_id="workspace-a",
        profile_id="profile-a",
        label="Launch",
        source=IntentSource.LLM,
    )
    plan = IntentLayoutPlan()
    log = IntentLog(
        id="log-a",
        raw_input="Plan launch",
        channel="api",
        profile_id="profile-a",
    )

    assert link.value == "high"
    assert signal.confidence == 0.5
    assert tag_model.status is IntentTagStatus.CANDIDATE
    assert plan.long_term_intents == []
    assert log.final_decision == {}
