#!/usr/bin/env python3
"""
Meeting E2E smoke test for PipelineCore(meeting mode).

Verifies:
- Meeting session lifecycle (created -> closed)
- Replayable meeting events exist
- Minutes and action items are produced
"""

import argparse
import asyncio
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Set

from sqlalchemy import text

# Allow running via: python backend/scripts/test_meeting_e2e.py
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from backend.app.models.mindscape import EventActor, EventType, MindEvent
from backend.app.models.workspace import ConversationThread
from backend.app.services.conversation.pipeline_core import PipelineCore
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.stores.meeting_session_store import MeetingSessionStore
from backend.app.services.stores.workspace_runtime_profile_store import (
    WorkspaceRuntimeProfileStore,
)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _event_type_value(value) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _must(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _first_id(store: MindscapeStore, table: str, workspace_id: Optional[str] = None) -> Optional[str]:
    with store.get_connection() as conn:
        if workspace_id:
            row = conn.execute(
                text(f"SELECT id FROM {table} WHERE workspace_id = :workspace_id ORDER BY created_at DESC NULLS LAST LIMIT 1"),
                {"workspace_id": workspace_id},
            ).fetchone()
        else:
            row = conn.execute(
                text(f"SELECT id FROM {table} ORDER BY created_at DESC NULLS LAST LIMIT 1")
            ).fetchone()
    if not row:
        return None
    return str(row[0] if not hasattr(row, "_mapping") else row._mapping["id"])


async def _resolve_workspace_id(store: MindscapeStore, workspace_id: Optional[str]) -> str:
    if workspace_id:
        return workspace_id
    detected = _first_id(store, "workspaces")
    _must(bool(detected), "No workspace found. Provide --workspace-id.")
    return detected


async def _resolve_profile_id(store: MindscapeStore, profile_id: Optional[str]) -> str:
    candidate = profile_id or "default-user"
    if store.get_profile(candidate):
        return candidate
    detected = _first_id(store, "profiles")
    _must(bool(detected), "No profile found. Provide --profile-id.")
    return detected


def _ensure_thread(store: MindscapeStore, workspace_id: str, thread_id: Optional[str]) -> str:
    if thread_id:
        return thread_id

    default_thread = store.conversation_threads.get_default_thread(workspace_id)
    if default_thread:
        return default_thread.id

    existing = store.conversation_threads.list_threads_by_workspace(workspace_id, limit=1)
    if existing:
        return existing[0].id

    new_thread = ConversationThread(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        title="Meeting E2E Thread",
        project_id=None,
        created_at=_now_utc(),
        updated_at=_now_utc(),
        last_message_at=_now_utc(),
        message_count=0,
        metadata={"source": "meeting_e2e"},
        is_default=True,
    )
    store.conversation_threads.create_thread(new_thread)
    return new_thread.id


async def run(args: argparse.Namespace) -> int:
    store = MindscapeStore()
    workspace_id = await _resolve_workspace_id(store, args.workspace_id)
    profile_id = await _resolve_profile_id(store, args.profile_id)
    thread_id = _ensure_thread(store, workspace_id, args.thread_id)

    workspace = await store.get_workspace(workspace_id)
    _must(workspace is not None, f"Workspace not found: {workspace_id}")

    profile = store.get_profile(profile_id)
    _must(profile is not None, f"Profile not found: {profile_id}")

    runtime_store = WorkspaceRuntimeProfileStore(db_path=store.db_path)
    runtime_profile = await runtime_store.get_runtime_profile(workspace_id)
    if not runtime_profile:
        runtime_profile = await runtime_store.create_default_profile(workspace_id)

    # Keep project optional for meeting mode.
    project_id = args.project_id
    if not project_id and getattr(workspace, "primary_project_id", None):
        project_id = workspace.primary_project_id

    user_event = MindEvent(
        id=str(uuid.uuid4()),
        timestamp=_now_utc(),
        actor=EventActor.USER,
        channel="local_workspace",
        profile_id=profile_id,
        project_id=project_id,
        workspace_id=workspace_id,
        thread_id=thread_id,
        event_type=EventType.MESSAGE,
        payload={"message": args.message, "mode": "meeting"},
        entity_ids=[],
        metadata={"e2e_test": True},
    )
    store.create_event(user_event)

    pipeline = PipelineCore(
        orchestrator_store=store,
        workspace=workspace,
        profile=profile,
        runtime_profile=runtime_profile,
    )
    result = await pipeline.process(
        workspace_id=workspace_id,
        profile_id=profile_id,
        thread_id=thread_id,
        project_id=project_id,
        message=args.message,
        user_event_id=user_event.id,
        execution_mode="meeting",
        model_name=args.model_name,
        request=None,
    )

    _must(result.success, f"PipelineCore failed: {result.error}")
    _must(bool(result.meeting_session_id), "meeting_session_id missing in PipelineResult")
    _must(bool(result.response_text.strip()), "Meeting minutes are empty")

    session_store = MeetingSessionStore()
    session = session_store.get_by_id(result.meeting_session_id)
    _must(session is not None, "MeetingSession not found after run")
    _must(session.status.value == "closed", f"Session not closed: {session.status}")
    _must(session.round_count >= 1, "round_count should be >= 1")
    _must(bool(session.minutes_md.strip()), "Session.minutes_md is empty")
    _must(len(session.action_items) >= 1, "No action_items in session")

    events = store.get_events_by_meeting_session(
        meeting_session_id=result.meeting_session_id,
        workspace_id=workspace_id,
        limit=args.max_events,
    )
    _must(len(events) > 0, "No meeting events found for session")

    event_types: Set[str] = {_event_type_value(e.event_type) for e in events}
    required = {
        EventType.MEETING_START.value,
        EventType.MEETING_ROUND.value,
        EventType.AGENT_TURN.value,
        EventType.DECISION_FINAL.value,
        EventType.ACTION_ITEM.value,
        EventType.MEETING_END.value,
        EventType.MESSAGE.value,
    }
    missing = sorted(required - event_types)
    _must(not missing, f"Missing event types: {missing}")

    has_minutes_message = any(
        _event_type_value(e.event_type) == EventType.MESSAGE.value
        and bool((e.payload or {}).get("is_meeting_minutes"))
        for e in events
    )
    _must(has_minutes_message, "Meeting minutes MESSAGE event missing")

    print("Meeting E2E validation passed")
    print(f"- workspace_id: {workspace_id}")
    print(f"- profile_id: {profile_id}")
    print(f"- thread_id: {thread_id}")
    print(f"- meeting_session_id: {result.meeting_session_id}")
    print(f"- round_count: {session.round_count}")
    print(f"- action_items: {len(session.action_items)}")
    print(f"- replay_events: {len(events)}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Meeting pipeline E2E validator")
    parser.add_argument("--workspace-id", help="Workspace ID to run against")
    parser.add_argument("--profile-id", help="Profile ID (default: default-user)")
    parser.add_argument("--thread-id", help="Thread ID (auto-create if absent)")
    parser.add_argument("--project-id", help="Project ID (optional)")
    parser.add_argument(
        "--message",
        default="請做一次落地導向會議，包含決策、風險、可執行 action items。",
        help="Meeting user message",
    )
    parser.add_argument("--model-name", help="Override model name")
    parser.add_argument("--max-events", type=int, default=500, help="Replay fetch limit")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        return asyncio.run(run(args))
    except Exception as exc:
        print(f"Meeting E2E validation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
