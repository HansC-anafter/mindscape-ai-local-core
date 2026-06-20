"""Workspace timeline item helpers."""

import asyncio
import logging
import sys
import traceback
from datetime import datetime
from typing import Optional

from fastapi import HTTPException

from backend.app.routes.workspace_schemas import TimelineListResponse
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.stores.tasks_store import TasksStore
from backend.app.services.stores.timeline_items_store import TimelineItemsStore

logger = logging.getLogger("backend.features.workspace.timeline")


def _parse_time_filter(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _timeline_item_type(item) -> str:
    return item.type.value if hasattr(item.type, "value") else str(item.type)


def _serialize_timeline_item(item) -> dict:
    return {
        "id": item.id,
        "workspace_id": item.workspace_id,
        "message_id": item.message_id,
        "task_id": item.task_id,
        "type": _timeline_item_type(item),
        "title": item.title,
        "summary": item.summary,
        "data": item.data,
        "cta": item.cta,
        "created_at": (
            (
                item.created_at.isoformat() + "Z"
                if item.created_at.tzinfo is None
                else item.created_at.isoformat()
            )
            if item.created_at
            else None
        ),
    }


def _filter_timeline_items(
    *,
    timeline_items: list,
    start_time: Optional[str],
    end_time: Optional[str],
    event_types: Optional[str],
) -> list:
    start = _parse_time_filter(start_time)
    end = _parse_time_filter(end_time)

    if start or end:
        filtered_items = []
        for item in timeline_items:
            item_time = item.created_at
            if start and item_time < start:
                continue
            if end and item_time > end:
                continue
            filtered_items.append(item)
        timeline_items = filtered_items

    if event_types:
        type_list = [t.strip() for t in event_types.split(",")]
        timeline_items = [
            item for item in timeline_items if _timeline_item_type(item) in type_list
        ]

    return timeline_items


async def _enrich_timeline_item(item, tasks_store: TasksStore) -> dict:
    enriched = _serialize_timeline_item(item)
    if not item.task_id:
        enriched["has_execution_context"] = False
        return enriched

    try:
        task = await asyncio.to_thread(tasks_store.get_task, item.task_id)
        if task and task.execution_context:
            enriched["execution_id"] = task.execution_id or task.id
            enriched["task_status"] = task.status.value if task.status else None
            enriched["task_started_at"] = (
                task.started_at.isoformat() if task.started_at else None
            )
            enriched["task_completed_at"] = (
                task.completed_at.isoformat() if task.completed_at else None
            )
            enriched["has_execution_context"] = True
        else:
            enriched["has_execution_context"] = False
    except Exception as e:
        logger.warning(
            f"Failed to load task {item.task_id} for timeline item {item.id}: {e}"
        )
        enriched["has_execution_context"] = False
    return enriched


async def build_workspace_timeline_response(
    *,
    workspace_id: str,
    start_time: Optional[str],
    end_time: Optional[str],
    event_types: Optional[str],
    limit: int,
    timeline_items_store: TimelineItemsStore,
    store: MindscapeStore,
) -> TimelineListResponse:
    try:
        timeline_items = await asyncio.to_thread(
            timeline_items_store.list_timeline_items_by_workspace,
            workspace_id=workspace_id,
            limit=limit,
        )

        timeline_items = _filter_timeline_items(
            timeline_items=timeline_items,
            start_time=start_time,
            end_time=end_time,
            event_types=event_types,
        )

        tasks_store = TasksStore(db_path=store.db_path)
        enriched_items = [
            await _enrich_timeline_item(item, tasks_store) for item in timeline_items
        ]

        logger.info(
            f"Returning {len(enriched_items)} timeline items for workspace {workspace_id}"
        )

        return TimelineListResponse(
            workspace_id=workspace_id,
            total=len(enriched_items),
            timeline_items=enriched_items,
            events=enriched_items,
        )
    except HTTPException:
        raise
    except Exception as e:
        full_traceback = "".join(traceback.format_exception(*sys.exc_info()))
        logger.error(f"Timeline error: {str(e)}\n{full_traceback}")
        print(f"ERROR: Timeline error: {str(e)}", file=sys.stderr)
        print(full_traceback, file=sys.stderr)
        raise
