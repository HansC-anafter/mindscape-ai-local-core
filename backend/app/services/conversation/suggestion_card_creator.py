"""
Suggestion Card Creator

Creates suggestion cards for soft_write and external_write tasks.
"""

import logging
import sys
from typing import Dict, Any, Optional
from datetime import datetime
import uuid

from ...models.workspace import Task, TaskStatus, TimelineItemType
from .task_events_emitter import TaskEventsEmitter

logger = logging.getLogger(__name__)


class SuggestionCardCreator:
    """
    Creates suggestion cards for tasks

    Responsibilities:
    - Validate playbook exists before creating suggestion
    - Check user preferences for auto-suggest
    - Check for existing suggestion tasks to avoid duplicates
    - Create suggestion task with LLM analysis
    - Handle background playbook marking
    """

    def __init__(
        self,
        tasks_store,
        playbook_service=None,
        message_generator=None,
        default_locale: str = "en",
    ):
        """
        Initialize SuggestionCardCreator

        Args:
            tasks_store: TasksStore instance
            playbook_service: Optional PlaybookService instance
            message_generator: Optional MessageGenerator instance
            default_locale: Default locale for i18n
        """
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
        """
        Create suggestion card for soft_write task

        Args:
            task_plan: Task plan
            workspace_id: Workspace ID
            message_id: Message ID
            event_emitter: TaskEventsEmitter instance

        Returns:
            Dict with task_id, timeline_item_id, pack_id, or None if failed
        """
        try:
            from ...services.i18n_service import get_i18n_service

            i18n = get_i18n_service(default_locale=self.default_locale)

            pack_id = task_plan.pack_id

            # Validate playbook exists
            validation_result = await self._validate_playbook(pack_id, workspace_id)
            if not validation_result["is_valid"]:
                logger.warning(
                    f"SuggestionCardCreator: Skipping suggestion task creation for invalid pack_id: {pack_id}. "
                    f"Reason: {validation_result.get('reason', 'unknown')}"
                )
                return {
                    "task_id": None,
                    "timeline_item_id": None,
                    "pack_id": pack_id,
                    "skipped": True,
                    "reason": validation_result.get("reason", "invalid_playbook_code"),
                }

            # Check user preference
            preference_result = await self._check_user_preference(
                task_plan, workspace_id
            )
            if not preference_result["should_auto_suggest"]:
                logger.info(
                    f"SuggestionCardCreator: Skipping suggestion task creation for pack {pack_id} "
                    f"(auto_suggest disabled by user preference)"
                )
                return {
                    "task_id": None,
                    "timeline_item_id": None,
                    "pack_id": pack_id,
                    "skipped": True,
                    "reason": "auto_suggest_disabled",
                }

            # Check for existing suggestion tasks
            existing_tasks = self.tasks_store.find_existing_suggestion_tasks(
                workspace_id=workspace_id,
                pack_id=pack_id,
                created_within_hours=1,
            )

            if existing_tasks:
                if not self._should_create_new_suggestion_task(existing_tasks, task_plan):
                    existing_task = existing_tasks[0]
                    logger.info(
                        f"SuggestionCardCreator: Reusing existing suggestion task {existing_task.id} for pack {pack_id}"
                    )
                    return {
                        "task_id": existing_task.id,
                        "timeline_item_id": None,
                        "pack_id": pack_id,
                        "is_duplicate": True,
                    }

            # Prepare LLM analysis
            llm_analysis = self._prepare_llm_analysis(task_plan)

            # Create suggestion task
            suggestion_task = Task(
                id=str(uuid.uuid4()),
                workspace_id=workspace_id,
                message_id=message_id,
                execution_id=None,
                pack_id=pack_id,
                task_type="suggestion",
                status=TaskStatus.PENDING,
                params=task_plan.params,
                result={
                    "suggestion": True,
                    "pack_id": pack_id,
                    "requires_cta": True,
                    "llm_analysis": llm_analysis,
                },
                created_at=datetime.utcnow(),
                started_at=None,
                completed_at=None,
                error=None,
            )
            self.tasks_store.create_task(suggestion_task)
            logger.info(
                f"SuggestionCardCreator: Created suggestion task {suggestion_task.id} (status=PENDING) for {pack_id}"
            )

            # Emit task created event
            event_emitter.emit_task_created(
                task_id=suggestion_task.id,
                pack_id=pack_id,
                status=suggestion_task.status.value,
                task_type=suggestion_task.task_type,
                workspace_id=workspace_id,
            )

            return {
                "task_id": suggestion_task.id,
                "timeline_item_id": None,
                "pack_id": pack_id,
            }

        except Exception as e:
            logger.error(f"SuggestionCardCreator: Failed to create suggestion card: {e}", exc_info=True)
            return None

    async def create_playbook_suggestion(
        self,
        playbook_code: str,
        playbook_context: Dict[str, Any],
        workspace_id: str,
        message_id: str,
        event_emitter: TaskEventsEmitter,
    ) -> Dict[str, Any]:
        """
        Create suggestion card for soft_write playbook

        Args:
            playbook_code: Playbook code
            playbook_context: Playbook context
            workspace_id: Workspace ID
            message_id: Message ID
            event_emitter: TaskEventsEmitter instance

        Returns:
            Dict with status and task_id
        """
        try:
            from ...services.i18n_service import get_i18n_service

            i18n = get_i18n_service(default_locale=self.default_locale)

            # Extract LLM analysis from playbook_context
            llm_analysis = playbook_context.get("llm_analysis", {})
            if not llm_analysis and isinstance(playbook_context.get("context"), dict):
                llm_analysis = playbook_context.get("context", {}).get("llm_analysis", {})

            # Check if this is a background playbook
            background_playbooks = ["habit_learning"]
            is_background_playbook = playbook_code.lower() in [
                p.lower() for p in background_playbooks
            ]

            # Ensure llm_analysis has all required fields
            llm_analysis = self._normalize_llm_analysis(llm_analysis, is_background_playbook)

            # Create suggestion task
            suggestion_task = Task(
                id=str(uuid.uuid4()),
                workspace_id=workspace_id,
                message_id=message_id,
                execution_id=None,
                pack_id=playbook_code,
                task_type="suggestion",
                status=TaskStatus.PENDING,
                params={
                    "playbook_code": playbook_code,
                    "context": playbook_context,
                    "llm_analysis": llm_analysis,
                },
                result={
                    "suggestion": True,
                    "playbook_code": playbook_code,
                    "requires_cta": True,
                    "llm_analysis": llm_analysis,
                },
                created_at=datetime.utcnow(),
                started_at=None,
                completed_at=None,
                error=None,
            )
            self.tasks_store.create_task(suggestion_task)

            # Emit task created event
            event_emitter.emit_task_created(
                task_id=suggestion_task.id,
                pack_id=playbook_code,
                status=suggestion_task.status.value,
                task_type=suggestion_task.task_type,
                workspace_id=workspace_id,
            )

            return {
                "status": "suggestion",
                "playbook_code": playbook_code,
                "task_id": suggestion_task.id,
                "timeline_item_id": None,
                "message": i18n.t("conversation_orchestrator", "suggestion.add_to_mindscape"),
            }

        except Exception as e:
            logger.error(f"SuggestionCardCreator: Failed to create playbook suggestion: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}

    async def _validate_playbook(
        self, pack_id: str, workspace_id: str
    ) -> Dict[str, Any]:
        """
        Validate playbook exists before creating suggestion

        Args:
            pack_id: Pack ID
            workspace_id: Workspace ID

        Returns:
            Dict with is_valid and reason
        """
        if not pack_id:
            return {"is_valid": False, "reason": "empty_pack_id"}

        is_valid = False

        # Check PlaybookService first
        if self.playbook_service:
            try:
                playbook = await self.playbook_service.get_playbook(
                    playbook_code=pack_id,
                    locale=self.default_locale,
                    workspace_id=workspace_id,
                )
                if playbook:
                    is_valid = True
                    logger.info(f"SuggestionCardCreator: Pack {pack_id} validated as playbook")
            except Exception as e:
                logger.debug(f"SuggestionCardCreator: Pack {pack_id} not found in PlaybookService: {e}")

        # If not a playbook, check CapabilityRegistry
        if not is_valid:
            from ...capabilities.registry import get_registry

            registry = get_registry()
            execution_method = registry.get_execution_method(pack_id)
            if execution_method in ["playbook", "pack_executor"]:
                is_valid = True
                logger.info(
                    f"SuggestionCardCreator: Pack {pack_id} validated as capability pack (execution_method={execution_method})"
                )

        # Special cases: intent_extraction and semantic_seeds are valid
        pack_id_lower = pack_id.lower()
        if pack_id_lower in ["intent_extraction", "semantic_seeds"]:
            is_valid = True
            logger.info(f"SuggestionCardCreator: Pack {pack_id} validated as special pack")

        return {"is_valid": is_valid, "reason": None if is_valid else "invalid_playbook_code"}

    async def _check_user_preference(
        self, task_plan, workspace_id: str
    ) -> Dict[str, Any]:
        """
        Check user preference for auto-suggest

        Args:
            task_plan: Task plan
            workspace_id: Workspace ID

        Returns:
            Dict with should_auto_suggest
        """
        try:
            from ...services.stores.task_preference_store import TaskPreferenceStore
            from ...services.mindscape_store import MindscapeStore

            store = MindscapeStore()
            preference_store = TaskPreferenceStore(store.db_path)

            workspace = store.get_workspace(workspace_id)
            if workspace:
                should_auto_suggest = preference_store.should_auto_suggest(
                    workspace_id=workspace_id,
                    user_id=workspace.owner_user_id,
                    pack_id=task_plan.pack_id,
                    task_type=task_plan.task_type,
                )
                return {"should_auto_suggest": should_auto_suggest}

            return {"should_auto_suggest": True}  # Default to True if workspace not found

        except Exception as e:
            logger.warning(f"SuggestionCardCreator: Failed to check user preference: {e}")
            return {"should_auto_suggest": True}  # Default to True on error

    def _should_create_new_suggestion_task(
        self, existing_tasks: list, task_plan
    ) -> bool:
        """
        Determine if a new suggestion task should be created

        Args:
            existing_tasks: List of existing suggestion tasks
            task_plan: New task plan

        Returns:
            True if should create new task, False if duplicate exists
        """
        if not existing_tasks:
            return True

        new_params_source = task_plan.params.get("source", "") if task_plan.params else ""
        new_params_files = task_plan.params.get("files", []) if task_plan.params else []

        for existing_task in existing_tasks:
            existing_params = existing_task.params or {}
            existing_source = existing_params.get("source", "")
            existing_files = existing_params.get("files", [])

            source_match = new_params_source == existing_source
            files_match = set(new_params_files) == set(existing_files)

            if source_match and files_match:
                logger.info(
                    f"SuggestionCardCreator: Found duplicate suggestion task {existing_task.id} for pack {task_plan.pack_id}, skipping creation"
                )
                return False

        return True

    def _prepare_llm_analysis(self, task_plan) -> Dict[str, Any]:
        """
        Prepare LLM analysis from task plan

        Args:
            task_plan: Task plan

        Returns:
            Normalized LLM analysis dict
        """
        llm_analysis = (
            task_plan.params.get("llm_analysis", {}) if task_plan.params else {}
        )

        background_playbooks = ["habit_learning"]
        is_background_playbook = (
            task_plan.pack_id.lower() in [p.lower() for p in background_playbooks]
            if task_plan.pack_id
            else False
        )

        return self._normalize_llm_analysis(llm_analysis, is_background_playbook)

    def _normalize_llm_analysis(
        self, llm_analysis: Dict[str, Any], is_background_playbook: bool
    ) -> Dict[str, Any]:
        """
        Normalize LLM analysis with required fields

        Args:
            llm_analysis: LLM analysis dict
            is_background_playbook: Whether this is a background playbook

        Returns:
            Normalized LLM analysis dict
        """
        if not llm_analysis or not isinstance(llm_analysis, dict):
            llm_analysis = {}

        if "confidence" not in llm_analysis:
            llm_analysis["confidence"] = 0.0

        if "reason" not in llm_analysis:
            if is_background_playbook:
                llm_analysis["reason"] = (
                    "This task will be executed automatically in the background, no LLM analysis needed"
                )
            else:
                llm_analysis["reason"] = ""

        if "content_tags" not in llm_analysis:
            llm_analysis["content_tags"] = []

        if "analysis_summary" not in llm_analysis:
            if is_background_playbook:
                llm_analysis["analysis_summary"] = "Background auto-execution task"
            else:
                llm_analysis["analysis_summary"] = ""

        if is_background_playbook:
            llm_analysis["is_background"] = True

        return llm_analysis
