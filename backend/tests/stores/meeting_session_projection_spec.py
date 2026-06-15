import json
from datetime import datetime, timedelta, timezone

from backend.app.models.meeting_session import MeetingSession, MeetingStatus
from backend.app.services.stores.meeting_session_projection import (
    is_active_session_fresh,
    row_to_meeting_decision,
    row_to_session,
    unresolved_decision_from_row,
)


def _deserialize_json(value, default=None):
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    return json.loads(value)


def test_row_to_session_projects_json_fields_and_status():
    row = {
        "id": "session-1",
        "workspace_id": "workspace-1",
        "project_id": "project-1",
        "thread_id": "thread-1",
        "lens_id": "lens-1",
        "started_at": "2026-06-16T01:00:00+00:00",
        "ended_at": None,
        "status": "active",
        "meeting_type": "planning",
        "agenda": json.dumps(["scope"]),
        "success_criteria": json.dumps(["done"]),
        "round_count": 2,
        "max_rounds": 4,
        "action_items": json.dumps([{"task": "ship"}]),
        "minutes_md": "notes",
        "state_before": json.dumps({"a": 1}),
        "state_after": json.dumps({"a": 2}),
        "decisions": json.dumps(["decision-1"]),
        "traces": json.dumps(["trace-1"]),
        "intents_patched": json.dumps(["intent-1"]),
        "metadata": json.dumps({"updated_at": "2026-06-16T01:05:00+00:00"}),
    }

    session = row_to_session(row, deserialize_json=_deserialize_json)

    assert session.id == "session-1"
    assert session.status == MeetingStatus.ACTIVE
    assert session.agenda == ["scope"]
    assert session.action_items == [{"task": "ship"}]
    assert session.state_diff == {"a": {"before": 1, "after": 2}}


def test_decision_projection_helpers_preserve_shapes():
    created_at = datetime(2026, 6, 16, 1, 0, tzinfo=timezone.utc)
    unresolved = unresolved_decision_from_row(
        (
            "decision-1",
            "session-1",
            "workspace-1",
            "action",
            "Do it",
            "pending",
            None,
            created_at,
        )
    )
    decision = row_to_meeting_decision(
        {
            "id": "decision-1",
            "session_id": "session-1",
            "workspace_id": "workspace-1",
            "category": "action",
            "content": "Do it",
            "status": None,
            "resolved_by_task_id": None,
            "source_action_item": json.dumps({"task": "Do it"}),
            "created_at": created_at.isoformat(),
        },
        deserialize_json=_deserialize_json,
    )

    assert unresolved["created_at"] == "2026-06-16T01:00:00+00:00"
    assert decision.status == "pending"
    assert decision.source_action_item == {"task": "Do it"}
    assert decision.created_at == created_at


def test_is_active_session_fresh_uses_status_specific_ttl():
    now = datetime(2026, 6, 16, 2, 0, tzinfo=timezone.utc)
    planned = MeetingSession(
        id="session-1",
        workspace_id="workspace-1",
        started_at=now - timedelta(minutes=10),
        status=MeetingStatus.PLANNED,
    )
    stale_active = MeetingSession(
        id="session-2",
        workspace_id="workspace-1",
        started_at=now - timedelta(hours=2),
        status=MeetingStatus.ACTIVE,
        metadata={"dispatch_updated_at": (now - timedelta(minutes=45)).isoformat()},
    )

    assert is_active_session_fresh(planned, now=now) is True
    assert is_active_session_fresh(stale_active, now=now) is False
    stale_active.metadata["dispatch_updated_at"] = (now - timedelta(minutes=5)).isoformat()
    assert is_active_session_fresh(stale_active, now=now) is True
