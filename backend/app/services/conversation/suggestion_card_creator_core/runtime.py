"""Runtime orchestration for suggestion card creation."""

import logging
from typing import Any, Dict, Optional

from backend.app.services.conversation.suggestion_card_creator_core.analysis import (
    extract_playbook_llm_analysis,
    is_background_playbook,
    normalize_llm_analysis,
    prepare_llm_analysis,
)
from backend.app.services.conversation.suggestion_card_creator_core.duplicates import (
    should_create_new_suggestion_task,
)
from backend.app.services.conversation.suggestion_card_creator_core.preferences import (
    check_user_preference,
)
from backend.app.services.conversation.suggestion_card_creator_core.task_factory import (
    build_playbook_suggestion_task,
    build_suggestion_task,
    emit_task_created,
)
from backend.app.services.conversation.suggestion_card_creator_core.validation import (
    validate_playbook,
)

logger = logging.getLogger(__name__)


async def create_suggestion_card(
    *,
    creator,
    task_plan,
    workspace_id: str,
    message_id: str,
    event_emitter,
) -> Optional[Dict[str, Any]]:
    try:
        pack_id = task_plan.pack_id

        validation_result = await validate_playbook(
            pack_id=pack_id,
            workspace_id=workspace_id,
            playbook_service=creator.playbook_service,
            default_locale=creator.default_locale,
        )
        if not validation_result["is_valid"]:
            logger.warning(
                "SuggestionCardCreator: Skipping suggestion task creation for "
                "invalid pack_id: %s. Reason: %s",
                pack_id,
                validation_result.get("reason", "unknown"),
            )
            return {
                "task_id": None,
                "timeline_item_id": None,
                "pack_id": pack_id,
                "skipped": True,
                "reason": validation_result.get("reason", "invalid_playbook_code"),
            }

        preference_result = await check_user_preference(
            task_plan=task_plan,
            workspace_id=workspace_id,
        )
        if not preference_result["should_auto_suggest"]:
            logger.info(
                "SuggestionCardCreator: Skipping suggestion task creation for pack "
                "%s (auto_suggest disabled by user preference)",
                pack_id,
            )
            return {
                "task_id": None,
                "timeline_item_id": None,
                "pack_id": pack_id,
                "skipped": True,
                "reason": "auto_suggest_disabled",
            }

        existing_tasks = creator.tasks_store.find_existing_suggestion_tasks(
            workspace_id=workspace_id,
            pack_id=pack_id,
            created_within_hours=1,
        )

        if existing_tasks:
            if not should_create_new_suggestion_task(existing_tasks, task_plan):
                existing_task = existing_tasks[0]
                logger.info(
                    "SuggestionCardCreator: Reusing existing suggestion task %s for "
                    "pack %s",
                    existing_task.id,
                    pack_id,
                )
                return {
                    "task_id": existing_task.id,
                    "timeline_item_id": None,
                    "pack_id": pack_id,
                    "is_duplicate": True,
                }

        suggestion_task = build_suggestion_task(
            task_plan=task_plan,
            workspace_id=workspace_id,
            message_id=message_id,
            llm_analysis=prepare_llm_analysis(task_plan),
        )
        creator.tasks_store.create_task(suggestion_task)
        logger.info(
            "SuggestionCardCreator: Created suggestion task %s "
            "(status=PENDING) for %s",
            suggestion_task.id,
            pack_id,
        )

        emit_task_created(
            event_emitter=event_emitter,
            task=suggestion_task,
            pack_id=pack_id,
        )

        return {
            "task_id": suggestion_task.id,
            "timeline_item_id": None,
            "pack_id": pack_id,
        }

    except Exception as exc:
        logger.error(
            "SuggestionCardCreator: Failed to create suggestion card: %s",
            exc,
            exc_info=True,
        )
        return None


async def create_playbook_suggestion(
    *,
    creator,
    playbook_code: str,
    playbook_context: Dict[str, Any],
    workspace_id: str,
    message_id: str,
    event_emitter,
) -> Dict[str, Any]:
    try:
        from backend.app.services.i18n_service import get_i18n_service

        i18n = get_i18n_service(default_locale=creator.default_locale)
        llm_analysis = normalize_llm_analysis(
            extract_playbook_llm_analysis(playbook_context),
            is_background_playbook(playbook_code),
        )

        suggestion_task = build_playbook_suggestion_task(
            playbook_code=playbook_code,
            playbook_context=playbook_context,
            workspace_id=workspace_id,
            message_id=message_id,
            llm_analysis=llm_analysis,
        )
        creator.tasks_store.create_task(suggestion_task)

        emit_task_created(
            event_emitter=event_emitter,
            task=suggestion_task,
            pack_id=playbook_code,
        )

        return {
            "status": "suggestion",
            "playbook_code": playbook_code,
            "task_id": suggestion_task.id,
            "timeline_item_id": None,
            "message": i18n.t(
                "conversation_orchestrator",
                "suggestion.add_to_mindscape",
            ),
        }

    except Exception as exc:
        logger.error(
            "SuggestionCardCreator: Failed to create playbook suggestion: %s",
            exc,
            exc_info=True,
        )
        return {"status": "error", "error": str(exc)}
