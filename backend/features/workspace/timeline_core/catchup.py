"""Bounded forward keyset catch-up for the workspace lifecycle stream."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, List, Optional


CATCHUP_PAGE_SIZE = 50
MAX_CATCHUP_PAGES = 20


class WorkspaceEventCursorInvalid(ValueError):
    pass


@dataclass(frozen=True)
class WorkspaceEventCatchup:
    events: List[Any]
    page_sizes: List[int]
    last_event_id: str
    truncated: bool


async def load_workspace_event_catchup(
    *,
    store: Any,
    workspace_id: str,
    after_id: Optional[str],
    start_time: Optional[datetime],
) -> WorkspaceEventCatchup:
    cursor = str(after_id or "").strip()
    if cursor:
        cursor_event = await asyncio.to_thread(store.get_event, cursor)
        if cursor_event is None or str(getattr(cursor_event, "workspace_id", "")) != workspace_id:
            raise WorkspaceEventCursorInvalid("workspace_event_cursor_invalid")

    resolved_start = start_time
    if not cursor and resolved_start is None:
        resolved_start = datetime.now(timezone.utc)

    collected: List[Any] = []
    page_sizes: List[int] = []
    for _page_index in range(MAX_CATCHUP_PAGES):
        page = await asyncio.to_thread(
            store.get_events_after_cursor,
            workspace_id,
            after_id=cursor or None,
            start_time=resolved_start if not cursor else None,
            limit=CATCHUP_PAGE_SIZE,
        )
        page = list(page or [])
        page_sizes.append(len(page))
        if not page:
            break
        collected.extend(page)
        cursor = str(getattr(page[-1], "id", "") or cursor)
        resolved_start = None
        if len(page) < CATCHUP_PAGE_SIZE:
            break

    truncated = bool(page_sizes and page_sizes[-1] == CATCHUP_PAGE_SIZE)
    return WorkspaceEventCatchup(
        events=collected,
        page_sizes=page_sizes,
        last_event_id=cursor,
        truncated=truncated,
    )


__all__ = [
    "CATCHUP_PAGE_SIZE",
    "MAX_CATCHUP_PAGES",
    "WorkspaceEventCatchup",
    "WorkspaceEventCursorInvalid",
    "load_workspace_event_catchup",
]
