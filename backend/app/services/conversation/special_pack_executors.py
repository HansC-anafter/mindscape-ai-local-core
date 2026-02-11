"""
Special Pack Executors

Handles execution of special pack executors that require custom logic
(e.g., semantic_seeds, daily_planning, content_drafting).
"""

import logging
import sys
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
import uuid

from ...models.workspace import Task, TaskStatus, TimelineItemType
from ...models.mindscape import EventType
from .task_events_emitter import TaskEventsEmitter

logger = logging.getLogger(__name__)


class SpecialPackExecutors:
    """
    Executes special pack executors

    Responsibilities:
    - Execute semantic_seeds pack
    - Handle other special pack executors with custom logic
    - Maintain backward compatibility with legacy implementations
    """

    def __init__(
        self,
        tasks_store,
        timeline_items_store,
        store,
        config_store,
        event_emitter: Optional[TaskEventsEmitter] = None,
    ):
        """
        Initialize SpecialPackExecutors

        Args:
            tasks_store: TasksStore instance
            timeline_items_store: TimelineItemsStore instance
            store: MindscapeStore instance
            config_store: ConfigStore instance
            event_emitter: Optional TaskEventsEmitter instance
        """
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
        """
        Execute semantic_seeds pack - can work with or without files

        Args:
            workspace_id: Workspace ID
            profile_id: User profile ID
            message_id: Message ID
            files: List of file IDs
            message: User message
            event_emitter: Optional TaskEventsEmitter instance

        Returns:
            Execution result dict or None if failed
        """
        try:
            pack_id = "semantic_seeds"

            # Create task
            task = Task(
                id=str(uuid.uuid4()),
                workspace_id=workspace_id,
                message_id=message_id,
                execution_id=None,
                pack_id=pack_id,
                task_type="extract_intents",
                status=TaskStatus.RUNNING,
                params={"files": files, "message": message},
                result=None,
                created_at=_utc_now(),
                started_at=_utc_now(),
                completed_at=None,
                error=None,
            )
            self.tasks_store.create_task(task)
            logger.info(
                f"SpecialPackExecutors: Created RUNNING task {task.id} for semantic_seeds "
                f"(pack_id={pack_id}, workspace={workspace_id})"
            )

            # Emit task created event
            emitter = event_emitter or self.event_emitter
            if emitter:
                emitter.emit_task_created(
                    task_id=task.id,
                    pack_id=pack_id,
                    status=task.status.value,
                    task_type=task.task_type,
                    workspace_id=workspace_id,
                )

            # Extract intents
            extracted_intents = []
            file_contents = []

            # Get intents from timeline items
            extracted_intents.extend(
                await self._get_intents_from_timeline_items(workspace_id)
            )

            # Get intents from events
            extracted_intents, file_contents = await self._get_intents_from_events(
                workspace_id, extracted_intents, file_contents
            )

            # Extract from files if available
            if not extracted_intents and file_contents:
                extracted_intents.extend(
                    await self._extract_intents_from_files(
                        profile_id, message_id, message, file_contents
                    )
                )

            # Extract from message if no files
            if not extracted_intents and not file_contents and message:
                extracted_intents.extend(
                    await self._extract_intents_from_message(
                        profile_id, message_id, message
                    )
                )

            # Build execution result
            execution_result = self._build_execution_result(
                extracted_intents, files, file_contents
            )

            # Update task status
            self.tasks_store.update_task_status(
                task_id=task.id,
                status=TaskStatus.SUCCEEDED,
                result=execution_result,
                completed_at=_utc_now(),
            )
            logger.info(
                f"SpecialPackExecutors: Updated task {task.id} to SUCCEEDED"
            )

            # Emit task updated event
            if emitter:
                emitter.emit_task_updated(
                    task_id=task.id,
                    pack_id=pack_id,
                    status=TaskStatus.SUCCEEDED.value,
                    task_type=task.task_type,
                    workspace_id=workspace_id,
                )

            return {
                "pack_id": pack_id,
                "task_id": task.id,
                "result": execution_result,
            }

        except Exception as e:
            logger.error(
                f"SpecialPackExecutors: Failed to execute semantic_seeds: {e}",
                exc_info=True,
            )
            return None

    async def _get_intents_from_timeline_items(
        self, workspace_id: str
    ) -> List[str]:
        """
        Get intents from timeline items

        Args:
            workspace_id: Workspace ID

        Returns:
            List of intent texts
        """
        extracted_intents = []

        try:
            if self.timeline_items_store:
                recent_timeline_items = (
                    self.timeline_items_store.list_timeline_items_by_workspace(
                        workspace_id=workspace_id, limit=10
                    )
                )
                for item in recent_timeline_items:
                    if item.type == TimelineItemType.INTENT_SEEDS:
                        item_data = item.data if isinstance(item.data, dict) else {}
                        if "intents" in item_data:
                            intents_list = item_data.get("intents", [])
                            if isinstance(intents_list, list):
                                for intent_obj in intents_list:
                                    if isinstance(intent_obj, dict):
                                        intent_text = (
                                            intent_obj.get("title")
                                            or intent_obj.get("text")
                                            or str(intent_obj)
                                        )
                                    else:
                                        intent_text = str(intent_obj)
                                    if intent_text and intent_text not in extracted_intents:
                                        extracted_intents.append(intent_text)
                            logger.info(
                                f"SpecialPackExecutors: Found {len(intents_list)} intents from IntentExtractor timeline_item {item.id}"
                            )
        except Exception as e:
            logger.warning(
                f"SpecialPackExecutors: Failed to get intents from timeline_items: {e}"
            )

        return extracted_intents

    async def _get_intents_from_events(
        self, workspace_id: str, extracted_intents: List[str], file_contents: List[str]
    ) -> tuple[List[str], List[str]]:
        """
        Get intents from events

        Args:
            workspace_id: Workspace ID
            extracted_intents: Existing intents list
            file_contents: Existing file contents list

        Returns:
            Tuple of (extracted_intents, file_contents)
        """
        try:
            recent_events = self.store.get_events_by_workspace(
                workspace_id=workspace_id, limit=50
            )

            for event in recent_events:
                if event.event_type == EventType.MESSAGE:
                    payload = event.payload if isinstance(event.payload, dict) else {}
                    metadata = event.metadata if isinstance(event.metadata, dict) else {}

                    file_analysis = metadata.get("file_analysis", {})
                    collaboration = file_analysis.get("collaboration_results", {})
                    semantic_seeds = collaboration.get("semantic_seeds", {})

                    if semantic_seeds.get("enabled") and semantic_seeds.get("intents"):
                        intents = semantic_seeds.get("intents", [])
                        for intent in intents:
                            intent_text = (
                                intent
                                if isinstance(intent, str)
                                else (
                                    intent.get("title")
                                    or intent.get("text")
                                    or str(intent)
                                )
                            )
                            if intent_text and intent_text not in extracted_intents:
                                extracted_intents.append(intent_text)

                        analysis = file_analysis.get("analysis", {})
                        file_info = analysis.get("file_info", {})
                        if file_info.get("text_content"):
                            file_contents.append(file_info["text_content"])

        except Exception as e:
            logger.warning(
                f"SpecialPackExecutors: Failed to get intents from events: {e}"
            )

        return extracted_intents, file_contents

    async def _extract_intents_from_files(
        self,
        profile_id: str,
        message_id: str,
        message: str,
        file_contents: List[str],
    ) -> List[str]:
        """
        Extract intents from files using SeedExtractor

        Args:
            profile_id: User profile ID
            message_id: Message ID
            message: User message
            file_contents: List of file contents

        Returns:
            List of extracted intent texts
        """
        try:
            from ...capabilities.semantic_seeds.services.seed_extractor import (
                SeedExtractor,
            )
            from backend.app.shared.llm_provider_helper import (
                create_llm_provider_manager,
                get_llm_provider_from_settings,
            )

            config = self.config_store.get_or_create_config(profile_id)
            llm_manager = create_llm_provider_manager(
                openai_key=config.agent_backend.openai_api_key,
                anthropic_key=config.agent_backend.anthropic_api_key,
                vertex_api_key=config.agent_backend.vertex_api_key,
                vertex_project_id=config.agent_backend.vertex_project_id,
                vertex_location=config.agent_backend.vertex_location,
            )
            llm_provider = get_llm_provider_from_settings(llm_manager)

            if llm_provider:
                extractor = SeedExtractor(llm_provider=llm_provider)
                combined_content = "\n\n".join(file_contents[:3])

                seeds = await extractor.extract_seeds_from_content(
                    user_id=profile_id,
                    content=combined_content,
                    source_type="conversation",
                    source_id=message_id,
                    source_context=message,
                )

                return [
                    seed.get("text", "")
                    for seed in seeds
                    if seed.get("type") in ["intent", "project"]
                ]

        except Exception as e:
            logger.warning(
                f"SpecialPackExecutors: Failed to extract seeds from files: {e}"
            )

        return []

    async def _extract_intents_from_message(
        self, profile_id: str, message_id: str, message: str
    ) -> List[str]:
        """
        Extract intents from message using SeedExtractor

        Args:
            profile_id: User profile ID
            message_id: Message ID
            message: User message

        Returns:
            List of extracted intent texts
        """
        try:
            from ...capabilities.semantic_seeds.services.seed_extractor import (
                SeedExtractor,
            )
            from backend.app.shared.llm_provider_helper import (
                create_llm_provider_manager,
                get_llm_provider_from_settings,
            )

            config = self.config_store.get_or_create_config(profile_id)
            llm_manager = create_llm_provider_manager(
                openai_key=config.agent_backend.openai_api_key,
                anthropic_key=config.agent_backend.anthropic_api_key,
                vertex_api_key=config.agent_backend.vertex_api_key,
                vertex_project_id=config.agent_backend.vertex_project_id,
                vertex_location=config.agent_backend.vertex_location,
            )
            llm_provider = get_llm_provider_from_settings(llm_manager)

            if llm_provider:
                extractor = SeedExtractor(llm_provider=llm_provider)
                seeds = await extractor.extract_seeds_from_content(
                    user_id=profile_id,
                    content=message,
                    source_type="conversation",
                    source_id=message_id,
                    source_context=message,
                )
                extracted_intents = [
                    seed.get("text", "")
                    for seed in seeds
                    if seed.get("type") in ["intent", "project"]
                ]
                logger.info(
                    f"SpecialPackExecutors: Extracted {len(extracted_intents)} intents from message content"
                )
                return extracted_intents

        except Exception as e:
            logger.warning(
                f"SpecialPackExecutors: Failed to extract seeds from message: {e}",
                exc_info=True,
            )

        return []

    def _build_execution_result(
        self,
        extracted_intents: List[str],
        files: List[str],
        file_contents: List[str],
    ) -> Dict[str, Any]:
        """
        Build execution result from extracted intents

        Args:
            extracted_intents: List of extracted intent texts
            files: List of file IDs
            file_contents: List of file contents

        Returns:
            Execution result dict
        """
        if files:
            title = f"Extracted {len(extracted_intents)} intents from {len(files)} file(s)"
            summary = f"Found {len(extracted_intents)} potential intents or projects from files"
            result_message = f"Extracted {len(extracted_intents)} intents from uploaded files"
        else:
            title = f"Extracted {len(extracted_intents)} intents from message"
            summary = f"Found {len(extracted_intents)} potential intents or projects from message"
            result_message = f"Extracted {len(extracted_intents)} intents from message"

        return {
            "title": title,
            "summary": summary,
            "message": result_message,
            "intents": extracted_intents[:5],
            "files_processed": len(files),
            "source": "files" if files else "message",
        }
