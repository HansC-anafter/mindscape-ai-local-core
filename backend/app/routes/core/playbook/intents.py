"""
Playbook-Intent associations
"""

import logging
from typing import List
from fastapi import APIRouter, HTTPException, Path

logger = logging.getLogger(__name__)

router = APIRouter(tags=["playbooks-intents"])


@router.post("/{playbook_code}/associate/{intent_id}", status_code=201)
async def associate_intent_playbook(
    playbook_code: str = Path(..., description="Playbook code"),
    intent_id: str = Path(..., description="Intent ID")
):
    """Associate an intent with a playbook"""
    try:
        from ....services.mindscape_store import MindscapeStore
        mindscape_store = MindscapeStore()

        association = mindscape_store.associate_intent_playbook(intent_id, playbook_code)
        return {
            "intent_id": association.intent_id,
            "playbook_code": association.playbook_code,
            "message": "Association created"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create association: {str(e)}")


@router.delete("/{playbook_code}/associate/{intent_id}", status_code=204)
async def remove_intent_playbook_association(
    playbook_code: str = Path(..., description="Playbook code"),
    intent_id: str = Path(..., description="Intent ID")
):
    """Remove association between intent and playbook"""
    try:
        from ....services.mindscape_store import MindscapeStore
        mindscape_store = MindscapeStore()

        success = mindscape_store.remove_intent_playbook_association(intent_id, playbook_code)
        if not success:
            raise HTTPException(status_code=404, detail="Association not found")
        return None
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to remove association: {str(e)}")


@router.get("/intent/{intent_id}", response_model=List[str])
async def get_intent_playbooks(intent_id: str = Path(..., description="Intent ID")):
    """Get playbook codes associated with an intent"""
    try:
        from ....services.mindscape_store import MindscapeStore
        mindscape_store = MindscapeStore()

        playbook_codes = mindscape_store.get_intent_playbooks(intent_id)
        return playbook_codes
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get intent playbooks: {str(e)}")
