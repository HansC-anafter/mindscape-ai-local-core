from types import SimpleNamespace

import pytest

from backend.app.models.mindscape import (
    IntentCard,
    IntentLayoutPlan,
    IntentOperation,
    IntentSignal,
    IntentStatus,
    IntentStewardInput,
    PriorityLevel,
    SignalMapping,
)
from backend.app.services.conversation import intent_steward as steward_module
from backend.app.services.conversation.intent_steward import IntentStewardService


class _FakeIntentsStore:
    def __init__(self, store):
        self.store = store

    def update_intent(self, intent):
        self.store.intents_by_id[intent.id] = intent
        return intent


class _FakeStore:
    def __init__(self):
        self.created_intents = []
        self.created_logs = []
        self.intents_by_id = {}
        self.intents = _FakeIntentsStore(self)

    def create_intent(self, intent):
        self.created_intents.append(intent)
        self.intents_by_id[intent.id] = intent
        return intent

    def get_intent(self, intent_id):
        return self.intents_by_id.get(intent_id)

    def list_intents(self, profile_id):
        del profile_id
        return list(self.intents_by_id.values())

    def create_intent_log(self, intent_log):
        self.created_logs.append(intent_log)
        return intent_log


def _service(monkeypatch):
    monkeypatch.setattr(steward_module, "IntentTagsStore", lambda: SimpleNamespace())
    monkeypatch.setattr(
        steward_module, "PostgresTimelineItemsStore", lambda: SimpleNamespace()
    )
    monkeypatch.setattr(
        steward_module, "PostgresEventsStore", lambda: SimpleNamespace()
    )
    return IntentStewardService(store=_FakeStore())


def _signal(signal_id, label, confidence=0.9):
    return IntentSignal(
        id=signal_id,
        workspace_id="ws_1",
        profile_id="profile_1",
        label=label,
        confidence=confidence,
    )


def _intent(intent_id="intent_1", title="Launch Plan"):
    return IntentCard(
        id=intent_id,
        profile_id="profile_1",
        title=title,
        description="Original description",
        status=IntentStatus.ACTIVE,
        priority=PriorityLevel.MEDIUM,
    )


@pytest.mark.asyncio
async def test_prefilter_filters_low_confidence_duplicates_and_noise(monkeypatch):
    service = _service(monkeypatch)
    signals = [
        _signal("s1", "Launch Plan", 0.9),
        _signal("s2", "launch plan", 0.95),
        _signal("s3", "12", 0.99),
        _signal("s4", "Low Confidence", 0.4),
        _signal("s5", "2222", 0.99),
        _signal("s6", "Ship", 0.7),
    ]

    filtered = await service.prefilter_signals(signals)

    assert [signal.id for signal in filtered] == ["s1", "s6"]


@pytest.mark.asyncio
async def test_steward_analyze_supports_positional_contract(monkeypatch):
    service = _service(monkeypatch)
    monkeypatch.setattr(service, "_llm_analyze_signals", _no_llm)
    signals = [
        _signal("s1", "Build Modular Entry Alpha"),
        _signal("s2", "Build Modular Entry Beta"),
    ]
    context = IntentStewardInput(recent_signals=signals, current_intent_cards=[])

    layout = await service.steward_analyze(signals, context)

    assert len(layout.long_term_intents) == 1
    assert layout.long_term_intents[0].operation_type == "CREATE_INTENT_CARD"
    assert [mapping.signal_id for mapping in layout.signal_mapping] == ["s1", "s2"]


@pytest.mark.asyncio
async def test_steward_analyze_supports_hook_keyword_contract(monkeypatch):
    service = _service(monkeypatch)
    monkeypatch.setattr(service, "_llm_analyze_signals", _no_llm)
    signals = [
        _signal("s1", "Build Modular Entry Alpha"),
        _signal("s2", "Build Modular Entry Beta"),
    ]
    steward_input = IntentStewardInput(
        recent_signals=signals,
        current_intent_cards=[],
    )

    layout = await service.steward_analyze(
        workspace_id="ws_1",
        profile_id="profile_1",
        steward_input=steward_input,
    )

    assert service._current_workspace_id == "ws_1"
    assert len(layout.long_term_intents) == 1
    assert layout.long_term_intents[0].intent_data["title"] == "Build Modular Entry Alpha"


def test_find_similar_intent_matches_exact_and_prefix(monkeypatch):
    service = _service(monkeypatch)
    exact = _intent("intent_exact", "Launch Plan")
    prefix = _intent("intent_prefix", "Build Modular Entry Alpha")

    assert service._find_similar_intent("launch plan", [exact]).id == "intent_exact"
    assert (
        service._find_similar_intent(
            "Build Modular Entry Beta",
            [prefix],
        ).id
        == "intent_prefix"
    )


@pytest.mark.asyncio
async def test_execute_layout_plan_creates_intent_and_updates_mapping(monkeypatch):
    service = _service(monkeypatch)
    layout = IntentLayoutPlan(
        long_term_intents=[
            IntentOperation(
                operation_type="CREATE_INTENT_CARD",
                intent_data={"title": "Launch Plan", "priority": "medium"},
                relation_signals=["s1"],
                confidence=0.9,
                reasoning="Detected recurring goal",
            )
        ],
        signal_mapping=[
            SignalMapping(
                signal_id="s1",
                action="mapped_to_intent_id",
                reasoning="Grouped with matching signal",
            )
        ],
    )

    await service._execute_layout_plan(layout, "ws_1", "profile_1", "turn_1")

    created = service.store.created_intents[0]
    assert created.title == "Launch Plan"
    assert created.metadata["workspace_id"] == "ws_1"
    assert layout.signal_mapping[0].target_intent_id == created.id
    assert layout.metadata["executed_operations"][0]["type"] == "CREATE"


@pytest.mark.asyncio
async def test_execute_layout_plan_updates_existing_intent_with_rollback_metadata(
    monkeypatch,
):
    service = _service(monkeypatch)
    existing = _intent("intent_1", "Original Goal")
    service.store.intents_by_id[existing.id] = existing
    layout = IntentLayoutPlan(
        long_term_intents=[
            IntentOperation(
                operation_type="UPDATE_INTENT_CARD",
                intent_id="intent_1",
                intent_data={"title": "Updated Goal", "priority": "high"},
                relation_signals=["s1"],
                confidence=0.92,
                reasoning="Matched existing goal",
            )
        ]
    )

    await service._execute_layout_plan(layout, "ws_1", "profile_1", "turn_1")

    updated = service.store.get_intent("intent_1")
    assert updated.title == "Updated Goal"
    assert updated.priority == PriorityLevel.HIGH
    assert updated.metadata["rollback_data"]["title"] == "Original Goal"
    assert layout.metadata["executed_operations"][0]["type"] == "UPDATE"


async def _no_llm(filtered_signals, context):
    del filtered_signals, context
    return None
