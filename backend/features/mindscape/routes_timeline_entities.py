"""Mindscape timeline, entity, and tag route group."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Path, Query

from backend.app.models.mindscape import Entity, Tag
from backend.features.mindscape.route_state import store
from backend.features.mindscape.routes_core import (
    create_entity_record,
    create_tag_record,
    get_entities_by_tag_payload,
    get_entity_payload,
    get_project_timeline_payload,
    get_timeline_payload,
    list_entities_payload,
    list_tags_payload,
    tag_entity_record,
    untag_entity_record,
    update_entity_record,
)

router = APIRouter()


@router.get("/timeline")
async def get_timeline(
    profile_id: str = Query(..., description="Profile ID"),
    start_time: Optional[str] = Query(
        None, description="Start time filter (ISO format)"
    ),
    end_time: Optional[str] = Query(None, description="End time filter (ISO format)"),
    event_types: Optional[str] = Query(None, description="Comma-separated event types"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of events"),
):
    """Get mindspace timeline events"""
    try:
        return get_timeline_payload(
            store=store,
            profile_id=profile_id,
            start_time=start_time,
            end_time=end_time,
            event_types=event_types,
            limit=limit,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get timeline: {str(e)}")


@router.get("/entities", response_model=List[Entity])
async def list_entities(
    profile_id: str = Query(..., description="Profile ID"),
    entity_type: Optional[str] = Query(None, description="Entity type filter"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of entities"),
):
    """Get entities list"""
    try:
        return list_entities_payload(
            store=store,
            profile_id=profile_id,
            entity_type=entity_type,
            limit=limit,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to list entities: {str(e)}"
        )


@router.get("/projects/{project_id}/timeline")
async def get_project_timeline(
    project_id: str = Path(..., description="Project ID"),
    profile_id: Optional[str] = Query(
        None, description="Profile ID (optional, for validation)"
    ),
    start_time: Optional[str] = Query(
        None, description="Start time filter (ISO format)"
    ),
    end_time: Optional[str] = Query(None, description="End time filter (ISO format)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of events"),
):
    """Get timeline for a specific project"""
    try:
        return get_project_timeline_payload(
            store=store,
            project_id=project_id,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get project timeline: {str(e)}"
        )


@router.get("/entities/{entity_id}", response_model=Entity)
async def get_entity(entity_id: str = Path(..., description="Entity ID")):
    """Get a specific entity by ID"""
    try:
        return get_entity_payload(store=store, entity_id=entity_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get entity: {str(e)}")


@router.post("/entities", response_model=Entity, status_code=201)
async def create_entity(entity: Entity = Body(...)):
    """Create a new entity"""
    try:
        return create_entity_record(store=store, entity=entity)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to create entity: {str(e)}"
        )


@router.put("/entities/{entity_id}", response_model=Entity)
async def update_entity(
    entity_id: str = Path(..., description="Entity ID"),
    updates: Dict[str, Any] = Body(...),
):
    """Update an entity"""
    try:
        return update_entity_record(store=store, entity_id=entity_id, updates=updates)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to update entity: {str(e)}"
        )


@router.get("/tags", response_model=List[Tag])
async def list_tags(
    profile_id: str = Query(..., description="Profile ID"),
    category: Optional[str] = Query(None, description="Tag category filter"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of tags"),
):
    """Get tags list"""
    try:
        return list_tags_payload(
            store=store,
            profile_id=profile_id,
            category=category,
            limit=limit,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list tags: {str(e)}")


@router.post("/tags", response_model=Tag, status_code=201)
async def create_tag(tag: Tag = Body(...)):
    """Create a new tag"""
    try:
        return create_tag_record(store=store, tag=tag)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create tag: {str(e)}")


@router.post("/entities/{entity_id}/tags/{tag_id}")
async def tag_entity(
    entity_id: str = Path(..., description="Entity ID"),
    tag_id: str = Path(..., description="Tag ID"),
    value: Optional[str] = Body(None, description="Optional tag value"),
):
    """Tag an entity with a tag"""
    try:
        return tag_entity_record(
            store=store,
            entity_id=entity_id,
            tag_id=tag_id,
            value=value,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to tag entity: {str(e)}")


@router.delete("/entities/{entity_id}/tags/{tag_id}", status_code=204)
async def untag_entity(
    entity_id: str = Path(..., description="Entity ID"),
    tag_id: str = Path(..., description="Tag ID"),
):
    """Remove a tag from an entity"""
    try:
        untag_entity_record(store=store, entity_id=entity_id, tag_id=tag_id)
        return None
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to untag entity: {str(e)}")


@router.get("/tags/{tag_id}/entities", response_model=List[Entity])
async def get_entities_by_tag(
    tag_id: str = Path(..., description="Tag ID"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of entities"),
):
    """Get all entities tagged with a specific tag"""
    try:
        return get_entities_by_tag_payload(store=store, tag_id=tag_id, limit=limit)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get entities by tag: {str(e)}"
        )
