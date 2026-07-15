"""Projection and freshness helpers for meeting session store rows."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from backend.app.models.meeting_decision import MeetingDecision
from backend.app.models.meeting_session import MeetingSession, MeetingStatus

DeserializeJson = Callable[..., Any]

DEFAULT_ACTIVE_SESSION_FRESHNESS = timedelta(minutes=30)
DEFAULT_PLANNED_SESSION_FRESHNESS = timedelta(minutes=15)
SESSION_ACTIVITY_METADATA_KEYS = (
    "last_round_updated_at",
    "pipeline_stage_updated_at",
    "dispatch_updated_at",
    "updated_at",
)


def row_data(row: Any) -> Dict[str, Any]:
    return row._mapping if hasattr(row, "_mapping") else row


def coerce_activity_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value))
        except Exception:
            return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def is_active_session_fresh(
    session: MeetingSession,
    *,
    now: Optional[datetime] = None,
    active_ttl: timedelta = DEFAULT_ACTIVE_SESSION_FRESHNESS,
    planned_ttl: timedelta = DEFAULT_PLANNED_SESSION_FRESHNESS,
) -> bool:
    if session is None or session.ended_at is not None:
        return False

    effective_now = now or datetime.now(timezone.utc)
    if effective_now.tzinfo is None:
        effective_now = effective_now.replace(tzinfo=timezone.utc)
    else:
        effective_now = effective_now.astimezone(timezone.utc)

    activity_points: List[datetime] = []
    started_at = coerce_activity_datetime(session.started_at)
    if started_at is not None:
        activity_points.append(started_at)

    for key in SESSION_ACTIVITY_METADATA_KEYS:
        activity_dt = coerce_activity_datetime((session.metadata or {}).get(key))
        if activity_dt is not None:
            activity_points.append(activity_dt)

    if not activity_points:
        return False

    ttl = planned_ttl if session.status == MeetingStatus.PLANNED else active_ttl
    return max(activity_points) >= (effective_now - ttl)


def row_to_session(row: Any, *, deserialize_json: DeserializeJson) -> MeetingSession:
    data = row_data(row)
    try:
        status = MeetingStatus(data.get("status", MeetingStatus.PLANNED.value))
    except Exception:
        status = MeetingStatus.PLANNED

    started_at = data["started_at"]
    if not isinstance(started_at, datetime):
        started_at = datetime.fromisoformat(str(started_at))

    ended_at = data.get("ended_at")
    if ended_at and not isinstance(ended_at, datetime):
        ended_at = datetime.fromisoformat(str(ended_at))

    return MeetingSession(
        id=data["id"],
        workspace_id=data["workspace_id"],
        project_id=data.get("project_id"),
        thread_id=data.get("thread_id"),
        lens_id=data.get("lens_id"),
        workspace_group_snapshot_id=data.get("workspace_group_snapshot_id"),
        started_at=started_at,
        ended_at=ended_at,
        status=status,
        meeting_type=data.get("meeting_type", "general"),
        agenda=deserialize_json(data.get("agenda"), []),
        success_criteria=deserialize_json(data.get("success_criteria"), []),
        round_count=data.get("round_count", 0) or 0,
        max_rounds=data.get("max_rounds", 5) or 5,
        action_items=deserialize_json(data.get("action_items"), []),
        minutes_md=data.get("minutes_md", "") or "",
        state_before=deserialize_json(data.get("state_before"), {}),
        state_after=deserialize_json(data.get("state_after"), {}),
        decisions=deserialize_json(data.get("decisions"), []),
        traces=deserialize_json(data.get("traces"), []),
        intents_patched=deserialize_json(data.get("intents_patched"), []),
        metadata=deserialize_json(data.get("metadata"), {}),
    )


def unresolved_decision_from_row(row: Any) -> Dict[str, Any]:
    return {
        "id": row[0],
        "session_id": row[1],
        "workspace_id": row[2],
        "category": row[3],
        "content": row[4],
        "status": row[5],
        "resolved_by_task_id": row[6],
        "created_at": row[7].isoformat() if row[7] else None,
    }


def row_to_meeting_decision(
    row: Any,
    *,
    deserialize_json: DeserializeJson,
) -> MeetingDecision:
    data = row_data(row)
    created_at = data["created_at"]
    if created_at and not isinstance(created_at, datetime):
        created_at = datetime.fromisoformat(str(created_at))
    return MeetingDecision(
        id=data["id"],
        session_id=data["session_id"],
        workspace_id=data["workspace_id"],
        category=data["category"],
        content=data["content"],
        status=data.get("status") or "pending",
        resolved_by_task_id=data.get("resolved_by_task_id"),
        source_action_item=deserialize_json(data.get("source_action_item"), default={}),
        created_at=created_at,
    )
