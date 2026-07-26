"""Mindscape profile, intent, and intent-playbook route group."""

import asyncio
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from backend.app.dependencies.auth import AuthContext, get_current_identity
from backend.app.models.mindscape import (
    CreateIntentRequest,
    CreateProfileRequest,
    EventActor,
    EventType,
    IntentCard,
    IntentStatus,
    MindEvent,
    MindscapeProfile,
    PriorityLevel,
    UpdateIntentRequest,
    UpdateProfileRequest,
)
from backend.app.services.profile_preferences import (
    ProfilePreferencesConflictError,
    ProfilePreferencesMutationService,
    ProfilePreferencesNotFoundError,
    ProfilePreferencesPatchRequest,
    ProfileUiLanguageProjection,
    ProfileUiLanguageProjectionService,
)
from backend.features.mindscape.route_state import logger, store
from backend.features.mindscape.routes_core import (
    archive_intent,
    associate_intent_playbook_payload,
    create_profile_record,
    get_intent_or_404,
    get_intent_playbooks_payload,
    get_profile_or_404,
    list_intents_payload,
    remove_intent_playbook_payload,
    update_profile_record,
)

router = APIRouter()
profile_ui_language_projection_service = ProfileUiLanguageProjectionService()
profile_preferences_mutation_service = ProfilePreferencesMutationService()


@router.post("/profiles", response_model=MindscapeProfile, status_code=201)
async def create_profile(request: CreateProfileRequest):
    """Create a new mindscape profile"""
    try:
        return create_profile_record(store=store, request=request)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to create profile: {str(e)}"
        )


@router.get(
    "/profiles/me/preferences/ui-language",
    response_model=ProfileUiLanguageProjection,
)
async def get_my_ui_language(
    identity: AuthContext = Depends(get_current_identity),
):
    """Return the authenticated profile's effective UI locale and CAS version."""
    try:
        return await asyncio.to_thread(
            profile_ui_language_projection_service.get_ui_language,
            identity.user_id,
        )
    except ProfilePreferencesNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Profile not found") from exc


@router.patch(
    "/profiles/me/preferences",
    response_model=ProfileUiLanguageProjection,
)
async def patch_my_preferences(
    request: ProfilePreferencesPatchRequest,
    identity: AuthContext = Depends(get_current_identity),
):
    """Apply one allowlisted, optimistic current-profile preference mutation."""
    try:
        return await asyncio.to_thread(
            profile_preferences_mutation_service.patch_preferences,
            identity.user_id,
            request,
        )
    except ProfilePreferencesNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Profile not found") from exc
    except ProfilePreferencesConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "profile_preferences_version_conflict",
                "current_version": exc.current_version,
            },
        ) from exc


@router.get("/profiles/{user_id}", response_model=MindscapeProfile)
async def get_profile(user_id: str = Path(..., description="Profile ID")):
    """Get profile by ID"""
    return get_profile_or_404(store=store, user_id=user_id)


@router.put("/profiles/{user_id}", response_model=MindscapeProfile)
async def update_profile(
    user_id: str = Path(..., description="Profile ID"),
    request: UpdateProfileRequest = None,
):
    """Update an existing profile"""
    if request and "preferences" in request.model_fields_set:
        raise HTTPException(
            status_code=422,
            detail=(
                "Profile preferences must be updated through "
                "/profiles/me/preferences"
            ),
        )
    try:
        return update_profile_record(
            store=store,
            user_id=user_id,
            request=request,
            logger=logger,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to update profile: {str(e)}"
        )


@router.post("/profiles/{user_id}/intents", response_model=IntentCard, status_code=201)
async def create_intent(
    user_id: str = Path(..., description="Profile ID"),
    request: CreateIntentRequest = None,
):
    """Create a new intent card"""
    if not request:
        raise HTTPException(status_code=400, detail="Create request required")

    profile = store.get_profile(user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    try:
        intent = IntentCard(
            id=str(uuid.uuid4()),
            user_id=user_id,
            title=request.title,
            description=request.description,
            priority=request.priority,
            tags=request.tags,
            category=request.category,
            due_date=request.due_date,
            parent_intent_id=request.parent_intent_id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        created = store.create_intent(intent)

        try:
            is_high_priority = created.priority in ["high", "critical"]
            intent_event = MindEvent(
                id=str(uuid.uuid4()),
                timestamp=datetime.utcnow(),
                actor=EventActor.USER,
                channel="api",
                profile_id=user_id,
                project_id=None,
                workspace_id=None,
                event_type=EventType.INTENT_CREATED,
                payload={
                    "intent_id": created.id,
                    "title": created.title,
                    "description": created.description,
                    "status": created.status.value,
                    "priority": created.priority.value,
                },
                entity_ids=[created.id],
                metadata={
                    "should_embed": is_high_priority,
                    "is_artifact": is_high_priority,
                },
            )
            store.create_event(intent_event, generate_embedding=is_high_priority)
        except Exception as e:
            logger.warning(f"Failed to record intent creation event: {e}")

        return created

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to create intent: {str(e)}"
        )


@router.get("/profiles/{user_id}/intents", response_model=List[IntentCard])
async def list_intents(
    user_id: str = Path(..., description="Profile ID"),
    status: Optional[IntentStatus] = Query(None, description="Filter by status"),
    priority: Optional[PriorityLevel] = Query(None, description="Filter by priority"),
):
    """List intents for a profile"""
    return list_intents_payload(
        store=store,
        user_id=user_id,
        status=status,
        priority=priority,
    )


@router.get("/intents/{intent_id}", response_model=IntentCard)
async def get_intent(intent_id: str = Path(..., description="Intent ID")):
    """Get intent by ID"""
    return get_intent_or_404(store=store, intent_id=intent_id)


@router.put("/intents/{intent_id}", response_model=IntentCard)
async def update_intent(
    intent_id: str = Path(..., description="Intent ID"),
    request: UpdateIntentRequest = None,
):
    """Update an existing intent"""
    if not request:
        raise HTTPException(status_code=400, detail="Update request required")

    intent = store.get_intent(intent_id)
    if not intent:
        raise HTTPException(status_code=404, detail="Intent not found")

    if request.title is not None:
        intent.title = request.title
    if request.description is not None:
        intent.description = request.description
    if request.status is not None:
        intent.status = request.status
    if request.priority is not None:
        intent.priority = request.priority
    if request.tags is not None:
        intent.tags = request.tags
    if request.category is not None:
        intent.category = request.category
    if request.progress_percentage is not None:
        intent.progress_percentage = request.progress_percentage
    if request.due_date is not None:
        intent.due_date = request.due_date
    if request.metadata is not None:
        intent.metadata = request.metadata

    if request.status == IntentStatus.COMPLETED and not intent.completed_at:
        intent.completed_at = datetime.utcnow()
    if request.status == IntentStatus.ACTIVE and not intent.started_at:
        intent.started_at = datetime.utcnow()

    intent.updated_at = datetime.utcnow()
    is_completed = intent.status == IntentStatus.COMPLETED
    store.create_intent(intent)

    try:
        update_event = MindEvent(
            id=str(uuid.uuid4()),
            timestamp=datetime.utcnow(),
            actor=EventActor.USER,
            channel="api",
            profile_id=intent.user_id,
            project_id=None,
            workspace_id=None,
            event_type=EventType.INTENT_UPDATED,
            payload={
                "intent_id": intent.id,
                "title": intent.title,
                "description": intent.description,
                "status": intent.status.value,
                "priority": intent.priority.value,
                "updated_fields": [
                    k
                    for k in request.dict(exclude_unset=True).keys()
                    if k
                    in [
                        "title",
                        "description",
                        "status",
                        "priority",
                        "tags",
                        "category",
                    ]
                ],
            },
            entity_ids=[intent.id],
            metadata={
                "should_embed": is_completed or intent.priority in ["high", "critical"],
                "is_artifact": is_completed,
            },
        )
        store.create_event(
            update_event,
            generate_embedding=is_completed or intent.priority in ["high", "critical"],
        )
    except Exception as e:
        logger.warning(f"Failed to record intent update event: {e}")

    return intent


@router.delete("/intents/{intent_id}", status_code=204)
async def delete_intent(intent_id: str = Path(..., description="Intent ID")):
    """Delete an intent"""
    archive_intent(store=store, intent_id=intent_id)
    return None


@router.get("/intents/{intent_id}/playbooks", response_model=List[str])
async def get_intent_playbooks(intent_id: str = Path(..., description="Intent ID")):
    """Get playbook codes associated with an intent"""
    return get_intent_playbooks_payload(store=store, intent_id=intent_id)


@router.post("/intents/{intent_id}/playbooks/{playbook_code}", status_code=201)
async def associate_intent_playbook(
    intent_id: str = Path(..., description="Intent ID"),
    playbook_code: str = Path(..., description="Playbook code"),
):
    """Associate a playbook with an intent"""
    return await associate_intent_playbook_payload(
        store=store,
        intent_id=intent_id,
        playbook_code=playbook_code,
    )


@router.delete("/intents/{intent_id}/playbooks/{playbook_code}", status_code=204)
async def remove_intent_playbook(
    intent_id: str = Path(..., description="Intent ID"),
    playbook_code: str = Path(..., description="Playbook code"),
):
    """Remove association between intent and playbook"""
    remove_intent_playbook_payload(
        store=store,
        intent_id=intent_id,
        playbook_code=playbook_code,
    )
    return None
