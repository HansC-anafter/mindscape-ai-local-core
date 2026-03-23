from datetime import datetime
from types import SimpleNamespace

from backend.app.models.mindscape import EventType
from backend.features.workspace.executions_core.serializers import (
    serialize_execution_session,
    serialize_tool_call,
)
from backend.features.workspace.executions_core.step_views import (
    group_step_events_by_execution,
)
from backend.features.workspace.executions_core.stream_events import (
    ExecutionStreamEvent,
)
from backend.features.workspace.executions_core.views import (
    get_execution_chat_payload,
    get_execution_payload,
    list_execution_tool_calls_payload,
    list_executions_with_steps_payload,
)


def test_execution_stream_event_execution_update_flattens_task_payload():
    execution = SimpleNamespace(
        model_dump=lambda mode="json": {
            "execution_id": "exec-1",
            "task": {"status": "running", "queue": "default"},
        }
    )

    event = ExecutionStreamEvent.execution_update(execution)

    assert event == {
        "type": "execution_update",
        "execution": {
            "execution_id": "exec-1",
            "task_status": "running",
            "task_queue": "default",
        },
    }


def test_serialize_tool_call_converts_datetimes_to_isoformat():
    tool_call = SimpleNamespace(
        id="tool-1",
        execution_id="exec-1",
        created_at=datetime(2026, 3, 24, 12, 0, 0),
    )

    payload = serialize_tool_call(tool_call)

    assert payload["id"] == "tool-1"
    assert payload["created_at"] == "2026-03-24T12:00:00"


def test_serialize_execution_session_includes_task_metadata():
    task = SimpleNamespace(
        status=SimpleNamespace(value="running"),
        created_at=datetime(2026, 3, 24, 12, 0, 0),
        started_at=None,
        completed_at=None,
        storyline_tags=["ops"],
        execution_context={"foo": "bar"},
    )

    payload = serialize_execution_session(
        task,
        execution_factory=lambda task: {"execution_id": "exec-1", "paused_at": None},
    )

    assert payload["execution_id"] == "exec-1"
    assert payload["status"] == "running"
    assert payload["created_at"] == "2026-03-24T12:00:00"
    assert payload["storyline_tags"] == ["ops"]
    assert payload["execution_context"] == {"foo": "bar"}


def test_group_step_events_by_execution_sorts_by_step_index():
    event_b = SimpleNamespace(payload={"execution_id": "exec-1", "step_index": 2})
    event_a = SimpleNamespace(payload={"execution_id": "exec-1", "step_index": 1})

    grouped = group_step_events_by_execution([event_b, event_a])

    assert grouped["exec-1"] == [event_a, event_b]


def test_list_execution_tool_calls_payload_returns_serialized_records():
    tool_call = SimpleNamespace(id="tool-1", created_at=datetime(2026, 3, 24, 12, 0, 0))
    tool_calls_store = SimpleNamespace(
        list_tool_calls=lambda **kwargs: [tool_call]
    )

    payload = list_execution_tool_calls_payload(
        tool_calls_store=tool_calls_store,
        execution_id="exec-1",
        step_id=None,
    )

    assert payload["count"] == 1
    assert payload["tool_calls"][0]["id"] == "tool-1"


def test_get_execution_chat_payload_filters_and_sorts_messages():
    event_new = SimpleNamespace(
        id="event-2",
        event_type=EventType.EXECUTION_CHAT,
        entity_ids=["exec-1"],
        payload={},
        created_at="2026-03-24T12:01:00",
    )
    event_old = SimpleNamespace(
        id="event-1",
        event_type=EventType.EXECUTION_CHAT,
        entity_ids=["exec-1"],
        payload={},
        created_at="2026-03-24T12:00:00",
    )
    ignored = SimpleNamespace(
        id="event-3",
        event_type="OTHER",
        entity_ids=["exec-1"],
        payload={},
        created_at="2026-03-24T12:02:00",
    )
    store = SimpleNamespace(
        get_events_by_workspace=lambda workspace_id, limit: [event_new, ignored, event_old]
    )

    payload = get_execution_chat_payload(
        store=store,
        workspace_id="ws-1",
        execution_id="exec-1",
        limit=10,
        logger=SimpleNamespace(warning=lambda *args, **kwargs: None),
        message_factory=lambda event: {
            "id": event.id,
            "created_at": event.created_at,
        },
    )

    assert payload["count"] == 2
    assert [message["id"] for message in payload["messages"]] == ["event-1", "event-2"]


def test_get_execution_payload_includes_current_step(monkeypatch):
    task = SimpleNamespace(
        workspace_id="ws-1",
        status=SimpleNamespace(value="running"),
        created_at=None,
        started_at=None,
        completed_at=None,
        storyline_tags=[],
        execution_context={"current_step_index": 1},
    )
    store = SimpleNamespace(get_events_by_workspace=lambda workspace_id, limit: ["event"])
    tasks_store = SimpleNamespace(get_task_by_execution_id=lambda execution_id: task)

    monkeypatch.setattr(
        "backend.features.workspace.executions_core.views.get_current_step_payload",
        lambda events, execution_id, current_step_index, logger: {"step_index": 1},
    )
    monkeypatch.setattr(
        "backend.features.workspace.executions_core.views.serialize_execution_session",
        lambda task: {"execution_id": "exec-1"},
    )

    payload = get_execution_payload(
        store=store,
        tasks_store=tasks_store,
        workspace_id="ws-1",
        execution_id="exec-1",
        logger=SimpleNamespace(warning=lambda *args, **kwargs: None),
    )

    assert payload["current_step"] == {"step_index": 1}


def test_list_executions_with_steps_payload_includes_steps_for_running(monkeypatch):
    task = SimpleNamespace(
        id="task-1",
        status=SimpleNamespace(value="running"),
        created_at=None,
        started_at=None,
        completed_at=None,
        storyline_tags=[],
        execution_context={},
    )
    event = SimpleNamespace(
        event_type=EventType.PLAYBOOK_STEP,
        payload={"execution_id": "exec-1", "step_index": 0},
    )
    store = SimpleNamespace(get_events_by_workspace=lambda workspace_id, limit: [event])
    tasks_store = SimpleNamespace(
        list_executions_by_workspace=lambda workspace_id, limit: [task]
    )

    monkeypatch.setattr(
        "backend.features.workspace.executions_core.views.serialize_execution_session",
        lambda task: {"execution_id": "exec-1", "paused_at": None},
    )
    monkeypatch.setattr(
        "backend.features.workspace.executions_core.views.build_step_payloads",
        lambda events, logger: [{"step_index": 0}],
    )

    payload = list_executions_with_steps_payload(
        store=store,
        tasks_store=tasks_store,
        workspace_id="ws-1",
        limit=10,
        include_steps_for="active",
        logger=SimpleNamespace(warning=lambda *args, **kwargs: None),
    )

    assert payload["count"] == 1
    assert payload["executions"][0]["steps"] == [{"step_index": 0}]
