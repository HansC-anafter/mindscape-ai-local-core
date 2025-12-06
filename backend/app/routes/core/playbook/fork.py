"""
Playbook Fork API
Endpoints for forking playbooks from template to workspace instance
"""

import logging
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Path, Query, Body
from pydantic import BaseModel, Field

from ....models.playbook import Playbook

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/playbooks",
    tags=["playbooks-fork"]
)


class ForkPlaybookRequest(BaseModel):
    """Request to fork a playbook"""
    target_playbook_code: str = Field(..., description="Target playbook code for the forked instance")
    workspace_id: str = Field(..., description="Workspace ID for the new instance")
    locale: str = Field(default="zh-TW", description="Language locale")


@router.post("/{playbook_code}/fork", response_model=Dict[str, Any], status_code=201)
async def fork_playbook(
    playbook_code: str = Path(..., description="Source playbook code (template)"),
    request: ForkPlaybookRequest = Body(...),
    profile_id: str = Query(..., description="Profile ID")
):
    """
    Fork a playbook from template to workspace instance

    Creates a workspace-scoped copy of a template playbook (system/tenant/profile).
    The forked playbook can be fully edited (SOP, resources, etc.).

    Example:
        POST /api/v1/playbooks/content_drafting/fork
        {
            "target_playbook_code": "content_drafting_workspace_1",
            "workspace_id": "workspace-123",
            "locale": "zh-TW"
        }
    """
    try:
        from ....services.playbook_service import PlaybookService
        from ....services.mindscape_store import MindscapeStore

        mindscape_store = MindscapeStore()
        playbook_service = PlaybookService(store=mindscape_store)

        # Get source playbook to validate
        source_playbook = await playbook_service.get_playbook(
            playbook_code,
            locale=request.locale,
            workspace_id=request.workspace_id
        )
        if not source_playbook:
            raise HTTPException(status_code=404, detail=f"Source playbook {playbook_code} not found")

        # Check if source is a template
        if not source_playbook.metadata.is_template():
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Cannot fork non-template playbook: {playbook_code} "
                    f"(scope: {source_playbook.metadata.get_scope_level()}). "
                    f"Only template playbooks (system/tenant/profile) can be forked."
                )
            )

        # Fork the playbook
        forked_playbook = await playbook_service.fork_playbook(
            source_playbook_code=playbook_code,
            target_playbook_code=request.target_playbook_code,
            workspace_id=request.workspace_id,
            profile_id=profile_id,
            locale=request.locale
        )

        if not forked_playbook:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to fork playbook {playbook_code}"
            )

        return {
            "success": True,
            "source_playbook_code": playbook_code,
            "target_playbook_code": request.target_playbook_code,
            "workspace_id": request.workspace_id,
            "playbook": {
                "playbook_code": forked_playbook.metadata.playbook_code,
                "name": forked_playbook.metadata.name,
                "scope": forked_playbook.metadata.get_scope_level(),
                "is_instance": forked_playbook.metadata.is_instance(),
            },
            "message": f"Playbook {playbook_code} forked to {request.target_playbook_code} for workspace {request.workspace_id}"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fork playbook {playbook_code}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fork playbook: {str(e)}")

