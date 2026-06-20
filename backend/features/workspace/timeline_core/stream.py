"""Workspace event stream helpers."""

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import AsyncGenerator, List, Optional

from backend.app.models.mindscape import EventType
from backend.app.services.mindscape_store import MindscapeStore
from backend.features.workspace.event_stream_lifecycle import should_stop_event_stream

logger = logging.getLogger("backend.features.workspace.timeline")
HEARTBEAT_INTERVAL = 30


def _event_type_enums(event_types: Optional[List[str]]) -> Optional[list[EventType]]:
    if not event_types:
        return None
    try:
        return [EventType(event_type) for event_type in event_types]
    except ValueError as e:
        logger.warning(f"Invalid event type in filter: {e}")
        return None


async def _last_poll_time_from_resume(
    *,
    workspace_id: str,
    store: MindscapeStore,
    last_event_id: Optional[str],
    default_time: datetime,
    seen_event_ids: set[str],
) -> datetime:
    if not last_event_id:
        return default_time

    resume_events = await asyncio.to_thread(
        store.get_events_by_workspace,
        workspace_id=workspace_id,
        start_time=None,
        limit=1000,
    )
    for event in resume_events:
        if event.id == last_event_id:
            if isinstance(event.timestamp, datetime):
                default_time = event.timestamp
            seen_event_ids.add(event.id)
            break
        seen_event_ids.add(event.id)
    return default_time


async def _open_redis_listener(workspace_id: str):
    try:
        from backend.app.services.cache.async_redis import (
            get_async_redis_client,
            meeting_stream_channel,
        )

        redis_client = await get_async_redis_client()
        if not redis_client:
            return None

        redis_listener = redis_client.pubsub(ignore_subscribe_messages=True)
        await redis_listener.subscribe(meeting_stream_channel(workspace_id))
        logger.info(
            "[SSE] Redis meeting stream subscribed for ws=%s",
            workspace_id[:8],
        )
        return redis_listener
    except Exception as redis_exc:
        logger.warning(
            "[SSE] Redis meeting stream unavailable, degrading to DB-only: %s",
            redis_exc,
        )
        return None


def _serialize_stream_event(event) -> dict:
    payload = event.payload if isinstance(event.payload, dict) else {}
    entity_ids = event.entity_ids if isinstance(event.entity_ids, list) else []
    metadata = event.metadata if isinstance(event.metadata, dict) else {}

    return {
        "id": event.id,
        "type": (
            event.event_type.value
            if hasattr(event.event_type, "value")
            else str(event.event_type)
        ),
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
        "workspace_id": event.workspace_id,
        "project_id": event.project_id,
        "profile_id": event.profile_id,
        "thread_id": getattr(event, "thread_id", None),
        "payload": payload,
        "entity_ids": entity_ids,
        "metadata": metadata,
    }


def _advance_poll_time(current_time: datetime, event_timestamp) -> datetime:
    if not isinstance(event_timestamp, datetime):
        return current_time

    now_utc = datetime.now(timezone.utc)
    event_time = event_timestamp
    if event_time.tzinfo is None:
        event_time = event_time.replace(tzinfo=timezone.utc)
    return min(event_time, now_utc)


async def _drain_redis_listener(redis_listener) -> AsyncGenerator[str, None]:
    try:
        for _ in range(50):
            msg = await redis_listener.get_message(
                ignore_subscribe_messages=True,
                timeout=0.01,
            )
            if not msg:
                break
            raw = msg.get("data")
            if not raw or not isinstance(raw, str):
                continue
            try:
                chunk_data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            chunk_type = chunk_data.get("type", "chunk")
            yield f"event: {chunk_type}\n"
            yield f"data: {json.dumps(chunk_data)}\n\n"
    except Exception as drain_exc:
        logger.warning(
            "[SSE] Redis drain error (non-fatal): %s",
            drain_exc,
        )


async def event_stream_generator(
    workspace_id: str,
    store: MindscapeStore,
    event_types: Optional[List[str]] = None,
    project_id: Optional[str] = None,
    start_time: Optional[datetime] = None,
    last_event_id: Optional[str] = None,
    client_disconnected: Optional[Callable[[], Awaitable[bool]]] = None,
) -> AsyncGenerator[str, None]:
    """
    Generate SSE event stream for unified workspace events.
    """
    redis_listener = None
    try:
        yield f"data: {json.dumps({'type': 'connected', 'workspace_id': workspace_id})}\n\n"

        event_type_enums = _event_type_enums(event_types)
        last_poll_time = start_time or datetime.now(timezone.utc)
        seen_event_ids: set[str] = set()
        last_poll_time = await _last_poll_time_from_resume(
            workspace_id=workspace_id,
            store=store,
            last_event_id=last_event_id,
            default_time=last_poll_time,
            seen_event_ids=seen_event_ids,
        )

        redis_listener = await _open_redis_listener(workspace_id)
        poll_count = 0
        heartbeat_counter = 0

        while True:
            try:
                if await should_stop_event_stream(
                    client_disconnected,
                    logger=logger,
                    workspace_id=workspace_id,
                ):
                    break

                poll_count += 1
                events = await asyncio.to_thread(
                    store.get_events_by_workspace,
                    workspace_id=workspace_id,
                    start_time=last_poll_time,
                    limit=100,
                )

                if poll_count <= 3 or poll_count % 10 == 0:
                    logger.info(
                        f"[SSE-DEBUG] poll#{poll_count} ws={workspace_id[:8]} "
                        f"start_time={last_poll_time} "
                        f"raw_events={len(events)} "
                        f"filter={[e.value for e in event_type_enums] if event_type_enums else 'none'} "
                        f"seen={len(seen_event_ids)}"
                    )

                if event_type_enums:
                    events = [event for event in events if event.event_type in event_type_enums]
                if project_id:
                    events = [event for event in events if event.project_id == project_id]

                new_events = [event for event in events if event.id not in seen_event_ids]
                if new_events:
                    logger.info(
                        f"[SSE-DEBUG] poll#{poll_count} FOUND {len(new_events)} new events! "
                        f"types={[event.event_type.value for event in new_events]}"
                    )

                new_events.sort(
                    key=lambda event: (
                        event.timestamp
                        if isinstance(event.timestamp, datetime)
                        else datetime.min.replace(tzinfo=timezone.utc)
                    )
                )

                for event in new_events:
                    seen_event_ids.add(event.id)
                    event_data = _serialize_stream_event(event)
                    logger.info(
                        f"[SSE-DEBUG] YIELDING event {event.id[:8]} type={event_data['type']}"
                    )
                    yield f"id: {event.id}\n"
                    yield f"event: {event_data['type']}\n"
                    yield f"data: {json.dumps(event_data)}\n\n"
                    last_poll_time = _advance_poll_time(last_poll_time, event.timestamp)

                if redis_listener:
                    async for chunk in _drain_redis_listener(redis_listener):
                        yield chunk

                heartbeat_counter += 1
                if heartbeat_counter >= HEARTBEAT_INTERVAL:
                    yield f": heartbeat\n\n"
                    heartbeat_counter = 0

                await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"Error in event stream: {e}", exc_info=True)
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
                await asyncio.sleep(5)

    except Exception as e:
        logger.error(f"Fatal error in event stream: {e}", exc_info=True)
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
    finally:
        if redis_listener:
            try:
                await redis_listener.unsubscribe()
                await redis_listener.close()
            except Exception:
                pass
