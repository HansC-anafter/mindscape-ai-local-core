"""Projection helpers for MindEvent store rows."""

from __future__ import annotations

import traceback
from typing import Any, Callable, Iterable, List

from backend.app.models.mindscape import EventActor, EventType, MindEvent

DeserializeJson = Callable[[Any, Any], Any]
FromIsoformat = Callable[[Any], Any]
RowToEvent = Callable[[Any], MindEvent]


def _row_text_value(row: Any, key: str, logger: Any) -> Any:
    try:
        return row[key]
    except KeyError as exc:
        logger.error(
            "Missing column in row: %s, available columns: %s",
            exc,
            row.keys() if hasattr(row, "keys") else "unknown",
        )
        raise


def _drop_sqlite_row_values(value: Any) -> Any:
    if not isinstance(value, dict):
        return {}
    cleaned = {}
    for key, item in value.items():
        if hasattr(item, "__class__"):
            class_name = item.__class__.__name__
            module_name = getattr(item.__class__, "__module__", "")
            if class_name == "Row" or "sqlite3" in module_name:
                continue
        if isinstance(item, dict):
            item = _drop_sqlite_row_values(item)
        cleaned[key] = item
    return cleaned


def _json_column(row: Any, key: str, *, logger: Any) -> Any:
    value = _row_text_value(row, key, logger)
    if hasattr(value, "__class__") and value.__class__.__name__ == "Row":
        logger.error(
            "%s is sqlite3.Row object. Row keys: %s",
            key,
            value.keys() if hasattr(value, "keys") else "unknown",
        )
        return None
    return str(value) if value is not None else None


def row_to_event(
    row: Any,
    *,
    deserialize_json: DeserializeJson,
    from_isoformat: FromIsoformat,
    logger: Any,
) -> MindEvent:
    payload = deserialize_json(_json_column(row, "payload", logger=logger), {})
    entity_ids = deserialize_json(_json_column(row, "entity_ids", logger=logger), [])
    metadata = deserialize_json(_json_column(row, "metadata", logger=logger), {})

    if not isinstance(payload, dict):
        logger.warning(
            "deserialize_json returned non-dict payload: type=%s, value=%s",
            type(payload),
            payload,
        )
        payload = {}
    else:
        payload = _drop_sqlite_row_values(payload)

    if not isinstance(entity_ids, list):
        entity_ids = []

    if not isinstance(metadata, dict):
        metadata = {}
    else:
        metadata = _drop_sqlite_row_values(metadata)

    try:
        row_keys = row.keys() if hasattr(row, "keys") else []
        return MindEvent(
            id=str(row["id"]),
            timestamp=from_isoformat(row["timestamp"]),
            actor=EventActor(row["actor"]),
            channel=str(row["channel"]),
            profile_id=str(row["profile_id"]),
            project_id=str(row["project_id"]) if row["project_id"] else None,
            workspace_id=str(row["workspace_id"]) if row["workspace_id"] else None,
            thread_id=str(row["thread_id"])
            if "thread_id" in row_keys and row["thread_id"]
            else None,
            event_type=EventType(row["event_type"]),
            payload=payload,
            entity_ids=entity_ids,
            metadata=metadata,
        )
    except Exception as exc:
        logger.error("Error creating MindEvent: %s", exc)
        logger.error("Payload type: %s, Payload: %s", type(payload), payload)
        logger.error("Entity IDs type: %s, Entity IDs: %s", type(entity_ids), entity_ids)
        logger.error("Metadata type: %s, Metadata: %s", type(metadata), metadata)
        logger.error(traceback.format_exc())
        raise


def rows_to_events(
    rows: Iterable[Any],
    *,
    row_to_event: RowToEvent,
    context: str,
    logger: Any,
) -> List[MindEvent]:
    events = []
    for index, row in enumerate(rows):
        try:
            events.append(row_to_event(row))
        except Exception as exc:
            logger.error("Error converting row %s %s: %s", index, context, exc)
            logger.error(traceback.format_exc())
            continue
    return events
