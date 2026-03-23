"""Onboarding and profile helpers for mindscape routes."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import HTTPException

from backend.app.models.mindscape import (
    EventActor,
    EventType,
    MindEvent,
    MindscapeProfile,
)


def get_onboarding_status_payload(*, onboarding_service, user_id: str) -> dict:
    """Return onboarding status payload for a profile."""
    status = onboarding_service.get_onboarding_status(user_id)
    completed_count = onboarding_service.get_completion_count(user_id)
    return {
        "onboarding_state": status,
        "completed_count": completed_count,
        "is_complete": onboarding_service.is_onboarding_complete(user_id),
    }


def complete_self_intro_payload(
    *,
    onboarding_service,
    user_id: str,
    identity: str,
    solving: str,
    thinking: str,
):
    """Complete onboarding task 1."""
    return onboarding_service.complete_task1_self_intro(
        user_id=user_id,
        identity=identity,
        solving=solving,
        thinking=thinking,
    )


def complete_task2_payload(
    *,
    onboarding_service,
    user_id: str,
    execution_id: str | None,
    intent_id: str | None,
):
    """Complete onboarding task 2."""
    return onboarding_service.complete_task2_project_breakdown(
        user_id=user_id,
        execution_id=execution_id,
        intent_id=intent_id,
    )


def complete_task3_payload(
    *,
    onboarding_service,
    user_id: str,
    execution_id: str | None,
    created_seeds_count: int,
):
    """Complete onboarding task 3."""
    return onboarding_service.complete_task3_weekly_review(
        user_id=user_id,
        execution_id=execution_id,
        created_seeds_count=created_seeds_count,
    )


async def playbook_completion_webhook_payload(
    *,
    governance_engine,
    execution_id: str,
    playbook_code: str,
    user_id: str,
    output_data: dict,
):
    """Handle the playbook completion webhook payload."""
    return await governance_engine.process_playbook_webhook(
        execution_id=execution_id,
        playbook_code=playbook_code,
        user_id=user_id,
        output_data=output_data,
    )


def create_profile_record(*, store, request) -> MindscapeProfile:
    """Create and persist a new mindscape profile."""
    profile = MindscapeProfile(
        id=str(uuid.uuid4()),
        name=request.name,
        email=request.email,
        roles=request.roles,
        domains=request.domains,
        preferences=request.preferences or None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    return store.create_profile(profile)


def get_profile_or_404(*, store, user_id: str):
    """Return a profile or raise not found."""
    profile = store.get_profile(user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


def update_profile_record(*, store, user_id: str, request, logger):
    """Update a profile and record the profile-updated event."""
    if not request:
        raise HTTPException(status_code=400, detail="Update request required")

    updates = {}
    for field_name in ("name", "email", "roles", "domains", "preferences"):
        value = getattr(request, field_name)
        if value is not None:
            updates[field_name] = value

    updated = store.update_profile(user_id, updates)
    if not updated:
        raise HTTPException(status_code=404, detail="Profile not found")

    try:
        update_event = MindEvent(
            id=str(uuid.uuid4()),
            timestamp=datetime.utcnow(),
            actor=EventActor.USER,
            channel="api",
            profile_id=user_id,
            project_id=None,
            workspace_id=None,
            event_type=EventType.PROFILE_UPDATED,
            payload={
                "updated_fields": list(updates.keys()),
                "updates": updates,
            },
            entity_ids=[],
            metadata={},
        )
        store.create_event(update_event)
    except Exception as exc:
        logger.warning("Failed to record profile update event: %s", exc)

    return updated
