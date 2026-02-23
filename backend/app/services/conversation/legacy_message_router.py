"""
Legacy Message Router

Handles the full legacy routing path (feature flag off) for
ConversationOrchestrator.route_message. Processes messages through:
file upload -> user event creation -> thread stats -> intent extraction
-> intent analysis -> multi-step workflow -> execution plan -> playbook
execution -> QA fallback -> response building.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.app.models.mindscape import MindEvent, EventActor, EventType
from backend.app.services.conversation.response_assembler import (
    serialize_events,
    collect_pending_tasks,
)
from backend.app.services.conversation.thread_stats_updater import update_thread_stats

logger = logging.getLogger(__name__)


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


class LegacyMessageRouter:
    """
    Legacy message routing implementation (feature flag off path).

    Coordinates file processing, event creation, intent extraction,
    playbook execution, QA fallback, and response assembly.
    """

    def __init__(
        self,
        store,
        identity_port,
        intent_extractor,
        intent_pipeline,
        plan_builder,
        execution_coordinator,
        qa_response_generator,
        file_processor,
        tasks_store,
        task_manager,
        default_locale: str,
    ):
        self.store = store
        self.identity_port = identity_port
        self.intent_extractor = intent_extractor
        self.intent_pipeline = intent_pipeline
        self.plan_builder = plan_builder
        self.execution_coordinator = execution_coordinator
        self.qa_response_generator = qa_response_generator
        self.file_processor = file_processor
        self.tasks_store = tasks_store
        self.task_manager = task_manager
        self.default_locale = default_locale

    async def route(
        self,
        workspace_id: str,
        profile_id: str,
        message: str,
        files: List[str],
        mode: str,
        project_id: Optional[str],
        workspace: Any,
        thread_id: Optional[str],
    ) -> Dict[str, Any]:
        """
        Route a message through the legacy pipeline.

        Args:
            workspace_id: Workspace ID.
            profile_id: User profile ID.
            message: User message text.
            files: List of file IDs.
            mode: Interaction mode.
            project_id: Optional project ID (may be updated by project detection).
            workspace: Workspace object.
            thread_id: Optional conversation thread ID.

        Returns:
            Response dict with workspace_id, display_events,
            triggered_playbook, pending_tasks.
        """
        # Ensure thread
        if not thread_id:
            from backend.features.workspace.chat.streaming.generator import (
                _get_or_create_default_thread,
            )

            thread_id = _get_or_create_default_thread(workspace_id, self.store)

        # Project detection
        from backend.app.services.conversation.project_detector_handler import (
            detect_and_handle_project,
        )

        resolved_project_id = await detect_and_handle_project(
            store=self.store,
            workspace=workspace,
            workspace_id=workspace_id,
            profile_id=profile_id,
            message=message,
            project_id=project_id,
        )
        if resolved_project_id:
            project_id = resolved_project_id

        # File processing
        file_document_ids = await self._process_files(workspace_id, profile_id, files)

        # Create user event
        user_event = self._create_user_event(
            workspace_id,
            profile_id,
            project_id,
            thread_id,
            message,
            files,
            mode,
            file_document_ids,
        )
        self.store.create_event(user_event)
        logger.info(
            "Created user event: %s, files: %d, file_document_ids: %d, thread_id=%s",
            user_event.id,
            len(files),
            len(file_document_ids),
            thread_id,
        )

        # Update thread statistics
        await update_thread_stats(self.store, workspace_id, thread_id)

        # Intent extraction (LLM-based, pre-pipeline)
        message_with_context = await self._extract_intent(
            workspace_id,
            profile_id,
            project_id,
            message,
            user_event,
        )

        # Intent pipeline analysis (rule-based)
        intent_result = await self._run_intent_pipeline(
            workspace_id,
            profile_id,
            project_id,
            message,
            files,
            mode,
        )

        triggered_playbook = None
        assistant_response = None

        # Multi-step workflow handling
        if intent_result and intent_result.is_multi_step:
            assistant_response = await self._handle_multi_step_workflow(
                workspace_id,
                profile_id,
                project_id,
                thread_id,
                message,
                files,
                mode,
                user_event,
                intent_result,
            )

        # Execution plan
        execution_results = await self._execute_plan(
            workspace_id,
            profile_id,
            project_id,
            message,
            files,
            user_event,
            thread_id,
        )

        # Playbook execution or QA fallback
        if intent_result and intent_result.selected_playbook_code:
            triggered_playbook, assistant_response = await self._execute_playbook(
                workspace_id,
                profile_id,
                project_id,
                user_event,
                intent_result,
            )
        else:
            assistant_response = await self._handle_qa_fallback(
                workspace_id,
                profile_id,
                project_id,
                message,
                mode,
                user_event,
                intent_result,
                workspace,
                thread_id,
            )

        # Build response
        return await self._build_response(
            workspace_id,
            triggered_playbook,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _process_files(
        self,
        workspace_id: str,
        profile_id: str,
        files: List[str],
    ) -> List[str]:
        """Process uploaded files and return document IDs."""
        if not files:
            return []
        ctx = await self.identity_port.get_current_context(
            workspace_id=workspace_id, profile_id=profile_id
        )
        return await self.file_processor.process_files_in_chat_with_ctx(
            ctx=ctx, files=files
        )

    def _create_user_event(
        self,
        workspace_id: str,
        profile_id: str,
        project_id: Optional[str],
        thread_id: Optional[str],
        message: str,
        files: List[str],
        mode: str,
        file_document_ids: List[str],
    ) -> MindEvent:
        """Create a user MindEvent for the incoming message."""
        return MindEvent(
            id=str(uuid.uuid4()),
            timestamp=_utc_now(),
            actor=EventActor.USER,
            channel="local_workspace",
            profile_id=profile_id,
            project_id=project_id,
            workspace_id=workspace_id,
            thread_id=thread_id,
            event_type=EventType.MESSAGE,
            payload={"message": message, "files": files, "mode": mode},
            entity_ids=[],
            metadata={
                "file_document_ids": (file_document_ids if file_document_ids else None)
            },
        )

    async def _extract_intent(
        self,
        workspace_id: str,
        profile_id: str,
        project_id: Optional[str],
        message: str,
        user_event: MindEvent,
    ) -> str:
        """
        Run LLM-based intent extraction and update event metadata.

        Returns message_with_context (enriched with project context if applicable).
        """
        ctx = await self.identity_port.get_current_context(
            workspace_id=workspace_id, profile_id=profile_id
        )

        message_with_context = message
        if project_id:
            from backend.app.services.project.project_manager import ProjectManager

            project_manager = ProjectManager(self.store)
            project = await project_manager.get_project(
                project_id, workspace_id=workspace_id
            )
            if project:
                project_context = (
                    f"\n[Project Context]\n"
                    f"Project: {project.title} ({project.type})\n"
                    f"Project ID: {project.id}\n\n"
                    f"[User Message]\n{message}\n"
                )
                message_with_context = project_context
                logger.info("Added Project context for project: %s", project.id)

        logger.info("Running intent extraction (pre-pipeline)")
        timeline_item = await self.intent_extractor.extract_and_create_timeline_item(
            ctx=ctx,
            message=message_with_context,
            message_id=user_event.id,
            locale=self.default_locale,
        )
        logger.info(
            "Intent extraction completed, result: %s", timeline_item is not None
        )

        if timeline_item:
            intents_list = (
                timeline_item.data.get("intents", []) if timeline_item.data else []
            )
            themes_list = (
                timeline_item.data.get("themes", []) if timeline_item.data else []
            )
            await self.intent_extractor.update_event_metadata(
                event_id=user_event.id, intents=intents_list, themes=themes_list
            )

        return message_with_context

    async def _run_intent_pipeline(
        self,
        workspace_id: str,
        profile_id: str,
        project_id: Optional[str],
        message: str,
        files: List[str],
        mode: str,
    ):
        """Run rule-based intent pipeline analysis."""
        intent_result = None
        try:
            intent_result = await self.intent_pipeline.analyze(
                user_input=message,
                profile_id=profile_id,
                channel="local_workspace",
                project_id=project_id,
                workspace_id=workspace_id,
                context={
                    "files": files,
                    "workspace_id": workspace_id,
                    "mode": mode,
                    "uploaded_files": files,
                },
            )
            if intent_result:
                logger.info(
                    "Intent analysis result: selected_playbook_code=%s, is_multi_step=%s",
                    intent_result.selected_playbook_code,
                    intent_result.is_multi_step,
                )
            else:
                logger.warning("Intent analysis returned None")
        except Exception as e:
            logger.warning("Intent analysis failed, falling back to QA: %s", str(e))

        return intent_result

    async def _handle_multi_step_workflow(
        self,
        workspace_id: str,
        profile_id: str,
        project_id: Optional[str],
        thread_id: Optional[str],
        message: str,
        files: List[str],
        mode: str,
        user_event: MindEvent,
        intent_result,
    ) -> Optional[str]:
        """Handle multi-step workflow execution."""
        logger.info(
            "Detected multi-step workflow with %d steps",
            len(intent_result.workflow_steps),
        )
        assistant_response = None
        try:
            from backend.app.services.workflow_orchestrator import (
                WorkflowOrchestrator,
            )

            workflow_response = await self.execution_coordinator.message_generator.generate_workflow_response(
                user_input=message,
                intent_result=intent_result,
                context={
                    "files": files,
                    "uploaded_files": files,
                    "workspace_id": workspace_id,
                    "mode": mode,
                },
                locale=self.default_locale,
            )

            handoff_plan = workflow_response.get("handoff_plan")
            assistant_response = workflow_response.get("message")

            if handoff_plan:
                logger.info(
                    "Executing HandoffPlan with %d steps", len(handoff_plan.steps)
                )
                orchestrator = WorkflowOrchestrator()
                workflow_result = await orchestrator.execute_workflow(handoff_plan)

                result_summary = await self.execution_coordinator.message_generator.generate_workflow_summary(
                    workflow_result=workflow_result,
                    handoff_plan=handoff_plan,
                    locale=self.default_locale,
                )
                assistant_response = result_summary or assistant_response

                # Create assistant event for workflow result
                assistant_event = MindEvent(
                    id=str(uuid.uuid4()),
                    timestamp=_utc_now(),
                    actor=EventActor.ASSISTANT,
                    channel="local_workspace",
                    profile_id=profile_id,
                    project_id=project_id,
                    workspace_id=workspace_id,
                    thread_id=thread_id,
                    event_type=EventType.MESSAGE,
                    payload={
                        "message": assistant_response,
                        "response_to": user_event.id,
                        "workflow_result": workflow_result,
                    },
                    entity_ids=[],
                    metadata={
                        "handoff_plan": handoff_plan.dict(),
                        "workflow_steps": len(handoff_plan.steps),
                        "is_multi_step_workflow": True,
                    },
                )
                self.store.create_event(assistant_event)

                # Update thread statistics
                await update_thread_stats(self.store, workspace_id, thread_id)

                # Update task execution context if applicable
                from backend.app.services.stores.tasks_store import TasksStore

                tasks_store = TasksStore(db_path=self.store.db_path)
                task = tasks_store.get_task_by_execution_id(user_event.id)
                if task:
                    if not task.execution_context:
                        task.execution_context = {}
                    task.execution_context["workflow_result"] = workflow_result
                    task.execution_context["handoff_plan"] = handoff_plan.dict()
                    tasks_store.update_task(task)

                logger.info(
                    "Created assistant event for multi-step workflow: %s",
                    assistant_event.id,
                )

        except Exception as e:
            logger.error("Failed to execute multi-step workflow: %s", e, exc_info=True)
            assistant_response = (
                f"I understand your request, but encountered an error "
                f"executing the workflow: {str(e)}"
            )

        return assistant_response

    async def _execute_plan(
        self,
        workspace_id: str,
        profile_id: str,
        project_id: Optional[str],
        message: str,
        files: List[str],
        user_event: MindEvent,
        thread_id: Optional[str],
    ) -> Dict[str, Any]:
        """Generate and execute the execution plan."""
        execution_plan = await self.plan_builder.generate_execution_plan(
            message=message,
            files=files,
            workspace_id=workspace_id,
            profile_id=profile_id,
            message_id=user_event.id,
            use_llm=True,
            thread_id=thread_id,
        )
        logger.info("Generated execution plan with %d tasks", len(execution_plan.tasks))

        execution_results = await self.execution_coordinator.execute_plan(
            execution_plan=execution_plan,
            workspace_id=workspace_id,
            profile_id=profile_id,
            message_id=user_event.id,
            files=files,
            message=message,
            project_id=project_id,
        )
        logger.info(
            "Execution plan completed - executed: %d, suggestions: %d, skipped: %d",
            len(execution_results.get("executed_tasks", [])),
            len(execution_results.get("suggestion_cards", [])),
            len(execution_results.get("skipped_tasks", [])),
        )
        return execution_results

    async def _execute_playbook(
        self,
        workspace_id: str,
        profile_id: str,
        project_id: Optional[str],
        user_event: MindEvent,
        intent_result,
    ) -> tuple:
        """Execute the selected playbook and return (triggered_playbook, response)."""
        triggered_playbook = None
        assistant_response = None

        logger.info("Executing playbook: %s", intent_result.selected_playbook_code)
        playbook_result = await self.execution_coordinator.execute_playbook(
            playbook_code=intent_result.selected_playbook_code,
            playbook_context=intent_result.playbook_context,
            workspace_id=workspace_id,
            profile_id=profile_id,
            message_id=user_event.id,
            project_id=project_id,
        )

        status = playbook_result.get("status")
        if status == "started":
            triggered_playbook = {
                "playbook_code": intent_result.selected_playbook_code,
                "execution_id": playbook_result.get("execution_id"),
                "context": intent_result.playbook_context,
                "status": "started",
                "message": playbook_result.get("message", ""),
            }
            assistant_response = playbook_result.get("message")
        elif status == "suggestion":
            assistant_response = playbook_result.get("message")
        elif status == "skipped":
            assistant_response = playbook_result.get("message")
        elif status == "failed":
            triggered_playbook = {
                "playbook_code": intent_result.selected_playbook_code,
                "context": intent_result.playbook_context,
                "status": "failed",
                "error": playbook_result.get("error"),
            }
            assistant_response = playbook_result.get("message")

        return triggered_playbook, assistant_response

    async def _handle_qa_fallback(
        self,
        workspace_id: str,
        profile_id: str,
        project_id: Optional[str],
        message: str,
        mode: str,
        user_event: MindEvent,
        intent_result,
        workspace: Any,
        thread_id: Optional[str],
    ) -> Optional[str]:
        """Handle QA response when no playbook was selected."""
        if not intent_result:
            logger.warning(
                "No playbook selected: intent_result is None "
                "(intent analysis may have failed)"
            )
        elif not intent_result.selected_playbook_code:
            logger.warning(
                "No playbook selected: intent_result.selected_playbook_code "
                "is empty. Intent analysis completed but no playbook matched."
            )
            logger.debug("Intent result details: %s", intent_result)

        mode_lower = mode.lower() if mode else ""
        disable_qa = mode_lower in ["execution", "mixed"]

        if disable_qa:
            return await self._respond_no_playbook(
                workspace_id,
                profile_id,
                thread_id,
                mode,
                user_event,
            )

        # QA mode enabled (conversational mode)
        logger.info("Using QA mode (no playbook selected, mode: %s)", mode)
        qa_result = await self.qa_response_generator.generate_response(
            workspace_id=workspace_id,
            profile_id=profile_id,
            message=message,
            message_id=user_event.id,
            project_id=project_id,
            workspace=workspace,
            thread_id=thread_id,
        )
        assistant_response = qa_result.get("response")
        assistant_event = qa_result.get("event")

        if assistant_response:
            logger.info(
                "Generated assistant response: %s... (length: %d)",
                assistant_response[:100],
                len(assistant_response),
            )
        else:
            logger.warning("Assistant response is empty or None")

        if assistant_event:
            logger.info(
                "Created assistant event: %s, timestamp: %s",
                assistant_event.id,
                assistant_event.timestamp,
            )
        else:
            logger.warning("Assistant event is None")

        return assistant_response

    async def _respond_no_playbook(
        self,
        workspace_id: str,
        profile_id: str,
        thread_id: Optional[str],
        mode: str,
        user_event: MindEvent,
    ) -> str:
        """Generate a no-playbook-matched response in execution/mixed mode."""
        logger.info("No playbook selected - QA mode is disabled (mode: %s)", mode)
        from backend.app.services.i18n_service import get_i18n_service

        i18n = get_i18n_service(default_locale=self.default_locale)
        assistant_response = i18n.t(
            "conversation_orchestrator",
            "no_playbook_matched",
            default=(
                "I couldn't find a suitable playbook for your request. "
                "Please try rephrasing your request or specify which "
                "playbook you'd like to use."
            ),
        )

        assistant_event = MindEvent(
            id=str(uuid.uuid4()),
            timestamp=_utc_now(),
            actor=EventActor.ASSISTANT,
            channel="local_workspace",
            profile_id=profile_id,
            workspace_id=workspace_id,
            thread_id=thread_id,
            event_type=EventType.MESSAGE,
            payload={"message": assistant_response},
            entity_ids=[],
            metadata={
                "no_playbook_matched": True,
                "qa_mode_disabled": True,
                "mode": mode,
            },
        )
        self.store.create_event(assistant_event)
        logger.info(
            "Created assistant event (no playbook matched): %s", assistant_event.id
        )

        return assistant_response

    async def _build_response(
        self,
        workspace_id: str,
        triggered_playbook: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Assemble the final API response dict."""
        # Small delay to ensure events are persisted
        await asyncio.sleep(0.1)

        recent_events = self.store.get_events_by_workspace(
            workspace_id=workspace_id, limit=20
        )
        logger.info("Retrieved %d events from workspace", len(recent_events))

        assistant_events = [e for e in recent_events if e.actor == EventActor.ASSISTANT]
        logger.info("Found %d assistant events in recent events", len(assistant_events))

        # Check running tasks status
        running_tasks_list = self.tasks_store.list_running_tasks(workspace_id)
        for running_task in running_tasks_list:
            if running_task.execution_id:
                await self.task_manager.check_and_update_task_status(
                    task=running_task,
                    execution_id=running_task.execution_id,
                    playbook_code=running_task.pack_id,
                )

        pending_tasks = collect_pending_tasks(self.tasks_store, workspace_id)
        display_events = serialize_events(recent_events)

        return {
            "workspace_id": workspace_id,
            "display_events": display_events,
            "triggered_playbook": triggered_playbook,
            "pending_tasks": pending_tasks,
        }
