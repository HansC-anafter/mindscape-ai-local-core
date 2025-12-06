"""
Playbook query and list endpoints
"""

import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Query

from ....models.playbook import Playbook
from .utils import (
    determine_preferred_locale,
    select_preferred_locale_version,
    filter_playbooks,
    format_playbook_list_response,
    sort_playbooks_by_user_preference
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["playbooks-queries"])


@router.get("/", response_model=List[Dict[str, Any]])
async def list_playbooks(
    tags: Optional[str] = Query(None, description="Comma-separated tags"),
    locale: str = Query('zh-TW', description="[DEPRECATED] Language locale. Use target_language instead."),
    target_language: Optional[str] = Query(None, description="Target language for filtering (e.g., 'zh-TW', 'en'). Playbooks are language-neutral by default."),
    scope: str = Query('system', description="system|user|all"),
    onboarding_task: Optional[str] = Query(None, description="Filter by onboarding task"),
    uses_tool: Optional[str] = Query(None, description="Filter playbooks that require this tool (e.g., 'wordpress', 'canva')"),
    profile_id: str = Query('default-user', description="User profile for personalization")
):
    """
    List playbooks with filtering and personalization

    Returns playbooks with user meta (favorite, use_count, etc.)
    Playbooks are language-neutral by default. The target_language parameter is informational only.
    """
    try:
        from ....services.playbook_service import PlaybookService
        from ....services.mindscape_store import MindscapeStore
        mindscape_store = MindscapeStore()
        playbook_service = PlaybookService(store=mindscape_store)

        tag_list = tags.split(',') if tags else None

        all_playbook_metadata = await playbook_service.list_playbooks(
            locale=None,
            tags=tag_list
        )

        file_playbooks = []
        for metadata in all_playbook_metadata:
            playbook = Playbook(
                metadata=metadata,
                sop_content=""
            )
            file_playbooks.append(playbook)

        preferred_locale = determine_preferred_locale(target_language, locale)
        playbooks = select_preferred_locale_version(file_playbooks, preferred_locale)

        playbooks = filter_playbooks(playbooks, tag_list, onboarding_task, uses_tool)

        results = []
        for playbook in playbooks:
            user_meta = None
            has_personal_variant = False
            default_variant = None

            results.append(format_playbook_list_response(
                playbook,
                user_meta,
                has_personal_variant,
                default_variant
            ))

        results = sort_playbooks_by_user_preference(results)

        return results

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/discover", response_model=Dict[str, Any])
async def discover_playbook(
    request: Dict[str, Any]
):
    """
    Discover playbook based on user query using LLM
    """
    try:
        from ....services.playbook_service import PlaybookService
        from ....services.mindscape_store import MindscapeStore
        mindscape_store = MindscapeStore()
        playbook_service = PlaybookService(store=mindscape_store)

        query = request.get('query', '')
        profile_id = request.get('profile_id', 'default-user')

        if not query:
            return {
                'suggestion': '請描述你的需求，例如：「我想分析數據」、「我需要生成 Instagram 貼文」等。',
                'recommended_playbooks': []
            }

        all_playbook_metadata = await playbook_service.list_playbooks()
        all_playbooks = [Playbook(metadata=m, sop_content="") for m in all_playbook_metadata]

        query_lower = query.lower()
        matched_playbooks = []

        for playbook in all_playbooks:
            name = playbook.metadata.name.lower()
            description = playbook.metadata.description.lower()
            tags = ' '.join([tag.lower() for tag in playbook.metadata.tags or []])

            if (query_lower in name or
                query_lower in description or
                any(query_lower in tag for tag in playbook.metadata.tags or [])):
                matched_playbooks.append({
                    'playbook_code': playbook.metadata.playbook_code,
                    'name': playbook.metadata.name,
                    'description': playbook.metadata.description,
                    'icon': playbook.metadata.icon
                })

        matched_playbooks = matched_playbooks[:5]

        if matched_playbooks:
            playbook_list = '\n\n'.join([
                f"{i + 1}. {p.get('icon', '📋')} {p.get('name', '')}\n   {p.get('description', '')}"
                for i, p in enumerate(matched_playbooks)
            ])
            suggestion = f'根據你的需求「{query}」，我找到 {len(matched_playbooks)} 個相關的 Playbook：\n\n{playbook_list}'
        else:
            suggestion = f'抱歉，我沒有找到與「{query}」相關的 Playbook。請嘗試使用其他關鍵字，或查看完整的 Playbook 列表。'

        return {
            'suggestion': suggestion,
            'recommended_playbooks': matched_playbooks
        }
    except Exception as e:
        logger.error(f"Failed to discover playbook: {e}")
        return {
            'suggestion': '抱歉，暫時無法處理你的請求。請稍後再試。',
            'recommended_playbooks': []
        }


@router.get("/{playbook_code}", response_model=Dict[str, Any])
async def get_playbook(
    playbook_code: str,
    version: Optional[str] = Query(None),
    locale: str = Query('zh-TW', description="[DEPRECATED] Language locale. Use target_language instead."),
    target_language: Optional[str] = Query(None, description="Target language for content (e.g., 'zh-TW', 'en'). Playbooks are language-neutral."),
    profile_id: str = Query('default-user')
):
    """
    Get playbook detail with user meta and associated intents

    Playbooks are language-neutral. The target_language parameter is used for execution,
    but the SOP content is returned as-is from the Playbook file.
    """
    try:
        from ....services.playbook_service import PlaybookService
        from ....services.mindscape_store import MindscapeStore
        mindscape_store = MindscapeStore()
        playbook_service = PlaybookService(store=mindscape_store)

        base_code = playbook_code.replace('.en', '')

        preferred_locale = determine_preferred_locale(target_language, locale)

        playbook = await playbook_service.get_playbook(
            playbook_code=base_code,
            locale=preferred_locale
        )

        if not playbook:
            raise HTTPException(status_code=404, detail="Playbook not found")

        playbook_steps = []
        try:
            from ....services.playbook_loaders.json_loader import PlaybookJsonLoader
            playbook_json = PlaybookJsonLoader.load_playbook_json(base_code)
            if playbook_json and hasattr(playbook_json, 'steps') and playbook_json.steps:
                playbook_steps = []
                for step in playbook_json.steps:
                    if hasattr(step, 'model_dump'):
                        playbook_steps.append(step.model_dump())
                    elif hasattr(step, 'dict'):
                        playbook_steps.append(step.dict())
                    else:
                        playbook_steps.append(step)
        except Exception as e:
            logger.debug(f"Failed to load playbook JSON for {base_code}: {e}")

        user_meta = None
        intent_ids = []
        associated_intents = []
        if intent_ids:
            for intent_id in intent_ids:
                try:
                    intent = mindscape_store.get_intent(intent_id)
                    if intent:
                        associated_intents.append({
                            "intent_id": intent.id,
                            "title": intent.title,
                            "status": intent.status.value if intent.status else "active",
                            "priority": intent.priority.value if intent.priority else "medium"
                        })
                except Exception as e:
                    logger.warning(f"Failed to fetch intent {intent_id}: {e}")
                    associated_intents.append({
                        "intent_id": intent_id,
                        "title": f"Intent {intent_id}"
                    })

        default_variant = None
        has_personal_variant = False

        active_executions = []
        recent_executions = []
        try:
            from datetime import datetime
            import sys

            try:
                from ...playbook_execution import playbook_runner
            except (ImportError, AttributeError):
                from ....services.playbook_runner import PlaybookRunner
                playbook_runner = PlaybookRunner()

            active_execution_ids = playbook_runner.list_active_executions()
            for exec_id in active_execution_ids:
                try:
                    conv_manager = playbook_runner.active_conversations.get(exec_id)
                    if conv_manager and conv_manager.playbook.metadata.playbook_code == playbook_code:
                        started_at = None
                        if conv_manager.conversation_history:
                            started_at = datetime.utcnow().isoformat()
                        active_executions.append({
                            "execution_id": exec_id,
                            "status": "running",
                            "started_at": started_at
                        })
                except Exception as e:
                    logger.debug(f"Failed to get execution info for {exec_id}: {e}")

            events = mindscape_store.get_events(
                profile_id=profile_id,
                limit=50
            )
            for event in events:
                payload = event.payload if isinstance(event.payload, dict) else {}
                if (event.channel == "playbook" and
                    (payload.get("playbook_code") == playbook_code or
                     event.metadata and event.metadata.get("playbook_code") == playbook_code)):
                    recent_executions.append({
                        "execution_id": payload.get("execution_id", event.id),
                        "status": payload.get("status", "completed"),
                        "started_at": event.timestamp.isoformat() if hasattr(event.timestamp, 'isoformat') else str(event.timestamp),
                        "completed_at": payload.get("completed_at")
                    })
            recent_executions.sort(key=lambda x: x.get("started_at", ""), reverse=True)
            recent_executions = recent_executions[:5]
        except Exception as e:
            logger.warning(f"Failed to fetch execution status: {e}")

        return {
            "metadata": {
                "playbook_code": playbook.metadata.playbook_code,
                "version": playbook.metadata.version,
                "locale": playbook.metadata.locale,
                "name": playbook.metadata.name,
                "description": playbook.metadata.description,
                "tags": playbook.metadata.tags,
                "entry_agent_type": playbook.metadata.entry_agent_type,
                "onboarding_task": playbook.metadata.onboarding_task,
                "icon": playbook.metadata.icon,
                "required_tools": playbook.metadata.required_tools,
                "scope": playbook.metadata.scope,
                "owner": playbook.metadata.owner,
            },
            "sop_content": playbook.sop_content,
            "steps": playbook_steps,
            "user_notes": playbook.user_notes,
            "user_meta": user_meta or {},
            "associated_intents": associated_intents,
            "execution_status": {
                "active_executions": active_executions,
                "recent_executions": recent_executions[:5]
            },
            "version_info": {
                "has_personal_variant": has_personal_variant,
                "default_variant": default_variant,
                "system_version": playbook.metadata.version
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/manifest", response_model=Dict[str, Any])
async def get_playbook_manifest():
    """
    Get manifest of installed playbook packages
    
    Returns list of installed @mindscape/playbook-* packages
    for frontend dynamic loading
    """
    try:
        from ....services.playbook_loaders.npm_loader import PlaybookNpmLoader
        
        packages = PlaybookNpmLoader.find_playbook_packages()
        
        playbooks = []
        for package in packages:
            playbooks.append({
                "name": package["name"],
                "version": package["version"],
                "playbook_code": package["playbook_code"],
                "register_function": f"register{package['playbook_code'].replace('_', '').title().replace('-', '')}Playbook"
            })
        
        return {
            "playbooks": playbooks
        }
    except Exception as e:
        logger.error(f"Failed to get playbook manifest: {e}")
        return {
            "playbooks": []
        }
