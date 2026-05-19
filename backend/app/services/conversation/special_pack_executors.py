"""Special pack executor facade."""

from typing import Any, Dict, List, Optional

from backend.app.services.conversation.special_pack_executors_core import (
    build_execution_result,
    execute_semantic_seeds as execute_semantic_seeds_helper,
    extract_intents_from_files,
    extract_intents_from_message,
    get_intents_from_events,
    get_intents_from_timeline_items,
    utc_now as _utc_now,
)
from backend.app.services.conversation.task_events_emitter import TaskEventsEmitter


class SpecialPackExecutors:
    """Executes local-core special pack paths."""

    def __init__(
        self,
        tasks_store,
        timeline_items_store,
        store,
        config_store,
        event_emitter: Optional[TaskEventsEmitter] = None,
    ):
        self.tasks_store = tasks_store
        self.timeline_items_store = timeline_items_store
        self.store = store
        self.config_store = config_store
        self.event_emitter = event_emitter

    async def execute_semantic_seeds(
        self,
        workspace_id: str,
        profile_id: str,
        message_id: str,
        files: List[str],
        message: str,
        event_emitter: Optional[TaskEventsEmitter] = None,
    ) -> Optional[Dict[str, Any]]:
        """Execute the semantic_seeds special pack path."""
        return await execute_semantic_seeds_helper(
            executor=self,
            workspace_id=workspace_id,
            profile_id=profile_id,
            message_id=message_id,
            files=files,
            message=message,
            event_emitter=event_emitter,
        )

    async def _get_intents_from_timeline_items(
        self, workspace_id: str
    ) -> List[str]:
        return await get_intents_from_timeline_items(
            timeline_items_store=self.timeline_items_store,
            workspace_id=workspace_id,
        )

    async def _get_intents_from_events(
        self, workspace_id: str, extracted_intents: List[str], file_contents: List[str]
    ) -> tuple[List[str], List[str]]:
        return await get_intents_from_events(
            store=self.store,
            workspace_id=workspace_id,
            extracted_intents=extracted_intents,
            file_contents=file_contents,
        )

    async def _extract_intents_from_files(
        self,
        profile_id: str,
        message_id: str,
        message: str,
        file_contents: List[str],
    ) -> List[str]:
        return await extract_intents_from_files(
            config_store=self.config_store,
            profile_id=profile_id,
            message_id=message_id,
            message=message,
            file_contents=file_contents,
        )

    async def _extract_intents_from_message(
        self, profile_id: str, message_id: str, message: str
    ) -> List[str]:
        return await extract_intents_from_message(
            config_store=self.config_store,
            profile_id=profile_id,
            message_id=message_id,
            message=message,
        )

    def _build_execution_result(
        self,
        extracted_intents: List[str],
        files: List[str],
        file_contents: List[str],
    ) -> Dict[str, Any]:
        return build_execution_result(
            extracted_intents=extracted_intents,
            files=files,
            file_contents=file_contents,
        )
