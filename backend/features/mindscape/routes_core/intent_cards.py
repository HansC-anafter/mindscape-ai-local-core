"""Intent-card helpers for mindscape routes."""

from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException

from backend.app.models.mindscape import IntentStatus


def list_intents_payload(*, store, user_id: str, status, priority):
    """Return intent cards for an existing profile."""
    profile = store.get_profile(user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return store.list_intents(user_id, status=status, priority=priority)


def get_intent_or_404(*, store, intent_id: str):
    """Return one intent card or raise not found."""
    intent = store.get_intent(intent_id)
    if not intent:
        raise HTTPException(status_code=404, detail="Intent not found")
    return intent


def archive_intent(*, store, intent_id: str) -> None:
    """Archive an intent card when delete support is not available."""
    intent = get_intent_or_404(store=store, intent_id=intent_id)
    intent.status = IntentStatus.ARCHIVED
    intent.updated_at = datetime.utcnow()
    store.create_intent(intent)
