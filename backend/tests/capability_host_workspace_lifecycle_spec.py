from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

import backend.app.capability_host.workspace_lifecycle as lifecycle
from backend.app.services.workspace_event_lifecycle import (
    serialize_mind_event_cloud_event,
)


WORKSPACE_ID = "11111111-1111-4111-8111-111111111111"


def _event(**overrides):
    data = overrides.pop(
        "data",
        {"event_type": "creative_loop.updated", "loop_id": "loop-1"},
    )
    event = {
        "specversion": "1.0",
        "id": "22222222-2222-4222-8222-222222222222",
        "source": "mindscape://creative-studio/loop/loop-1",
        "type": "creative_studio.loop.updated.v1",
        "subject": "creative_loop:loop-1",
        "time": "2026-07-15T16:00:00Z",
        "datacontenttype": "application/json",
        "dataschema": "creative_studio.loop_event.v1",
        "aggregateid": "loop-1",
        "aggregateversion": 1,
        "causationid": "command-1",
        "correlationid": "correlation-1",
        "ownerref": "mindscape://creative-studio/loop/loop-1",
        "workspaceid": WORKSPACE_ID,
        "payloadchecksum": lifecycle.workspace_event_payload_checksum(data),
        "data": data,
    }
    event.update(overrides)
    return event


class _Result:
    def __init__(self, *, scalar=None, row=None):
        self.scalar = scalar
        self.row = row

    def scalar_one_or_none(self):
        return self.scalar

    def mappings(self):
        return self

    def first(self):
        return self.row


class _Session:
    def __init__(self, *results):
        self.results = list(results)
        self.calls = []

    async def execute(self, statement, params):
        self.calls.append({"statement": str(statement), "params": params})
        return self.results.pop(0)

    async def commit(self):
        raise AssertionError("public append facade must not own commit")


class _SyncSession:
    def __init__(self, *results):
        self.results = list(results)
        self.calls = []

    def execute(self, statement, params):
        self.calls.append({"statement": str(statement), "params": params})
        return self.results.pop(0)

    def commit(self):
        raise AssertionError("public append facade must not own commit")


@pytest.mark.asyncio
async def test_append_uses_caller_session_without_commit_or_publish(monkeypatch):
    monkeypatch.setattr(
        lifecycle,
        "_publish_committed_event",
        lambda _event: (_ for _ in ()).throw(AssertionError("must not publish")),
    )
    session = _Session(_Result(scalar=_event()["id"]))

    receipt = await lifecycle.append_workspace_cloud_event(session, _event())

    assert receipt["status"] == "inserted"
    assert len(session.calls) == 1
    assert "FROM workspaces" in session.calls[0]["statement"]
    assert "ON CONFLICT (id) DO NOTHING" in session.calls[0]["statement"]


def test_sync_append_uses_same_caller_transaction_without_commit_or_publish(monkeypatch):
    monkeypatch.setattr(
        lifecycle,
        "_publish_committed_event",
        lambda _event: (_ for _ in ()).throw(AssertionError("must not publish")),
    )
    session = _SyncSession(_Result(scalar=_event()["id"]))

    receipt = lifecycle.append_workspace_cloud_event_sync(session, _event())

    assert receipt["status"] == "inserted"
    assert len(session.calls) == 1
    assert session.calls[0]["statement"] is not None
    assert "ON CONFLICT (id) DO NOTHING" in session.calls[0]["statement"]


def test_sync_duplicate_identical_event_uses_shared_collision_verifier():
    event = lifecycle.normalize_workspace_cloud_event(_event())
    envelope = {key: value for key, value in event.items() if key != "data"}
    session = _SyncSession(
        _Result(scalar=None),
        _Result(
            row={
                "workspace_id": WORKSPACE_ID,
                "payload": json.dumps(event["data"]),
                "metadata": json.dumps({"workspace_cloud_event": envelope}),
            }
        ),
    )

    receipt = lifecycle.append_workspace_cloud_event_sync(session, event)

    assert receipt["status"] == "existing"
    assert len(session.calls) == 2


@pytest.mark.asyncio
async def test_duplicate_identical_event_returns_existing():
    event = lifecycle.normalize_workspace_cloud_event(_event())
    envelope = {key: value for key, value in event.items() if key != "data"}
    session = _Session(
        _Result(scalar=None),
        _Result(
            row={
                "workspace_id": WORKSPACE_ID,
                "payload": json.dumps(event["data"]),
                "metadata": json.dumps({"workspace_cloud_event": envelope}),
            }
        ),
    )

    receipt = await lifecycle.append_workspace_cloud_event(session, event)

    assert receipt["status"] == "existing"
    assert len(session.calls) == 2


@pytest.mark.asyncio
async def test_duplicate_event_id_with_different_envelope_fails_closed():
    event = lifecycle.normalize_workspace_cloud_event(_event())
    conflicting = lifecycle.normalize_workspace_cloud_event(
        _event(type="creative_studio.loop.failed.v1")
    )
    envelope = {key: value for key, value in conflicting.items() if key != "data"}
    session = _Session(
        _Result(scalar=None),
        _Result(
            row={
                "workspace_id": WORKSPACE_ID,
                "payload": json.dumps(conflicting["data"]),
                "metadata": json.dumps({"workspace_cloud_event": envelope}),
            }
        ),
    )

    with pytest.raises(ValueError, match="id_collision"):
        await lifecycle.append_workspace_cloud_event(session, event)


@pytest.mark.asyncio
async def test_unknown_workspace_does_not_fall_through_to_duplicate():
    session = _Session(_Result(scalar=None), _Result(row=None))

    with pytest.raises(ValueError, match="workspace_not_found"):
        await lifecycle.append_workspace_cloud_event(session, _event())


def test_validation_rejects_workspace_mismatch_and_oversized_payload():
    mismatch = _event(workspaceid="")
    with pytest.raises(ValueError, match="required_attribute_missing"):
        lifecycle.normalize_workspace_cloud_event(mismatch)

    data = {"value": "x" * 150_000}
    oversized = _event(
        data=data,
        payloadchecksum=lifecycle.workspace_event_payload_checksum(data),
    )
    with pytest.raises(ValueError, match="payload_too_large"):
        lifecycle.normalize_workspace_cloud_event(oversized)


def test_validation_rejects_non_durable_event_id():
    with pytest.raises(ValueError, match="id_invalid"):
        lifecycle.normalize_workspace_cloud_event(_event(id="x" * 37))


def test_optional_time_remains_absent_and_deterministic():
    event = _event()
    event.pop("time")

    first = lifecycle.normalize_workspace_cloud_event(event)
    second = lifecycle.normalize_workspace_cloud_event(event)

    assert "time" not in first
    assert lifecycle.workspace_cloud_event_checksum(
        first
    ) == lifecycle.workspace_cloud_event_checksum(second)


def test_post_commit_publisher_delegates_only_normalized_event(monkeypatch):
    observed = {}
    monkeypatch.setattr(
        lifecycle,
        "_publish_committed_event",
        lambda event: observed.setdefault("event", event) is event,
    )

    assert lifecycle.publish_committed_workspace_cloud_event(_event()) is True
    assert observed["event"]["time"] == "2026-07-15T16:00:00Z"
    assert observed["event"]["workspaceid"] == WORKSPACE_ID


def test_stored_capability_event_round_trips_through_existing_sse_mapper():
    event = lifecycle.normalize_workspace_cloud_event(_event())
    envelope = {key: value for key, value in event.items() if key != "data"}
    stored = SimpleNamespace(
        id=event["id"],
        timestamp=datetime(2026, 7, 15, 16, tzinfo=timezone.utc),
        actor="system",
        channel="capability_host",
        profile_id="profile-1",
        project_id=None,
        workspace_id=WORKSPACE_ID,
        thread_id=None,
        event_type="capability_event",
        payload=event["data"],
        entity_ids=[],
        metadata={"workspace_cloud_event": envelope},
    )

    assert serialize_mind_event_cloud_event(stored) == event


def test_public_facade_does_not_create_session_pool_or_import_private_store():
    source = Path(lifecycle.__file__).read_text(encoding="utf-8")

    for forbidden in (
        "create_async_engine",
        "create_engine",
        "sessionmaker",
        "get_async_session",
        "PostgresEventsStore",
        "MindscapeStore",
        "session.commit",
        "session.rollback",
    ):
        assert forbidden not in source
