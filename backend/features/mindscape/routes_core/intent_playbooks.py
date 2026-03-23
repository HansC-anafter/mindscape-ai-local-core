"""Intent-playbook association helpers for mindscape routes."""

from __future__ import annotations

from fastapi import HTTPException


def get_intent_playbooks_payload(*, store, intent_id: str) -> list[str]:
    """Return playbook codes associated with an intent."""
    from backend.app.services.playbook_service import PlaybookService

    playbook_service = PlaybookService(store=store)
    intent = store.get_intent(intent_id)
    if not intent:
        raise HTTPException(status_code=404, detail="Intent not found")
    return playbook_service.playbook_store.get_intent_playbooks(intent_id)


async def associate_intent_playbook_payload(
    *,
    store,
    intent_id: str,
    playbook_code: str,
) -> dict[str, str]:
    """Associate a playbook with an intent."""
    from backend.app.services.playbook_service import PlaybookService

    playbook_service = PlaybookService(store=store)
    intent = store.get_intent(intent_id)
    if not intent:
        raise HTTPException(status_code=404, detail="Intent not found")

    playbook = await playbook_service.get_playbook(
        playbook_code=playbook_code,
        locale="zh-TW",
        workspace_id=None,
    )
    if not playbook:
        raise HTTPException(status_code=404, detail="Playbook not found")

    association = playbook_service.playbook_store.associate_intent_playbook(
        intent_id,
        playbook_code,
    )
    return {
        "intent_id": association.intent_id,
        "playbook_code": association.playbook_code,
        "message": "Association created",
    }


def remove_intent_playbook_payload(
    *,
    store,
    intent_id: str,
    playbook_code: str,
) -> None:
    """Remove the association between an intent and a playbook."""
    from backend.app.services.playbook_service import PlaybookService

    playbook_service = PlaybookService(store=store)
    success = playbook_service.playbook_store.remove_intent_playbook_association(
        intent_id,
        playbook_code,
    )
    if not success:
        raise HTTPException(status_code=404, detail="Association not found")
