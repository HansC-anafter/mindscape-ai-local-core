"""Recent event and meeting summary helpers for workspace project cards."""

from datetime import datetime, timedelta, timezone
from typing import Any

from backend.app.models.project import Project
from backend.app.services.stores.meeting_session_store import MeetingSessionStore


async def build_card_events(
    *,
    events_store: Any,
    project_id: str,
) -> list[dict[str, Any]]:
    """Transform recent project events into card display events."""
    # Get recent events for card display
    # Use the all_workspace_events we already fetched earlier
    recent_events_list = []

    # First try project events
    project_events_for_display = events_store.get_events_by_project(
        project_id=project_id, limit=10
    )
    recent_events_list.extend(project_events_for_display)

    # Always get workspace events that match our project executions
    # Use the all_workspace_events we already fetched earlier
    # [PERFORMANCE FIX] Second sync full table scan removed.
    # This logic (duplicate of the one removed earlier) caused severe event loop blocking.
    pass

    # Transform events to card format
    card_events = []
    # [PERFORMANCE] Instantiate Registry once outside the loop to avoid disk thrashing
    from backend.app.services.playbook_registry import PlaybookRegistry

    playbook_registry = PlaybookRegistry()

    for event in recent_events_list[:5]:
        event_type = None
        playbook_code = None
        playbook_name = None
        # ... (rest of loop logic)

        if event.payload and isinstance(event.payload, dict):
            # ...
            playbook_code = event.payload.get("playbook_code")
            # ...

            # Try to get playbook name
            if playbook_code:
                try:
                    # Use cached registry lookup (lazy loaded)
                    playbook = await playbook_registry.get_playbook(
                        playbook_code, locale="zh-TW"
                    )
                    if playbook:
                        playbook_name = (
                            playbook.metadata.name
                            if hasattr(playbook.metadata, "name")
                            else playbook_code
                        )
                except Exception:
                    playbook_name = playbook_code
        execution_id = None
        step_index = None
        step_name = None

        if event.payload and isinstance(event.payload, dict):
            execution_id = event.payload.get("execution_id")
            playbook_code = event.payload.get("playbook_code")

            # Determine event type from event_type
            event_type_str = (
                event.event_type.value
                if hasattr(event.event_type, "value")
                else str(event.event_type)
            )
            if event_type_str == "EXECUTION_PLAN":
                # Execution plan events indicate playbook started
                event_type = "playbook_started"
            elif event_type_str == "MESSAGE":
                # Check if it's assistant message (might indicate playbook started)
                actor_str = (
                    event.actor.value
                    if hasattr(event.actor, "value")
                    else str(event.actor)
                )
                if actor_str == "ASSISTANT":
                    event_type = "playbook_started"
            elif "PLAYBOOK_STEP" in event_type_str or "step" in event_type_str.lower():
                event_type = "step_completed"
            elif "ARTIFACT" in event_type_str or "artifact" in event_type_str.lower():
                event_type = "artifact_created"
            elif (
                "CONFIRMATION" in event_type_str
                or "confirmation" in event_type_str.lower()
                or "waiting" in event_type_str.lower()
            ):
                event_type = "confirmation_needed"

            # Try to get playbook name
            if playbook_code:
                try:
                    # Use the registry instance created outside the loop
                    playbook = await playbook_registry.get_playbook(
                        playbook_code, locale="zh-TW"
                    )
                    if playbook:
                        playbook_name = (
                            playbook.metadata.name
                            if hasattr(playbook.metadata, "name")
                            else playbook_code
                        )
                except Exception:
                    playbook_name = playbook_code

            step_index = event.payload.get("step_index")
            step_name = event.payload.get("step_name")

        # Only include events with valid type, and limit metadata size
        if event_type:
            # Limit metadata to essential fields only to avoid huge payloads
            limited_metadata = {}
            if event.payload and isinstance(event.payload, dict):
                # Only include small, essential fields
                for key in [
                    "execution_id",
                    "playbook_code",
                    "step_index",
                    "step_name",
                ]:
                    if key in event.payload:
                        limited_metadata[key] = event.payload[key]

            card_events.append(
                {
                    "id": event.id,
                    "type": event_type,
                    "playbookCode": playbook_code or "",
                    "playbookName": playbook_name or playbook_code or "Unknown",
                    "executionId": execution_id or "",
                    "stepIndex": step_index,
                    "stepName": step_name,
                    "timestamp": (
                        event.timestamp.isoformat()
                        if hasattr(event.timestamp, "isoformat")
                        else str(event.timestamp)
                    ),
                    "metadata": limited_metadata,
                }
            )

    return card_events


def build_project_metadata_and_meeting_summary(
    *,
    workspace_id: str,
    project_id: str,
    project: Project,
) -> dict[str, Any]:
    """Build mind-lens, status, and meeting summary fields for the project card."""
    # Get mind lens info if available
    mind_lens_id = project.metadata.get("mind_lens_id") if project.metadata else None
    mind_lens_name = (
        project.metadata.get("mind_lens_name") if project.metadata else None
    )

    # Map project state to status
    status_map = {"open": "active", "closed": "completed", "archived": "archived"}
    status = status_map.get(project.state, "active")

    # Project-scoped meeting status (persistent governance layer)
    meeting_enabled = bool((project.metadata or {}).get("meeting_enabled", False))
    meeting_store = MeetingSessionStore()
    active_meeting = meeting_store.get_active_session(
        workspace_id=workspace_id,
        project_id=project_id,
    )
    latest_sessions = meeting_store.list_by_workspace(
        workspace_id=workspace_id,
        project_id=project_id,
        limit=5,
        offset=0,
    )
    # Prefer active session; fallback to most recent session with
    # actual progress (round_count > 0) to avoid stale round=0 rows.
    # Extra guard: discard stale active sessions (round_count=0, age > 6h).
    latest_meeting = active_meeting
    if latest_meeting and latest_meeting.round_count == 0:
        age = (
            datetime.now(timezone.utc)
            - latest_meeting.started_at.replace(tzinfo=timezone.utc)
            if latest_meeting.started_at.tzinfo is None
            else datetime.now(timezone.utc) - latest_meeting.started_at
        )
        if age > timedelta(hours=6):
            latest_meeting = None  # stale; fall through to fallback
    if not latest_meeting and latest_sessions:
        for s in latest_sessions:
            if s.round_count > 0:
                latest_meeting = s
                break
        if not latest_meeting:
            latest_meeting = latest_sessions[0]
    meeting_summary = {
        "enabled": meeting_enabled,
        "active": bool(active_meeting and active_meeting.is_active),
        "session_id": latest_meeting.id if latest_meeting else None,
        "status": (
            latest_meeting.status.value
            if latest_meeting and hasattr(latest_meeting.status, "value")
            else (latest_meeting.status if latest_meeting else None)
        ),
        "round_count": latest_meeting.round_count if latest_meeting else 0,
        "max_rounds": latest_meeting.max_rounds if latest_meeting else 5,
        "action_item_count": len(latest_meeting.action_items) if latest_meeting else 0,
        "last_activity": (
            latest_meeting.ended_at.isoformat()
            if latest_meeting and latest_meeting.ended_at
            else (
                latest_meeting.started_at.isoformat()
                if latest_meeting and latest_meeting.started_at
                else None
            )
        ),
        "minutes_preview": (
            (latest_meeting.minutes_md or "").strip()[:180] if latest_meeting else ""
        ),
    }

    return {
        "mind_lens_id": mind_lens_id,
        "mind_lens_name": mind_lens_name,
        "status": status,
        "meeting_summary": meeting_summary,
    }
