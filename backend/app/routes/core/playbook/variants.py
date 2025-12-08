"""
Playbook variants management
"""

import logging
from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException, Path, Query

logger = logging.getLogger(__name__)

router = APIRouter(tags=["playbooks-variants"])


@router.get("/{playbook_code}/variants", response_model=List[Dict[str, Any]])
async def get_playbook_variants(
    playbook_code: str = Path(..., description="Playbook code"),
    profile_id: str = Query('default-user', description="User profile ID")
):
    """
    Get personalized variants for a playbook
    Returns empty list if no variants exist
    """
    try:
        from ....services.mindscape_store import MindscapeStore
        mindscape_store = MindscapeStore()

        variants = mindscape_store.list_personalized_variants(profile_id, playbook_code, active_only=True)
        return variants
    except Exception as e:
        logger.debug(f"Failed to load variants for {playbook_code}: {e}")
        return []
