"""Suggestion card creator facade."""

from typing import Any, Dict, Optional

from backend.app.services.conversation.suggestion_card_creator_core import (
    check_user_preference,
    create_playbook_suggestion as create_playbook_suggestion_helper,
    create_suggestion_card as create_suggestion_card_helper,
    normalize_llm_analysis,
    prepare_llm_analysis,
    should_create_new_suggestion_task,
    validate_playbook,
)
from backend.app.services.conversation.task_events_emitter import TaskEventsEmitter


class SuggestionCardCreator:
    """Creates suggestion cards for soft-write and external-write tasks."""

    def __init__(
        self,
        tasks_store,
        playbook_service=None,
        message_generator=None,
        default_locale: str = "en",
    ):
        self.tasks_store = tasks_store
        self.playbook_service = playbook_service
        self.message_generator = message_generator
        self.default_locale = default_locale

    async def create_suggestion_card(
        self,
        task_plan,
        workspace_id: str,
        message_id: str,
        event_emitter: TaskEventsEmitter,
    ) -> Optional[Dict[str, Any]]:
        """Create a suggestion task for a planned soft-write or external-write task."""
        return await create_suggestion_card_helper(
            creator=self,
            task_plan=task_plan,
            workspace_id=workspace_id,
            message_id=message_id,
            event_emitter=event_emitter,
        )

    async def create_playbook_suggestion(
        self,
        playbook_code: str,
        playbook_context: Dict[str, Any],
        workspace_id: str,
        message_id: str,
        event_emitter: TaskEventsEmitter,
    ) -> Dict[str, Any]:
        """Create a suggestion task for a soft-write playbook."""
        return await create_playbook_suggestion_helper(
            creator=self,
            playbook_code=playbook_code,
            playbook_context=playbook_context,
            workspace_id=workspace_id,
            message_id=message_id,
            event_emitter=event_emitter,
        )

    async def _validate_playbook(
        self, pack_id: str, workspace_id: str
    ) -> Dict[str, Any]:
        return await validate_playbook(
            pack_id=pack_id,
            workspace_id=workspace_id,
            playbook_service=self.playbook_service,
            default_locale=self.default_locale,
        )

    async def _check_user_preference(
        self, task_plan, workspace_id: str
    ) -> Dict[str, Any]:
        return await check_user_preference(
            task_plan=task_plan,
            workspace_id=workspace_id,
        )

    def _should_create_new_suggestion_task(
        self, existing_tasks: list, task_plan
    ) -> bool:
        return should_create_new_suggestion_task(existing_tasks, task_plan)

    def _prepare_llm_analysis(self, task_plan) -> Dict[str, Any]:
        return prepare_llm_analysis(task_plan)

    def _normalize_llm_analysis(
        self, llm_analysis: Dict[str, Any], is_background_playbook: bool
    ) -> Dict[str, Any]:
        return normalize_llm_analysis(llm_analysis, is_background_playbook)
