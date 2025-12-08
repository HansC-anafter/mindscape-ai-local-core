"""
Playbook management operations (reindex, reload)
"""

import logging
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Path, Query

logger = logging.getLogger(__name__)

router = APIRouter(tags=["playbooks-management"])


@router.post("/reindex", response_model=Dict[str, Any])
async def reindex_playbooks():
    """Re-scan and index all playbooks from file system"""
    try:
        from ....services.playbook_service import PlaybookService
        from ....services.mindscape_store import MindscapeStore

        mindscape_store = MindscapeStore()
        playbook_service = PlaybookService(store=mindscape_store)

        playbook_service.registry.invalidate_cache()

        await playbook_service.registry._load_all_playbooks()
        playbook_service.registry._loaded = True

        return {
            "message": "Playbooks reindexed successfully",
            "system_playbooks": sum(len(pbs) for pbs in playbook_service.registry.system_playbooks.values()),
            "capability_playbooks": sum(len(pbs) for pbs in playbook_service.registry.capability_playbooks.values()),
            "user_playbooks": sum(len(pbs) for pbs in playbook_service.registry.user_playbooks.values())
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{playbook_code}/reload", response_model=Dict[str, Any])
async def reload_playbook(
    playbook_code: str = Path(..., description="Playbook code"),
    locale: str = Query('zh-TW', description="Language locale")
):
    """Reload a specific playbook from file system"""
    try:
        from ....services.playbook_service import PlaybookService
        from ....services.mindscape_store import MindscapeStore

        mindscape_store = MindscapeStore()
        playbook_service = PlaybookService(store=mindscape_store)

        playbook_service.registry.invalidate_cache(playbook_code, locale)

        success = await playbook_service.registry.reload_playbook(playbook_code, locale)

        if not success:
            raise HTTPException(status_code=404, detail=f"Playbook {playbook_code} not found or failed to reload")

        from ....services.playbook_loaders import PlaybookJsonLoader
        playbook_json = PlaybookJsonLoader.load_playbook_json(playbook_code)
        if playbook_json:
            logger.info(f"Reloaded playbook.json for {playbook_code} (locale: {locale})")
        else:
            logger.warning(f"playbook.json not found for {playbook_code} after reload")

        reloaded_playbook = await playbook_service.get_playbook(playbook_code, locale=locale)
        if not reloaded_playbook:
            raise HTTPException(status_code=500, detail="Failed to get reloaded playbook")

        return {
            "message": f"Playbook {playbook_code} reloaded successfully",
            "playbook_code": reloaded_playbook.metadata.playbook_code,
            "locale": reloaded_playbook.metadata.locale,
            "name": reloaded_playbook.metadata.name,
            "playbook_json_reloaded": playbook_json is not None
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to reload playbook {playbook_code}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to reload playbook: {str(e)}")
