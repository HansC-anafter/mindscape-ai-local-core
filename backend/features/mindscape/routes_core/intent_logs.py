"""Intent-log helpers for mindscape routes."""

from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException


def list_intent_logs_payload(
    *,
    store,
    profile_id: str | None,
    start_time: str | None,
    end_time: str | None,
    has_override: bool | None,
    limit: int,
):
    """Return filtered intent logs."""
    start = datetime.fromisoformat(start_time) if start_time else None
    end = datetime.fromisoformat(end_time) if end_time else None
    return store.list_intent_logs(
        profile_id=profile_id,
        start_time=start,
        end_time=end,
        has_override=has_override,
        limit=limit,
    )


def get_intent_log_payload(*, store, log_id: str):
    """Return one intent log or raise not found."""
    log = store.get_intent_log(log_id)
    if not log:
        raise HTTPException(status_code=404, detail="Intent log not found")
    return log


def annotate_intent_log_record(*, store, log_id: str, request):
    """Persist intent-log override fields and return the updated record."""
    user_override = {}
    if request.correct_interaction_type:
        user_override["correct_interaction_type"] = request.correct_interaction_type
    if request.correct_task_domain:
        user_override["correct_task_domain"] = request.correct_task_domain
    if request.correct_playbook_code:
        user_override["correct_playbook_code"] = request.correct_playbook_code
    if request.notes:
        user_override["notes"] = request.notes

    updated_log = store.update_intent_log_override(log_id, user_override)
    if not updated_log:
        raise HTTPException(status_code=404, detail="Intent log not found")
    return updated_log
