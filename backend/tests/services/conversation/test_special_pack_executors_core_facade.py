from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from backend.app.models.mindscape import EventType
from backend.app.models.workspace import TaskStatus, TimelineItemType
from backend.app.services.conversation import special_pack_executors as facade_module
from backend.app.services.conversation.special_pack_executors import (
    SpecialPackExecutors,
)
from backend.app.services.conversation.special_pack_executors_core import (
    results,
    runtime,
    sources,
)


class FakeTasksStore:
    def __init__(self):
        self.created = []
        self.status_updates = []

    def create_task(self, task):
        self.created.append(task)
        return task

    def update_task_status(self, **kwargs):
        self.status_updates.append(kwargs)


class FakeEmitter:
    def __init__(self):
        self.created = []
        self.updated = []

    def emit_task_created(self, **kwargs):
        self.created.append(kwargs)

    def emit_task_updated(self, **kwargs):
        self.updated.append(kwargs)


def test_special_pack_executors_method_surface():
    expected = [
        "execute_semantic_seeds",
        "_get_intents_from_timeline_items",
        "_get_intents_from_events",
        "_extract_intents_from_files",
        "_extract_intents_from_message",
        "_build_execution_result",
    ]

    assert [name for name in expected if not hasattr(SpecialPackExecutors, name)] == []


@pytest.mark.asyncio
async def test_special_pack_executors_facade_delegates(monkeypatch):
    executor = SpecialPackExecutors.__new__(SpecialPackExecutors)
    observed = {}

    async def fake_execute_semantic_seeds(**kwargs):
        observed["execute"] = kwargs
        return {"pack_id": "semantic_seeds"}

    async def fake_get_timeline(**kwargs):
        observed["timeline"] = kwargs
        return ["timeline"]

    async def fake_get_events(**kwargs):
        observed["events"] = kwargs
        return ["event"], ["content"]

    async def fake_extract_files(**kwargs):
        observed["files"] = kwargs
        return ["file"]

    async def fake_extract_message(**kwargs):
        observed["message"] = kwargs
        return ["message"]

    monkeypatch.setattr(
        facade_module,
        "execute_semantic_seeds_helper",
        fake_execute_semantic_seeds,
    )
    monkeypatch.setattr(facade_module, "get_intents_from_timeline_items", fake_get_timeline)
    monkeypatch.setattr(facade_module, "get_intents_from_events", fake_get_events)
    monkeypatch.setattr(facade_module, "extract_intents_from_files", fake_extract_files)
    monkeypatch.setattr(facade_module, "extract_intents_from_message", fake_extract_message)
    monkeypatch.setattr(
        facade_module,
        "build_execution_result",
        lambda **kwargs: {"result": kwargs},
    )

    executor.timeline_items_store = object()
    executor.store = object()
    executor.config_store = object()
    assert (
        await executor.execute_semantic_seeds(
            workspace_id="ws_1",
            profile_id="profile_1",
            message_id="msg_1",
            files=[],
            message="message",
            event_emitter=Mock(),
        )
    ) == {"pack_id": "semantic_seeds"}
    assert await executor._get_intents_from_timeline_items("ws_1") == ["timeline"]
    assert await executor._get_intents_from_events("ws_1", [], []) == (
        ["event"],
        ["content"],
    )
    assert await executor._extract_intents_from_files(
        "profile_1", "msg_1", "message", ["content"]
    ) == ["file"]
    assert await executor._extract_intents_from_message(
        "profile_1", "msg_1", "message"
    ) == ["message"]
    assert executor._build_execution_result(["a"], [], []) == {
        "result": {"extracted_intents": ["a"], "files": [], "file_contents": []}
    }
    assert observed["execute"]["executor"] is executor
    assert observed["timeline"]["timeline_items_store"] is executor.timeline_items_store
    assert observed["events"]["store"] is executor.store
    assert observed["files"]["config_store"] is executor.config_store
    assert observed["message"]["config_store"] is executor.config_store


@pytest.mark.asyncio
async def test_timeline_source_extracts_unique_intents():
    store = SimpleNamespace(
        list_timeline_items_by_workspace=Mock(
            return_value=[
                SimpleNamespace(
                    id="tl_1",
                    type=TimelineItemType.INTENT_SEEDS,
                    data={
                        "intents": [
                            {"title": "Plan campaign"},
                            {"text": "Draft outline"},
                            "Plan campaign",
                        ]
                    },
                )
            ]
        )
    )

    assert await sources.get_intents_from_timeline_items(
        timeline_items_store=store,
        workspace_id="ws_1",
    ) == ["Plan campaign", "Draft outline"]


@pytest.mark.asyncio
async def test_event_source_extracts_intents_and_file_content():
    event = SimpleNamespace(
        event_type=EventType.MESSAGE,
        metadata={
            "file_analysis": {
                "collaboration_results": {
                    "semantic_seeds": {
                        "enabled": True,
                        "intents": [{"title": "Build map"}, "Collect sources"],
                    }
                },
                "analysis": {"file_info": {"text_content": "file body"}},
            }
        },
    )
    store = SimpleNamespace(
        get_events_by_workspace=Mock(return_value=[event]),
    )

    intents, file_contents = await sources.get_intents_from_events(
        store=store,
        workspace_id="ws_1",
        extracted_intents=["Build map"],
        file_contents=[],
    )

    assert intents == ["Build map", "Collect sources"]
    assert file_contents == ["file body"]


def test_build_execution_result_preserves_shape():
    file_result = results.build_execution_result(
        extracted_intents=["a", "b", "c", "d", "e", "f"],
        files=["file_1", "file_2"],
        file_contents=["content"],
    )
    message_result = results.build_execution_result(
        extracted_intents=["a"],
        files=[],
        file_contents=[],
    )

    assert file_result == {
        "title": "Extracted 6 intents from 2 file(s)",
        "summary": "Found 6 potential intents or projects from files",
        "message": "Extracted 6 intents from uploaded files",
        "intents": ["a", "b", "c", "d", "e"],
        "files_processed": 2,
        "source": "files",
    }
    assert message_result["source"] == "message"
    assert message_result["files_processed"] == 0


@pytest.mark.asyncio
async def test_execute_semantic_seeds_lifecycle(monkeypatch):
    async def fake_get_timeline(**kwargs):
        return ["Timeline intent"]

    async def fake_get_events(**kwargs):
        return kwargs["extracted_intents"] + ["Event intent"], ["file body"]

    monkeypatch.setattr(runtime, "get_intents_from_timeline_items", fake_get_timeline)
    monkeypatch.setattr(runtime, "get_intents_from_events", fake_get_events)
    monkeypatch.setattr(runtime, "extract_intents_from_files", AsyncMock())
    monkeypatch.setattr(runtime, "extract_intents_from_message", AsyncMock())

    tasks_store = FakeTasksStore()
    emitter = FakeEmitter()
    executor = SimpleNamespace(
        tasks_store=tasks_store,
        timeline_items_store=object(),
        store=object(),
        config_store=object(),
        event_emitter=emitter,
    )

    result = await runtime.execute_semantic_seeds(
        executor=executor,
        workspace_id="ws_1",
        profile_id="profile_1",
        message_id="msg_1",
        files=[],
        message="Extract seeds",
    )

    task = tasks_store.created[0]
    assert task.status == TaskStatus.RUNNING
    assert tasks_store.status_updates[0]["task_id"] == task.id
    assert tasks_store.status_updates[0]["status"] == TaskStatus.SUCCEEDED
    assert emitter.created[0]["task_id"] == task.id
    assert emitter.updated[0]["status"] == "succeeded"
    assert result["pack_id"] == "semantic_seeds"
    assert result["task_id"] == task.id
    assert result["result"]["intents"] == ["Timeline intent", "Event intent"]
    runtime.extract_intents_from_files.assert_not_awaited()
    runtime.extract_intents_from_message.assert_not_awaited()
