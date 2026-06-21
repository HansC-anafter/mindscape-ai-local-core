from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from backend.app.models.mindscape import IntentStatus
from backend.app.models.workspace import TimelineItemType
from backend.app.services import intent_infra
from backend.app.services.intent_infra import IntentInfraService


def _service_without_init() -> IntentInfraService:
    return IntentInfraService.__new__(IntentInfraService)


@dataclass
class ExistingIntent:
    title: str
    category: str = "intent_extraction"


def _ctx():
    return SimpleNamespace(actor_id="profile-1", workspace_id="workspace-1")


@pytest.mark.asyncio
async def test_intent_candidate_creation_preserves_cap_and_metadata():
    class FakeStore:
        def __init__(self):
            self.created = []

        def list_intents(self, **kwargs):
            return [ExistingIntent("Existing")] + self.created

        def create_intent(self, intent):
            self.created.append(intent)
            return intent

    service = _service_without_init()
    service.store = FakeStore()

    count = await service._create_intent_cards_from_candidates(
        ctx=_ctx(),
        intent_candidates=[
            {"title": "Existing", "confidence": 0.9},
            {"title": "Alpha", "confidence": 0.8},
            "Beta",
            "Gamma",
        ],
        task_id="task-1",
        workspace_id="workspace-1",
    )

    assert count == 2
    assert [intent.title for intent in service.store.created] == ["Alpha", "Beta"]
    assert service.store.created[0].status == IntentStatus.PAUSED
    assert service.store.created[0].metadata == {
        "source": "intent_extraction_task",
        "workspace_id": "workspace-1",
        "task_id": "task-1",
    }


@pytest.mark.asyncio
async def test_timeline_creation_preserves_payload_fields():
    class FakeI18n:
        def t(self, namespace, key, count, default):
            return default

    class FakeTimelineStore:
        def __init__(self):
            self.items = []

        def create_timeline_item(self, item):
            self.items.append(item)

    service = _service_without_init()
    service.i18n = FakeI18n()
    service.timeline_items_store = FakeTimelineStore()

    result = await service._create_timeline_for_extraction(
        ctx=_ctx(),
        original_message_id="message-1",
        task_id="task-1",
        intents=[{"title": "Alpha"}],
        themes=["theme-1"],
        intents_added=1,
    )

    assert result is service.timeline_items_store.items[0]
    assert result.type == TimelineItemType.INTENT_SEEDS
    assert result.workspace_id == "workspace-1"
    assert result.message_id == "message-1"
    assert result.task_id == "task-1"
    assert result.data["source"] == "intent_extraction_task"
    assert result.data["intents_added"] == 1


@pytest.mark.asyncio
async def test_flow_execution_wrapper_calls_executor_without_raising():
    class FakeExecutor:
        def __init__(self):
            self.calls = []

        async def execute_flow(self, **kwargs):
            self.calls.append(kwargs)
            return {"status": "completed"}

    service = _service_without_init()
    executor = FakeExecutor()

    await service._execute_playbook_flow_async(
        flow_executor=executor,
        project_id="project-1",
        workspace_id="workspace-1",
        profile_id="profile-1",
    )

    assert executor.calls == [
        {
            "project_id": "project-1",
            "workspace_id": "workspace-1",
            "profile_id": "profile-1",
        }
    ]


@pytest.mark.asyncio
async def test_flow_execution_wrapper_swallows_executor_failure():
    class FailingExecutor:
        async def execute_flow(self, **kwargs):
            raise RuntimeError("boom")

    service = _service_without_init()

    await service._execute_playbook_flow_async(
        flow_executor=FailingExecutor(),
        project_id="project-1",
        workspace_id="workspace-1",
        profile_id="profile-1",
    )


def test_public_facade_keeps_intent_infra_surface():
    assert hasattr(intent_infra, "IntentInfraService")
    assert hasattr(IntentInfraService, "handle_extraction_task")
    assert hasattr(IntentInfraService, "_create_project_from_intent")
    assert hasattr(IntentInfraService, "_execute_playbook_flow_async")
    assert hasattr(IntentInfraService, "create_intent_card")
    assert hasattr(IntentInfraService, "list_intents")
