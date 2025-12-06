"""
Playbook CRUD operations
"""

import logging
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Path, Query

from ....models.playbook import Playbook, CreatePlaybookRequest, UpdatePlaybookRequest

logger = logging.getLogger(__name__)

router = APIRouter(tags=["playbooks-crud"])


@router.patch("/{playbook_code}/meta", response_model=Dict[str, Any])
async def update_playbook_meta(
    playbook_code: str,
    profile_id: str = Query('default-user'),
    favorite: Optional[bool] = None,
    hidden: Optional[bool] = None,
    custom_tags: Optional[List[str]] = None,
    user_notes: Optional[str] = None
):
    """Update user's personal meta for a playbook"""
    try:
        from ....services.playbook_service import PlaybookService
        from ....services.mindscape_store import MindscapeStore
        mindscape_store = MindscapeStore()
        playbook_service = PlaybookService(store=mindscape_store)

        playbook = await playbook_service.get_playbook(playbook_code)
        if not playbook:
            raise HTTPException(status_code=404, detail="Playbook not found")

        updates = {}
        if favorite is not None:
            updates['favorite'] = favorite
        if hidden is not None:
            updates['hidden'] = hidden
        if custom_tags is not None:
            updates['custom_tags'] = custom_tags

        user_meta = mindscape_store.update_user_meta(profile_id, playbook_code, updates)

        if user_notes is not None:
            mindscape_store.update_playbook(playbook_code, {'user_notes': user_notes})

        return {
            "success": True,
            "user_meta": user_meta
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("", response_model=Playbook, status_code=201)
async def create_playbook(request: CreatePlaybookRequest):
    """Create a new playbook"""
    try:
        from ....models.playbook import PlaybookMetadata
        from datetime import datetime

        playbook = Playbook(
            metadata=PlaybookMetadata(
                playbook_code=request.playbook_code,
                name=request.name,
                description=request.description,
                tags=request.tags,
                owner=request.owner,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            ),
            sop_content=request.sop_content
        )

        raise HTTPException(status_code=501, detail="Create playbook not yet implemented in PlaybookService")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create playbook: {str(e)}")


@router.put("/{playbook_code}", response_model=Dict[str, Any])
async def update_playbook(
    playbook_code: str = Path(..., description="Playbook code"),
    request: UpdatePlaybookRequest = None,
    locale: str = Query('zh-TW', description="Language locale")
):
    """Update a playbook"""
    if not request:
        raise HTTPException(status_code=400, detail="Update request required")

    try:
        from ....services.playbook_service import PlaybookService
        from ....services.mindscape_store import MindscapeStore
        mindscape_store = MindscapeStore()
        playbook_service = PlaybookService(store=mindscape_store)

        existing_playbook = await playbook_service.get_playbook(playbook_code, locale=locale)
        if not existing_playbook:
            raise HTTPException(status_code=404, detail="Playbook not found")

        if request.playbook_json:
            from ....services.playbook_loaders import PlaybookJsonLoader
            from ....models.playbook import PlaybookJson
            try:
                playbook_json_obj = PlaybookJson(**request.playbook_json)
                success = PlaybookJsonLoader.save_playbook_json(playbook_code, playbook_json_obj, locale)
                if not success:
                    logger.warning(f"Failed to save playbook.json for {playbook_code}")
            except Exception as e:
                logger.error(f"Failed to parse playbook_json: {e}", exc_info=True)
                raise HTTPException(status_code=400, detail=f"Invalid playbook_json format: {str(e)}")

        if request.sop_content is not None:
            # Validate edit permission (template playbooks cannot edit SOP)
            is_allowed, error_message = playbook_service.validate_edit_permission(
                existing_playbook,
                edit_type="sop"
            )
            if not is_allowed:
                raise HTTPException(status_code=403, detail=error_message)

            from pathlib import Path
            base_dir = Path(__file__).parent.parent.parent.parent
            i18n_dir = base_dir / "backend" / "i18n" / "playbooks" / locale
            md_file = i18n_dir / f"{playbook_code}.md"

            if md_file.exists():
                with open(md_file, 'r', encoding='utf-8') as f:
                    content = f.read()

                from ....services.playbook_loaders import PlaybookFileLoader
                frontmatter_dict, _ = PlaybookFileLoader.parse_frontmatter(content)

                if request.name is not None:
                    frontmatter_dict['name'] = request.name
                if request.description is not None:
                    frontmatter_dict['description'] = request.description
                if request.tags is not None:
                    frontmatter_dict['tags'] = request.tags

                import yaml
                frontmatter_text = yaml.dump(frontmatter_dict, allow_unicode=True, default_flow_style=False)
                new_content = f"---\n{frontmatter_text}---\n{request.sop_content}"

                with open(md_file, 'w', encoding='utf-8') as f:
                    f.write(new_content)

                logger.info(f"Updated playbook.md for {playbook_code} (locale: {locale})")
            else:
                logger.warning(f"playbook.md not found for {playbook_code} (locale: {locale})")

        playbook_service.registry.invalidate_cache(playbook_code, locale)
        await playbook_service.registry.reload_playbook(playbook_code, locale)

        updated_playbook = await playbook_service.get_playbook(playbook_code, locale=locale)
        if not updated_playbook:
            raise HTTPException(status_code=500, detail="Failed to reload playbook after update")

        return {
            "metadata": {
                "playbook_code": updated_playbook.metadata.playbook_code,
                "version": updated_playbook.metadata.version,
                "locale": updated_playbook.metadata.locale,
                "name": updated_playbook.metadata.name,
                "description": updated_playbook.metadata.description,
                "tags": updated_playbook.metadata.tags,
            },
            "sop_content": updated_playbook.sop_content,
            "message": "Playbook updated successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update playbook {playbook_code}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update playbook: {str(e)}")
