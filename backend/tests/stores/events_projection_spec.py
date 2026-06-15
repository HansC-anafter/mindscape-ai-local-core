import json
from datetime import datetime

from backend.app.models.mindscape import EventActor, EventType
from backend.app.services.stores.events_projection import row_to_event, rows_to_events


class RecordingLogger:
    def __init__(self):
        self.errors = []
        self.warnings = []

    def error(self, message, *args):
        self.errors.append(message % args if args else message)

    def warning(self, message, *args):
        self.warnings.append(message % args if args else message)


def _deserialize_json(value, default):
    if value is None:
        return default
    if value == "bad_payload":
        return ["not-a-dict"]
    if value == "bad_entity_ids":
        return {"not": "a-list"}
    return json.loads(value)


def _base_row(**overrides):
    row = {
        "id": "event-1",
        "timestamp": "2026-06-16T01:00:00+00:00",
        "actor": EventActor.USER.value,
        "channel": "local_chat",
        "profile_id": "profile-1",
        "project_id": None,
        "workspace_id": "workspace-1",
        "thread_id": "thread-1",
        "event_type": EventType.MESSAGE.value,
        "payload": json.dumps({"text": "hello"}),
        "entity_ids": json.dumps(["entity-1"]),
        "metadata": json.dumps({"source": "spec"}),
    }
    row.update(overrides)
    return row


def test_row_to_event_projects_json_fields_into_mind_event():
    event = row_to_event(
        _base_row(),
        deserialize_json=_deserialize_json,
        from_isoformat=datetime.fromisoformat,
        logger=RecordingLogger(),
    )

    assert event.id == "event-1"
    assert event.actor == EventActor.USER
    assert event.event_type == EventType.MESSAGE
    assert event.payload == {"text": "hello"}
    assert event.entity_ids == ["entity-1"]
    assert event.metadata == {"source": "spec"}
    assert event.thread_id == "thread-1"


def test_row_to_event_preserves_type_fallbacks_for_bad_json_shapes():
    logger = RecordingLogger()

    event = row_to_event(
        _base_row(
            payload="bad_payload",
            entity_ids="bad_entity_ids",
            metadata=json.dumps(["not-a-dict"]),
        ),
        deserialize_json=_deserialize_json,
        from_isoformat=datetime.fromisoformat,
        logger=logger,
    )

    assert event.payload == {}
    assert event.entity_ids == []
    assert event.metadata == {}
    assert logger.warnings


def test_rows_to_events_skips_bad_rows_and_keeps_good_rows():
    logger = RecordingLogger()

    events = rows_to_events(
        ["good", "bad", "also-good"],
        row_to_event=lambda row: row if row != "bad" else (_ for _ in ()).throw(ValueError("boom")),
        context="in projection spec",
        logger=logger,
    )

    assert events == ["good", "also-good"]
    assert "Error converting row 1 in projection spec: boom" in logger.errors
