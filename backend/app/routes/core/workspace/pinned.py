import logging
from typing import List, Dict, Any

from fastapi import (
    APIRouter,
    HTTPException,
    Path as PathParam,
    Body,
)

from ....services.mindscape_store import MindscapeStore
from ....services.stores.workspace_pinned_playbooks_store import (
    WorkspacePinnedPlaybooksStore,
)

router = APIRouter()
logger = logging.getLogger(__name__)
store = MindscapeStore()
pinned_playbooks_store = WorkspacePinnedPlaybooksStore(store.db_path)


@router.get("/{workspace_id}/pinned-playbooks", response_model=List[Dict[str, Any]])
async def get_pinned_playbooks(
    workspace_id: str = PathParam(..., description="Workspace ID")
):
    """
    Get all pinned playbooks for a workspace
    """
    try:
        pinned = pinned_playbooks_store.list_pinned_playbooks(workspace_id)
        return pinned
    except Exception as e:
        logger.error(
            f"Failed to get pinned playbooks for workspace {workspace_id}: {e}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/{workspace_id}/pinned-playbooks", response_model=Dict[str, Any], status_code=201
)
async def pin_playbook(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    request: Dict[str, Any] = Body(...),
):
    """
    Pin a playbook to a workspace
    """
    try:
        playbook_code = request.get("playbook_code")
        if not playbook_code:
            raise HTTPException(status_code=400, detail="playbook_code is required")

        pinned_by = request.get("pinned_by")
        result = pinned_playbooks_store.pin_playbook(
            workspace_id, playbook_code, pinned_by
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to pin playbook {request.get('playbook_code')} to workspace {workspace_id}: {e}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{workspace_id}/pinned-playbooks/{playbook_code}", status_code=204)
async def unpin_playbook(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    playbook_code: str = PathParam(..., description="Playbook code"),
):
    """
    Unpin a playbook from a workspace
    """
    try:
        success = pinned_playbooks_store.unpin_playbook(workspace_id, playbook_code)
        if not success:
            raise HTTPException(
                status_code=404, detail="Playbook not pinned in this workspace"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to unpin playbook {playbook_code} from workspace {workspace_id}: {e}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=str(e))
