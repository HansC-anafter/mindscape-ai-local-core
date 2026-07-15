"""Single Redis-primary workspace lifecycle SSE coordinator."""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import AsyncGenerator, Dict, List, Optional, Set, Tuple

from backend.app.models.mindscape import EventType
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.workspace_event_lifecycle import (
    serialize_mind_event_cloud_event,
    validate_workspace_lifecycle_event,
)
from backend.features.workspace.event_stream_lifecycle import should_stop_event_stream
from backend.features.workspace.timeline_core.catchup import (
    WorkspaceEventCatchup,
    WorkspaceEventCursorInvalid,
    load_workspace_event_catchup,
)
from backend.features.workspace.timeline_core.subscription import (
    WorkspaceEventStreamUnavailable,
    WorkspaceEventSubscription,
)


logger = logging.getLogger("backend.features.workspace.timeline")
HEARTBEAT_INTERVAL = 15
SSE_RETRY_MILLISECONDS = 15_000


def _event_type_values(event_types: Optional[List[str]]) -> Optional[Set[str]]:
    if not event_types:
        return None
    try:
        return {EventType(event_type).value for event_type in event_types}
    except ValueError as exc:
        logger.warning("Invalid workspace event stream filter: %s", exc)
        return None


def _event_key(event: Dict) -> Tuple[str, str]:
    return (str(event.get("source") or ""), str(event.get("id") or ""))


def _matches_filters(
    event: Dict,
    *,
    event_types: Optional[Set[str]],
    project_id: Optional[str],
) -> bool:
    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    if event_types and str(data.get("event_type") or "") not in event_types:
        return False
    if project_id and str(data.get("project_id") or "") != project_id:
        return False
    return True


def _sse_event(event: Dict) -> str:
    return (
        f"id: {event['id']}\n"
        f"event: {event['type']}\n"
        f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"
    )


def _record_aggregate_version(event: Dict, versions: Dict[str, int]) -> bool:
    aggregate_id = str(event.get("aggregateid") or "")
    try:
        aggregate_version = int(event.get("aggregateversion") or 0)
    except (TypeError, ValueError):
        return False
    if not aggregate_id or aggregate_version <= 0:
        return False
    previous = versions.get(aggregate_id)
    versions[aggregate_id] = max(previous or 0, aggregate_version)
    return previous is not None and aggregate_version > previous + 1


async def _catchup(
    *,
    store: MindscapeStore,
    workspace_id: str,
    after_id: Optional[str],
    start_time: Optional[datetime],
    subscription: WorkspaceEventSubscription,
) -> tuple[WorkspaceEventCatchup, bool]:
    cursor_reset = False
    try:
        result = await load_workspace_event_catchup(
            store=store,
            workspace_id=workspace_id,
            after_id=after_id,
            start_time=start_time,
        )
    except WorkspaceEventCursorInvalid:
        cursor_reset = True
        result = await load_workspace_event_catchup(
            store=store,
            workspace_id=workspace_id,
            after_id=None,
            start_time=start_time or subscription.subscribed_at,
        )
    return result, cursor_reset


async def event_stream_generator(
    workspace_id: str,
    store: MindscapeStore,
    subscription: WorkspaceEventSubscription,
    event_types: Optional[List[str]] = None,
    project_id: Optional[str] = None,
    start_time: Optional[datetime] = None,
    last_event_id: Optional[str] = None,
    client_disconnected: Optional[Callable[[], Awaitable[bool]]] = None,
) -> AsyncGenerator[str, None]:
    """Subscribe first, catch up once, then deliver Redis events without DB polling."""
    seen: Set[Tuple[str, str]] = set()
    aggregate_versions: Dict[str, int] = {}
    filter_values = _event_type_values(event_types)
    durable_cursor = str(last_event_id or "").strip() or None
    initial_start = start_time or subscription.subscribed_at
    try:
        yield (
            f"retry: {SSE_RETRY_MILLISECONDS}\n"
            "event: connected\n"
            f"data: {json.dumps({'type': 'connected', 'workspace_id': workspace_id})}\n\n"
        )
        if await should_stop_event_stream(
            client_disconnected,
            logger=logger,
            workspace_id=workspace_id,
        ):
            return

        catchup, cursor_reset = await _catchup(
            store=store,
            workspace_id=workspace_id,
            after_id=durable_cursor,
            start_time=initial_start,
            subscription=subscription,
        )
        if cursor_reset:
            yield (
                "event: cursor_reset\n"
                f"data: {json.dumps({'type': 'cursor_reset', 'reason': 'invalid_last_event_id'})}\n\n"
            )
        for mind_event in catchup.events:
            event = validate_workspace_lifecycle_event(
                serialize_mind_event_cloud_event(mind_event),
                workspace_id=workspace_id,
            )
            durable_cursor = str(event["id"])
            seen.add(_event_key(event))
            _record_aggregate_version(event, aggregate_versions)
            if _matches_filters(
                event,
                event_types=filter_values,
                project_id=project_id,
            ):
                yield _sse_event(event)
        if catchup.truncated:
            yield (
                "event: catchup_truncated\n"
                f"data: {json.dumps({'type': 'catchup_truncated', 'retry': True})}\n\n"
            )
            return

        while True:
            if await should_stop_event_stream(
                client_disconnected,
                logger=logger,
                workspace_id=workspace_id,
            ):
                return
            try:
                raw_event = await subscription.next_payload(
                    timeout_seconds=HEARTBEAT_INTERVAL
                )
            except WorkspaceEventStreamUnavailable as exc:
                logger.warning("Workspace event Redis subscription ended: %s", exc)
                yield (
                    "event: stream_unavailable\n"
                    f"data: {json.dumps({'type': 'stream_unavailable', 'retry': True})}\n\n"
                )
                return
            if raw_event is None:
                yield ": heartbeat\n\n"
                continue

            try:
                event = validate_workspace_lifecycle_event(
                    raw_event,
                    workspace_id=workspace_id,
                )
            except ValueError as exc:
                logger.warning("Invalid workspace lifecycle event: %s", exc)
                gap, _cursor_reset = await _catchup(
                    store=store,
                    workspace_id=workspace_id,
                    after_id=durable_cursor,
                    start_time=initial_start,
                    subscription=subscription,
                )
                for mind_event in gap.events:
                    recovered = validate_workspace_lifecycle_event(
                        serialize_mind_event_cloud_event(mind_event),
                        workspace_id=workspace_id,
                    )
                    durable_cursor = str(recovered["id"])
                    if _event_key(recovered) in seen:
                        continue
                    seen.add(_event_key(recovered))
                    _record_aggregate_version(recovered, aggregate_versions)
                    if _matches_filters(
                        recovered,
                        event_types=filter_values,
                        project_id=project_id,
                    ):
                        yield _sse_event(recovered)
                continue

            if _event_key(event) in seen:
                continue
            if _record_aggregate_version(event, aggregate_versions):
                gap, _cursor_reset = await _catchup(
                    store=store,
                    workspace_id=workspace_id,
                    after_id=durable_cursor,
                    start_time=initial_start,
                    subscription=subscription,
                )
                for mind_event in gap.events:
                    recovered = validate_workspace_lifecycle_event(
                        serialize_mind_event_cloud_event(mind_event),
                        workspace_id=workspace_id,
                    )
                    durable_cursor = str(recovered["id"])
                    if _event_key(recovered) in seen:
                        continue
                    seen.add(_event_key(recovered))
                    _record_aggregate_version(recovered, aggregate_versions)
                    if _matches_filters(
                        recovered,
                        event_types=filter_values,
                        project_id=project_id,
                    ):
                        yield _sse_event(recovered)
                if _event_key(event) in seen:
                    continue
            durable_cursor = str(event["id"])
            seen.add(_event_key(event))
            if _matches_filters(
                event,
                event_types=filter_values,
                project_id=project_id,
            ):
                yield _sse_event(event)
    finally:
        await subscription.close()


__all__ = ["HEARTBEAT_INTERVAL", "event_stream_generator"]
