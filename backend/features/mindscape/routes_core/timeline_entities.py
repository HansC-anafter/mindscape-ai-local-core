"""Timeline, entity, and tag helpers for mindscape routes."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import HTTPException

from backend.app.models.mindscape import EntityType, EventType, TagCategory


def _entity_to_dict(entity, store) -> dict[str, Any]:
    """Serialize an entity and attach its tags."""
    entity_dict = entity.dict()
    tags = store.get_tags_by_entity(entity.id)
    entity_dict["tags"] = [tag.dict() for tag in tags]
    return entity_dict


def _enrich_events(events, store) -> list[dict[str, Any]]:
    """Attach entity payloads to timeline events."""
    enriched_events: list[dict[str, Any]] = []
    for event in events:
        enriched = event.dict()
        if not event.entity_ids:
            enriched["entities"] = []
            enriched_events.append(enriched)
            continue

        entities = []
        for entity_id in event.entity_ids:
            entity = store.get_entity(entity_id)
            if entity:
                entities.append(_entity_to_dict(entity, store))
        enriched["entities"] = entities
        enriched_events.append(enriched)
    return enriched_events


def _parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO datetime value when present."""
    return datetime.fromisoformat(value) if value else None


def _parse_event_types(event_types: Optional[str]):
    """Parse comma-separated event type filters into enums."""
    if not event_types:
        return None
    return [EventType(raw.strip()) for raw in event_types.split(",")]


def get_timeline_payload(
    *,
    store,
    profile_id: str,
    start_time: Optional[str],
    end_time: Optional[str],
    event_types: Optional[str],
    limit: int,
) -> dict[str, Any]:
    """Build the response payload for the profile timeline route."""
    events = store.get_timeline(
        profile_id=profile_id,
        start_time=_parse_iso_datetime(start_time),
        end_time=_parse_iso_datetime(end_time),
        event_types=_parse_event_types(event_types),
        limit=limit,
    )
    enriched_events = _enrich_events(events, store)
    return {
        "profile_id": profile_id,
        "total": len(enriched_events),
        "events": enriched_events,
    }


def list_entities_payload(
    *,
    store,
    profile_id: str,
    entity_type: Optional[str],
    limit: int,
) -> list[dict[str, Any]]:
    """Build the response payload for the entity list route."""
    entity_type_enum = EntityType(entity_type) if entity_type else None
    entities = store.list_entities(
        profile_id=profile_id,
        entity_type=entity_type_enum,
        limit=limit,
    )
    return [_entity_to_dict(entity, store) for entity in entities]


def get_project_timeline_payload(
    *,
    store,
    project_id: str,
    start_time: Optional[str],
    end_time: Optional[str],
    limit: int,
) -> dict[str, Any]:
    """Build the response payload for the project timeline route."""
    events = store.get_events_by_project(
        project_id=project_id,
        start_time=_parse_iso_datetime(start_time),
        end_time=_parse_iso_datetime(end_time),
        limit=limit,
    )
    enriched_events = _enrich_events(events, store)
    return {
        "project_id": project_id,
        "total": len(enriched_events),
        "events": enriched_events,
    }


def get_entity_payload(*, store, entity_id: str) -> dict[str, Any]:
    """Return one enriched entity or raise not found."""
    entity = store.get_entity(entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    return _entity_to_dict(entity, store)


def create_entity_record(*, store, entity):
    """Create and return a new entity."""
    return store.create_entity(entity)


def update_entity_record(*, store, entity_id: str, updates: dict[str, Any]):
    """Update an entity or raise not found."""
    updated = store.update_entity(entity_id, updates)
    if not updated:
        raise HTTPException(status_code=404, detail="Entity not found")
    return updated


def list_tags_payload(
    *,
    store,
    profile_id: str,
    category: Optional[str],
    limit: int,
):
    """Return tags filtered by optional category."""
    category_enum = TagCategory(category) if category else None
    return store.list_tags(
        profile_id=profile_id,
        category=category_enum,
        limit=limit,
    )


def create_tag_record(*, store, tag):
    """Create and return a new tag."""
    return store.create_tag(tag)


def tag_entity_record(*, store, entity_id: str, tag_id: str, value: Optional[str]):
    """Create and return an entity-tag relation."""
    return store.tag_entity(entity_id, tag_id, value)


def untag_entity_record(*, store, entity_id: str, tag_id: str) -> None:
    """Delete an entity-tag relation or raise not found."""
    removed = store.untag_entity(entity_id, tag_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Entity-tag association not found")


def get_entities_by_tag_payload(*, store, tag_id: str, limit: int):
    """Return entities associated with a tag."""
    return store.get_entities_by_tag(tag_id, limit=limit)
