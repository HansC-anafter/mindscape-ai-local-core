"""Workspace event list helpers."""

import asyncio
import logging
import traceback
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException

from backend.app.models.mindscape import EventActor, EventType, MindEvent
from backend.app.models.workspace import Workspace
from backend.app.routes.workspace_schemas import EventsListResponse
from backend.app.services.mindscape_store import MindscapeStore

logger = logging.getLogger("backend.features.workspace.timeline")


def serialize_event(event) -> dict:
    payload = event.payload if isinstance(event.payload, dict) else {}
    entity_ids = event.entity_ids if isinstance(event.entity_ids, list) else []
    metadata = event.metadata if isinstance(event.metadata, dict) else {}

    return {
        "id": event.id,
        "timestamp": (
            (
                event.timestamp.isoformat() + "Z"
                if event.timestamp.tzinfo is None
                else event.timestamp.isoformat()
            )
            if event.timestamp
            else None
        ),
        "actor": event.actor.value if hasattr(event.actor, "value") else str(event.actor),
        "channel": event.channel,
        "profile_id": event.profile_id,
        "project_id": event.project_id,
        "workspace_id": event.workspace_id,
        "thread_id": event.thread_id,
        "event_type": (
            event.event_type.value
            if hasattr(event.event_type, "value")
            else str(event.event_type)
        ),
        "payload": payload,
        "entity_ids": entity_ids,
        "metadata": metadata,
    }


async def _load_events(
    *,
    workspace_id: str,
    store: MindscapeStore,
    thread_id: Optional[str],
    start_dt: Optional[datetime],
    end_dt: Optional[datetime],
    limit: int,
    before_id: Optional[str],
):
    if thread_id:
        return await asyncio.to_thread(
            store.events.get_events_by_thread,
            workspace_id=workspace_id,
            thread_id=thread_id,
            start_time=start_dt,
            end_time=end_dt,
            limit=limit,
            before_id=before_id,
        )

    return await asyncio.to_thread(
        store.get_events_by_workspace,
        workspace_id=workspace_id,
        start_time=start_dt,
        end_time=end_dt,
        limit=limit,
        before_id=before_id,
    )


def _event_type_value(event) -> str:
    return (
        event.event_type.value
        if hasattr(event.event_type, "value")
        else str(event.event_type)
    )


def _has_welcome_event(events) -> bool:
    for event in events:
        payload = event.payload if isinstance(event.payload, dict) else {}
        metadata = event.metadata if isinstance(event.metadata, dict) else {}
        if payload.get("is_welcome") or metadata.get("is_cold_start"):
            return True
    return False


async def _create_welcome_event_if_needed(
    *,
    workspace_id: str,
    thread_id: Optional[str],
    workspace: Workspace,
    store: MindscapeStore,
) -> None:
    try:
        from backend.app.services.workspace_welcome_service import (
            WorkspaceWelcomeService,
        )
        from backend.features.workspace.chat.streaming.generator import (
            _get_or_create_default_thread,
        )

        locale = (
            workspace.default_locale
            if hasattr(workspace, "default_locale") and workspace.default_locale
            else "zh-TW"
        )
        welcome_message, suggestions = await WorkspaceWelcomeService.generate_welcome_message(
            workspace, workspace.owner_user_id, store, locale=locale
        )
        if not welcome_message:
            return

        target_thread_id = thread_id
        if not target_thread_id:
            target_thread_id = _get_or_create_default_thread(workspace_id, store)

        welcome_event = MindEvent(
            id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc),
            actor=EventActor.ASSISTANT,
            channel="local_workspace",
            profile_id=workspace.owner_user_id,
            project_id=workspace.primary_project_id,
            workspace_id=workspace_id,
            thread_id=target_thread_id,
            event_type=EventType.MESSAGE,
            payload={
                "message": welcome_message,
                "is_welcome": True,
                "suggestions": suggestions,
            },
            entity_ids=[],
            metadata={"is_cold_start": True},
        )
        await asyncio.to_thread(store.create_event, welcome_event)

        try:
            message_count = await asyncio.to_thread(
                store.events.count_messages_by_thread,
                workspace_id=workspace_id,
                thread_id=target_thread_id,
            )
            await asyncio.to_thread(
                store.conversation_threads.update_thread,
                thread_id=target_thread_id,
                last_message_at=datetime.now(timezone.utc),
                message_count=message_count,
            )
        except Exception as e:
            logger.warning(
                f"Failed to update thread statistics for welcome message: {e}"
            )

        logger.info(
            f"Generated cold start welcome message for workspace {workspace_id}"
        )
    except Exception as e:
        logger.warning(
            f"Failed to generate welcome message for workspace {workspace_id}: {e}"
        )


async def build_workspace_events_response(
    *,
    workspace_id: str,
    thread_id: Optional[str],
    start_time: Optional[str],
    end_time: Optional[str],
    event_types: Optional[str],
    limit: int,
    before_id: Optional[str],
    workspace: Workspace,
    store: MindscapeStore,
) -> EventsListResponse:
    try:
        start_dt = datetime.fromisoformat(start_time) if start_time else None
        end_dt = datetime.fromisoformat(end_time) if end_time else None

        recent_events = await _load_events(
            workspace_id=workspace_id,
            store=store,
            thread_id=thread_id,
            start_dt=start_dt,
            end_dt=end_dt,
            limit=limit,
            before_id=before_id,
        )

        if not before_id and not event_types and not _has_welcome_event(recent_events):
            await _create_welcome_event_if_needed(
                workspace_id=workspace_id,
                thread_id=thread_id,
                workspace=workspace,
                store=store,
            )
            recent_events = await _load_events(
                workspace_id=workspace_id,
                store=store,
                thread_id=thread_id,
                start_dt=start_dt,
                end_dt=end_dt,
                limit=limit,
                before_id=before_id,
            )

        if event_types:
            type_list = [t.strip() for t in event_types.split(",")]
            recent_events = [
                event for event in recent_events if _event_type_value(event) in type_list
            ]

        display_events_dicts = [serialize_event(event) for event in recent_events]
        has_more = len(recent_events) >= limit and len(display_events_dicts) >= limit

        return EventsListResponse(
            workspace_id=workspace_id,
            total=len(display_events_dicts),
            events=display_events_dicts,
            has_more=has_more,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to get workspace events: {str(e)}\n{traceback.format_exc()}"
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to get workspace events: {str(e)}"
        )
