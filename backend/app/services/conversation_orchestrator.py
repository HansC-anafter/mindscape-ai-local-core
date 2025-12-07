"""
Conversation Orchestrator Service

Central coordinator for all workspace interactions.

MODULARIZATION POLICY:
This file serves as a thin coordinator layer. All implementation logic MUST be
delegated to specialized modules in conversation/ directory:

Module Responsibilities:
- ExecutionCoordinator: Pack/playbook execution, suggestion card creation
- TaskManager: Task lifecycle, TimelineItem creation, status updates
- CTAHandler: Timeline item CTA actions, soft/external write confirmations
- SuggestionActionHandler: Dynamic suggestion action execution
- QAResponseGenerator: Context-aware QA response generation
- FileProcessor: File upload, analysis, document processing
- MessageGenerator: LLM-based message generation
- PlanBuilder: Execution plan generation
- ContextBuilder: Context building for LLM prompts
- IntentExtractor: LLM-based intent extraction and timeline item creation

This orchestrator ONLY:
- Routes messages to appropriate modules
- Coordinates module interactions
- Formats responses for API

DO NOT add implementation logic directly in this file.
All new features must be implemented in appropriate modules and delegated here.
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
import uuid

from backend.app.models.mindscape import MindEvent, EventType, EventActor
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.intent_analyzer import IntentPipeline
from backend.app.services.playbook_runner import PlaybookRunner
from backend.app.services.i18n_service import get_i18n_service
from backend.app.services.stores.tasks_store import TasksStore
from backend.app.services.stores.timeline_items_store import TimelineItemsStore
from backend.app.services.stores.artifacts_store import ArtifactsStore
from backend.app.services.conversation.plan_builder import PlanBuilder
from backend.app.services.conversation.task_manager import TaskManager
from backend.app.services.conversation.cta_handler import CTAHandler
from backend.app.services.conversation.file_processor import FileProcessor
from backend.app.services.conversation.suggestion_action_handler import SuggestionActionHandler
from backend.app.services.conversation.execution_coordinator import ExecutionCoordinator
from backend.app.services.conversation.qa_response_generator import QAResponseGenerator
from backend.app.services.conversation.message_generator import MessageGenerator
from backend.app.services.conversation.intent_extractor import IntentExtractor
from backend.app.core.execution_context import ExecutionContext
from backend.app.core.ports.identity_port import IdentityPort
from backend.app.core.ports.intent_registry_port import IntentRegistryPort
from backend.app.shared.llm_provider_helper import get_llm_provider_from_settings

logger = logging.getLogger(__name__)


class ConversationOrchestrator:
    """
    Conversation Orchestrator - central coordinator for workspace interactions

    Thin wrapper around existing IntentPipeline and PlaybookRunner,
    adding data synchronization logic for timeline_items and tasks tables.
    """

    def __init__(
        self,
        store: MindscapeStore,
        intent_pipeline: IntentPipeline,
        playbook_runner: PlaybookRunner,
        default_locale: str = "zh-TW",
        identity_port: Optional[IdentityPort] = None,
        intent_registry: Optional[IntentRegistryPort] = None
    ):
        self.store = store
        self.intent_pipeline = intent_pipeline
        self.playbook_runner = playbook_runner
        self.i18n = get_i18n_service(default_locale=default_locale)
        self.default_locale = default_locale

        if identity_port is None:
            from backend.app.adapters.local.local_identity_adapter import LocalIdentityAdapter
            identity_port = LocalIdentityAdapter()

        if intent_registry is None:
            from backend.app.adapters.local.local_intent_registry_adapter import LocalIntentRegistryAdapter
            intent_registry = LocalIntentRegistryAdapter(default_locale=default_locale)

        self.identity_port = identity_port
        self.intent_registry = intent_registry

        self.tasks_store = TasksStore(store.db_path)
        self.timeline_items_store = TimelineItemsStore(store.db_path)
        self.artifacts_store = ArtifactsStore(store.db_path)

        self.plan_builder = PlanBuilder(store=store, default_locale=default_locale)
        self.task_manager = TaskManager(
            tasks_store=self.tasks_store,
            timeline_items_store=self.timeline_items_store,
            plan_builder=self.plan_builder,
            playbook_runner=playbook_runner,
            default_locale=default_locale,
            artifacts_store=self.artifacts_store,
            store=store
        )
        self.cta_handler = CTAHandler(
            store=store,
            tasks_store=self.tasks_store,
            timeline_items_store=self.timeline_items_store,
            plan_builder=self.plan_builder,
            default_locale=default_locale
        )
        self.file_processor = FileProcessor(store=store)
        self.intent_extractor = IntentExtractor(
            store=store,
            timeline_items_store=self.timeline_items_store,
            intent_registry=intent_registry,
            default_locale=default_locale
        )
        self.suggestion_action_handler = SuggestionActionHandler(
            store=store,
            playbook_runner=playbook_runner,
            task_manager=self.task_manager,
            execution_coordinator=None,  # Will be set after execution_coordinator is created
            default_locale=default_locale
        )

        from backend.app.services.agent_runner import LLMProviderManager
        from backend.app.services.system_settings_store import SystemSettingsStore
        import os
        openai_key = os.getenv("OPENAI_API_KEY")
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")

        # Get Vertex AI configuration from system settings
        settings_store = SystemSettingsStore()
        service_account_setting = settings_store.get_setting("vertex_ai_service_account_json")
        vertex_project_setting = settings_store.get_setting("vertex_ai_project_id")
        vertex_location_setting = settings_store.get_setting("vertex_ai_location")

        # Get Vertex AI config - handle empty strings as None
        vertex_service_account_json = None
        if service_account_setting and service_account_setting.value:
            val = str(service_account_setting.value).strip()
            vertex_service_account_json = val if val else None
        if not vertex_service_account_json:
            vertex_service_account_json = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

        vertex_project_id = None
        if vertex_project_setting and vertex_project_setting.value:
            val = str(vertex_project_setting.value).strip()
            vertex_project_id = val if val else None
        if not vertex_project_id:
            vertex_project_id = os.getenv("GOOGLE_CLOUD_PROJECT")

        vertex_location = None
        if vertex_location_setting and vertex_location_setting.value:
            val = str(vertex_location_setting.value).strip()
            vertex_location = val if val else None
        if not vertex_location:
            vertex_location = os.getenv("VERTEX_LOCATION", "us-central1")

        from backend.app.shared.llm_provider_helper import create_llm_provider_manager

        logger.info(f"ConversationOrchestrator: Vertex AI config: service_account={'set' if vertex_service_account_json else 'not set'}, project_id={vertex_project_id}, location={vertex_location}")

        llm_manager = create_llm_provider_manager(
            openai_key=openai_key,
            anthropic_key=anthropic_key,
            vertex_api_key=vertex_service_account_json,
            vertex_project_id=vertex_project_id,
            vertex_location=vertex_location
        )
        llm_provider = get_llm_provider_from_settings(llm_manager)

        message_generator = MessageGenerator(
            llm_provider=llm_provider,
            default_locale=default_locale
        )

        from backend.app.services.playbook_service import PlaybookService
        playbook_service = PlaybookService(store=store)

        # Ensure we use the same PlaybookRunner instance as API routes to share active_conversations
        # Import the shared instance from playbook_execution module
        from backend.app.routes.core.playbook_execution import playbook_runner as shared_playbook_runner
        # Update playbook_runner reference to use shared instance
        playbook_runner = shared_playbook_runner

        self.execution_coordinator = ExecutionCoordinator(
            store=store,
            tasks_store=self.tasks_store,
            timeline_items_store=self.timeline_items_store,
            task_manager=self.task_manager,
            plan_builder=self.plan_builder,
            playbook_runner=playbook_runner,
            message_generator=message_generator,
            default_locale=default_locale,
            playbook_service=playbook_service
        )

        # Update SuggestionActionHandler with ExecutionCoordinator reference
        self.suggestion_action_handler.execution_coordinator = self.execution_coordinator

        self.qa_response_generator = QAResponseGenerator(
            store=store,
            timeline_items_store=self.timeline_items_store,
            default_locale=default_locale
        )

    async def route_message(
        self,
        workspace_id: str,
        profile_id: str,
        message: str,
        files: List[str],
        mode: str,
        project_id: Optional[str] = None,
        workspace: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Route message through existing pipeline and sync derived data

        Args:
            workspace_id: Workspace ID
            profile_id: User profile ID
            message: User message text
            files: List of file IDs
            mode: Interaction mode
            project_id: Optional project ID

        Returns:
            Response dict with events, triggered_playbook, pending_tasks
        """
        try:
            # Get workspace if not provided
            if not workspace:
                workspace = self.store.get_workspace(workspace_id)

            # If no project_id, check if we need to create a Project
            if not project_id and workspace:
                from backend.app.services.project.project_manager import ProjectManager
                from backend.app.services.project.project_detector import ProjectDetector

                project_manager = ProjectManager(self.store)

                # Detect if we should create a new project
                project_detector = ProjectDetector()

                # Get recent conversation context
                recent_events = self.store.events.get_events(
                    profile_id=profile_id,
                    workspace_id=workspace_id,
                    limit=10
                )
                conversation_context = [
                    {
                        "role": "user" if e.actor == EventActor.USER else "assistant",
                        "content": e.payload.get("message", "") if e.payload else ""
                    }
                    for e in recent_events
                    if e.event_type == EventType.MESSAGE and e.payload
                ]

                project_suggestion = await project_detector.detect(
                    message=message,
                    conversation_context=conversation_context,
                    workspace=workspace
                )

                if project_suggestion and project_suggestion.mode == "project":
                    # Check if a duplicate project already exists (same type and very similar/identical title)
                    existing_projects = await project_manager.list_projects(
                        workspace_id=workspace_id,
                        state="open"
                    )
                    
                    suggested_type = project_suggestion.project_type or "general"
                    suggested_title = (project_suggestion.project_title or "").lower().strip()
                    
                    # Check for duplicates: same type AND very similar/identical title
                    # Allow different projects of same type with different titles (e.g., 
                    # "產品 Landing Page" vs "服務介紹 Landing Page" or "Python 課程" vs "JavaScript 課程")
                    duplicate_project = None
                    for existing_project in existing_projects:
                        if existing_project.type == suggested_type:
                            existing_title = existing_project.title.lower().strip()
                            # Only consider it a duplicate if titles are identical or very similar
                            # (exact match or one is a substring of the other with small differences)
                            if suggested_title == existing_title:
                                duplicate_project = existing_project
                                break
                            # Check for very close similarity (e.g., "Landing Page" vs "Landing Page v2")
                            # This is a simple check - titles that are essentially the same
                            if suggested_title and existing_title:
                                # If one title contains the other (with only version numbers or small additions)
                                # Consider them duplicates
                                title_words = set(suggested_title.split())
                                existing_words = set(existing_title.split())
                                # If 90%+ of words overlap, consider duplicate
                                if len(title_words) > 0 and len(existing_words) > 0:
                                    overlap = len(title_words & existing_words) / max(len(title_words), len(existing_words))
                                    if overlap >= 0.9 and abs(len(suggested_title) - len(existing_title)) <= 10:
                                        duplicate_project = existing_project
                                        break
                    
                    # Only create if no duplicate project exists (different projects of same type are allowed)
                    if not duplicate_project:
                        # Check confidence score to decide if we should create directly or show suggestion
                        confidence = project_suggestion.confidence or 0.5
                        HIGH_CONFIDENCE_THRESHOLD = 0.8  # High confidence: create directly
                        LOW_CONFIDENCE_THRESHOLD = 0.5  # Low confidence: don't suggest
                        
                        if confidence >= HIGH_CONFIDENCE_THRESHOLD:
                            # High confidence: create project directly
                            from backend.app.services.project.constants import DEFAULT_PROJECT_TYPE
                            project = await project_manager.create_project(
                                project_type=project_suggestion.project_type or DEFAULT_PROJECT_TYPE,
                                title=project_suggestion.project_title or "New Project",
                                workspace_id=workspace_id,
                                flow_id=project_suggestion.flow_id or "general_flow",
                                initiator_user_id=profile_id
                            )

                            # Project PM assignment
                            from backend.app.services.project.project_assignment_agent import ProjectAssignmentAgent
                            assignment_agent = ProjectAssignmentAgent()
                            assignment = await assignment_agent.suggest_assignment(
                                project=project,
                                workspace=workspace
                            )

                            # Update project with assignments
                            if assignment.suggested_human_owner:
                                project.human_owner_user_id = assignment.suggested_human_owner.get("user_id")
                            if assignment.suggested_ai_pm_id:
                                project.ai_pm_id = assignment.suggested_ai_pm_id
                            await project_manager.update_project(project)

                            # Use new project_id
                            project_id = project.id

                            logger.info(f"Created new project: {project.id} for workspace: {workspace_id} (confidence: {confidence:.2f})")
                        elif confidence >= LOW_CONFIDENCE_THRESHOLD:
                            # Medium confidence: create timeline item for user confirmation
                            # Note: message_id will be set after user_event is created below
                            # We'll create the timeline item after the user event is created
                            pending_project_suggestion = {
                                "suggestion": project_suggestion,
                                "confidence": confidence
                            }
                        else:
                            # Low confidence: don't create or suggest
                            logger.debug(f"Project suggestion confidence too low ({confidence:.2f}), skipping suggestion")

            file_document_ids = []
            if files:
                ctx = await self.identity_port.get_current_context(
                    workspace_id=workspace_id,
                    profile_id=profile_id
                )
                file_document_ids = await self.file_processor.process_files_in_chat_with_ctx(
                    ctx=ctx,
                    files=files
                )

            user_event = MindEvent(
                id=str(uuid.uuid4()),
                timestamp=datetime.utcnow(),
                actor=EventActor.USER,
                channel="local_workspace",
                profile_id=profile_id,
                project_id=project_id,
                workspace_id=workspace_id,
                event_type=EventType.MESSAGE,
                payload={
                    "message": message,
                    "files": files,
                    "mode": mode
                },
                entity_ids=[],
                metadata={
                    "file_document_ids": file_document_ids if file_document_ids else None
                }
            )
            self.store.create_event(user_event)
            logger.info(f"Created user event: {user_event.id}, files: {len(files)}, file_document_ids: {len(file_document_ids)}")

            # Optional: LLM-based intent extraction (pre-pipeline)
            # This runs before rule-based IntentPipeline to provide early intent hints
            # Delegates to IntentExtractor module
            ctx = await self.identity_port.get_current_context(
                workspace_id=workspace_id,
                profile_id=profile_id
            )

            message_with_context = message
            if project_id:
                from backend.app.services.project.project_manager import ProjectManager
                project_manager = ProjectManager(self.store)
                project = await project_manager.get_project(project_id, workspace_id=workspace_id)

                if project:
                    # Build Project context string
                    # TODO: Integrate with Project Memory and Workspace Core Memory when available
                    project_context = f"""
[Project Context]
Project: {project.title} ({project.type})
Project ID: {project.id}

[User Message]
{message}
"""
                    message_with_context = project_context
                    logger.info(f"Added Project context for project: {project.id}")

            logger.info(f"ConversationOrchestrator: BEFORE calling intent_extractor.extract_and_create_timeline_item")
            import sys
            print(f"ConversationOrchestrator: BEFORE calling intent_extractor.extract_and_create_timeline_item", file=sys.stderr)
            timeline_item = await self.intent_extractor.extract_and_create_timeline_item(
                ctx=ctx,
                message=message_with_context,  # Use message with context
                message_id=user_event.id,
                locale=self.default_locale
            )
            logger.info(f"ConversationOrchestrator: AFTER intent_extractor call, result: {timeline_item is not None}")
            print(f"ConversationOrchestrator: AFTER intent_extractor call, result: {timeline_item is not None}", file=sys.stderr)

            # Update event metadata if extraction succeeded
            if timeline_item:
                intents_list = timeline_item.data.get("intents", []) if timeline_item.data else []
                themes_list = timeline_item.data.get("themes", []) if timeline_item.data else []
                await self.intent_extractor.update_event_metadata(
                    event_id=user_event.id,
                    intents=intents_list,
                    themes=themes_list
                )

            intent_result = None
            triggered_playbook = None
            assistant_response = None
            handoff_plan = None

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
                        "uploaded_files": files
                    }
                )
                if intent_result:
                    logger.info(f"Intent analysis result: selected_playbook_code={intent_result.selected_playbook_code}, is_multi_step={intent_result.is_multi_step}")
                else:
                    logger.warning("Intent analysis returned None")
            except Exception as e:
                logger.warning(f"Intent analysis failed, falling back to QA: {str(e)}")
                import sys
                print(f"Intent analysis failed: {str(e)}", file=sys.stderr)

            if intent_result and intent_result.is_multi_step:
                logger.info(f"Detected multi-step workflow with {len(intent_result.workflow_steps)} steps")
                try:
                    from backend.app.services.workflow_orchestrator import WorkflowOrchestrator
                    from backend.app.services.handoff_plan_extractor import HandoffPlanExtractor

                    workflow_response = await self.execution_coordinator.message_generator.generate_workflow_response(
                        user_input=message,
                        intent_result=intent_result,
                        context={
                            "files": files,
                            "uploaded_files": files,
                            "workspace_id": workspace_id,
                            "mode": mode
                        },
                        locale=self.default_locale
                    )

                    handoff_plan = workflow_response.get("handoff_plan")
                    assistant_response = workflow_response.get("message")

                    if handoff_plan:
                        logger.info(f"Executing HandoffPlan with {len(handoff_plan.steps)} steps")
                        orchestrator = WorkflowOrchestrator()
                        workflow_result = await orchestrator.execute_workflow(handoff_plan)

                        result_summary = await self.execution_coordinator.message_generator.generate_workflow_summary(
                            workflow_result=workflow_result,
                            handoff_plan=handoff_plan,
                            locale=self.default_locale
                        )

                        assistant_response = result_summary or assistant_response

                        assistant_event = MindEvent(
                            id=str(uuid.uuid4()),
                            timestamp=datetime.utcnow(),
                            actor=EventActor.ASSISTANT,
                            channel="local_workspace",
                            profile_id=profile_id,
                            project_id=project_id,
                            workspace_id=workspace_id,
                            event_type=EventType.MESSAGE,
                            payload={
                                "message": assistant_response,
                                "response_to": user_event.id,
                                "workflow_result": workflow_result
                            },
                            entity_ids=[],
                            metadata={
                                "handoff_plan": handoff_plan.dict(),
                                "workflow_steps": len(handoff_plan.steps),
                                "is_multi_step_workflow": True
                            }
                        )
                        self.store.create_event(assistant_event)

                        from backend.app.services.stores.tasks_store import TasksStore
                        tasks_store = TasksStore(db_path=self.store.db_path)
                        task = tasks_store.get_task_by_execution_id(user_event.id)
                        if task:
                            if not task.execution_context:
                                task.execution_context = {}
                            task.execution_context["workflow_result"] = workflow_result
                            task.execution_context["handoff_plan"] = handoff_plan.dict()
                            tasks_store.update_task(task)

                        logger.info(f"Created assistant event for multi-step workflow: {assistant_event.id}")

                except Exception as e:
                    logger.error(f"Failed to execute multi-step workflow: {e}", exc_info=True)
                    assistant_response = f"I understand your request, but encountered an error executing the workflow: {str(e)}"

            # Use LLM-based planning as primary, fallback to rule-based if LLM fails
            execution_plan = await self.plan_builder.generate_execution_plan(
                message=message,
                files=files,
                workspace_id=workspace_id,
                profile_id=profile_id,
                message_id=user_event.id,
                use_llm=True  # Priority: LLM-based analysis, fallback to rule-based
            )
            logger.info(f"ConversationOrchestrator: Generated execution plan with {len(execution_plan.tasks)} tasks")
            import sys
            print(f"ConversationOrchestrator: Generated execution plan with {len(execution_plan.tasks)} tasks", file=sys.stderr)

            execution_results = await self.execution_coordinator.execute_plan(
                execution_plan=execution_plan,
                workspace_id=workspace_id,
                profile_id=profile_id,
                message_id=user_event.id,
                files=files,
                message=message,
                project_id=project_id
            )
            logger.info(f"ConversationOrchestrator: Execution plan completed - executed: {len(execution_results.get('executed_tasks', []))}, suggestions: {len(execution_results.get('suggestion_cards', []))}, skipped: {len(execution_results.get('skipped_tasks', []))}")
            print(f"ConversationOrchestrator: Execution plan completed - executed: {len(execution_results.get('executed_tasks', []))}, suggestions: {len(execution_results.get('suggestion_cards', []))}, skipped: {len(execution_results.get('skipped_tasks', []))}", file=sys.stderr)

            if intent_result and intent_result.selected_playbook_code:
                logger.info(f"Executing playbook: {intent_result.selected_playbook_code}")
                playbook_result = await self.execution_coordinator.execute_playbook(
                    playbook_code=intent_result.selected_playbook_code,
                    playbook_context=intent_result.playbook_context,
                    workspace_id=workspace_id,
                    profile_id=profile_id,
                    message_id=user_event.id,
                    project_id=project_id
                )

                if playbook_result.get("status") == "started":
                    triggered_playbook = {
                        "playbook_code": intent_result.selected_playbook_code,
                        "execution_id": playbook_result.get("execution_id"),
                        "context": intent_result.playbook_context,
                        "status": "started",
                        "message": playbook_result.get("message", "")
                    }
                    assistant_response = playbook_result.get("message")
                elif playbook_result.get("status") == "suggestion":
                    triggered_playbook = None
                    assistant_response = playbook_result.get("message")
                elif playbook_result.get("status") == "skipped":
                    triggered_playbook = None
                    assistant_response = playbook_result.get("message")
                elif playbook_result.get("status") == "failed":
                    triggered_playbook = {
                        "playbook_code": intent_result.selected_playbook_code,
                        "context": intent_result.playbook_context,
                        "status": "failed",
                        "error": playbook_result.get("error")
                    }
                    assistant_response = playbook_result.get("message")
            else:
                # Log why no playbook was selected
                if not intent_result:
                    logger.warning("No playbook selected: intent_result is None (intent analysis may have failed)")
                elif not intent_result.selected_playbook_code:
                    logger.warning(f"No playbook selected: intent_result.selected_playbook_code is empty. Intent analysis completed but no playbook matched.")
                    logger.debug(f"Intent result details: {intent_result}")

                # Check mode to determine if QA should be disabled
                # QA is disabled only in execution and mixed modes, enabled in conversational mode
                mode_lower = mode.lower() if mode else ""
                disable_qa = mode_lower in ["execution", "mixed", "混合", "執行"]

                if disable_qa:
                    # QA mode disabled for execution/mixed modes - return message indicating no playbook matched
                    logger.info(f"No playbook selected - QA mode is disabled (mode: {mode})")
                    from backend.app.services.i18n_service import get_i18n_service

                    i18n = get_i18n_service(default_locale=self.default_locale)
                    assistant_response = i18n.t(
                        "conversation_orchestrator",
                        "no_playbook_matched",
                        default="I couldn't find a suitable playbook for your request. Please try rephrasing your request or specify which playbook you'd like to use."
                    )

                    # Create assistant event with the response
                    assistant_event = MindEvent(
                        id=str(uuid.uuid4()),
                        timestamp=datetime.utcnow(),
                        actor=EventActor.ASSISTANT,
                        channel="local_workspace",
                        profile_id=profile_id,
                        workspace_id=workspace_id,
                        event_type=EventType.MESSAGE,
                        payload={
                            "message": assistant_response
                        },
                        entity_ids=[],
                        metadata={
                            "no_playbook_matched": True,
                            "qa_mode_disabled": True,
                            "mode": mode
                        }
                    )
                    self.store.create_event(assistant_event)

                    logger.info(f"Created assistant event (no playbook matched): {assistant_event.id}")
                else:
                    # QA mode enabled for conversational mode
                    logger.info(f"Using QA mode (no playbook selected, mode: {mode})")
                    qa_result = await self.qa_response_generator.generate_response(
                        workspace_id=workspace_id,
                        profile_id=profile_id,
                        message=message,
                        message_id=user_event.id,
                        project_id=project_id,
                        workspace=workspace
                    )
                    assistant_response = qa_result.get("response")
                    assistant_event = qa_result.get("event")

                    # Log assistant response for debugging
                    if assistant_response:
                        logger.info(f"Generated assistant response: {assistant_response[:100]}... (length: {len(assistant_response)})")
                    else:
                        logger.warning("Assistant response is empty or None")

                    if assistant_event:
                        logger.info(f"Created assistant event: {assistant_event.id}, timestamp: {assistant_event.timestamp}")
                    else:
                        logger.warning("Assistant event is None")

            # Get recent events AFTER assistant event is created
            # Add a small delay to ensure event is persisted
            import asyncio
            await asyncio.sleep(0.1)  # Small delay to ensure event is saved

            recent_events = self.store.get_events_by_workspace(
                workspace_id=workspace_id,
                limit=20
            )

            # Log events for debugging
            logger.info(f"Retrieved {len(recent_events)} events from workspace")
            assistant_events = [e for e in recent_events if e.actor == EventActor.ASSISTANT]
            logger.info(f"Found {len(assistant_events)} assistant events in recent events")

            pending_tasks_list = self.tasks_store.list_pending_tasks(workspace_id)
            running_tasks_list = self.tasks_store.list_running_tasks(workspace_id)

            for running_task in running_tasks_list:
                if running_task.execution_id:
                    await self.task_manager.check_and_update_task_status(
                        task=running_task,
                        execution_id=running_task.execution_id,
                        playbook_code=running_task.pack_id
                    )

            pending_tasks_list = self.tasks_store.list_pending_tasks(workspace_id)
            running_tasks_list = self.tasks_store.list_running_tasks(workspace_id)

            pending_tasks = []
            for task in pending_tasks_list + running_tasks_list:
                pending_tasks.append({
                    "id": task.id,
                    "pack_id": task.pack_id,
                    "task_type": task.task_type,
                    "status": task.status.value,
                    "created_at": task.created_at.isoformat() if task.created_at else None
                })

            display_events_dicts = []
            for event in recent_events:
                payload = event.payload if isinstance(event.payload, dict) else {}
                entity_ids = event.entity_ids if isinstance(event.entity_ids, list) else []
                metadata = event.metadata if isinstance(event.metadata, dict) else {}

                event_dict = {
                    'id': event.id,
                    'timestamp': event.timestamp.isoformat(),
                    'actor': event.actor.value if hasattr(event.actor, 'value') else str(event.actor),
                    'channel': event.channel,
                    'profile_id': event.profile_id,
                    'project_id': event.project_id,
                    'workspace_id': event.workspace_id,
                    'event_type': event.event_type.value if hasattr(event.event_type, 'value') else str(event.event_type),
                    'payload': payload,
                    'entity_ids': entity_ids,
                    'metadata': metadata
                }
                display_events_dicts.append(event_dict)

            return {
                "workspace_id": workspace_id,
                "display_events": display_events_dicts,
                "triggered_playbook": triggered_playbook,
                "pending_tasks": pending_tasks
            }

        except Exception as e:
            logger.error(f"ConversationOrchestrator.route_message error: {str(e)}", exc_info=True)
            raise

    async def handle_cta(
        self,
        workspace_id: str,
        profile_id: str,
        timeline_item_id: str,
        action: str,
        confirm: Optional[bool] = None,
        project_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Handle CTA action from timeline item

        Delegates to CTAHandler module.

        Args:
            workspace_id: Workspace ID
            profile_id: User profile ID
            timeline_item_id: Timeline item ID
            action: Action type (e.g., 'add_to_intents', 'publish_to_wordpress')
            confirm: Confirmation flag (for external_write)
            project_id: Optional project ID

        Returns:
            Response dict with conversation message
        """
        return await self.cta_handler.handle_cta(
            workspace_id=workspace_id,
            profile_id=profile_id,
            timeline_item_id=timeline_item_id,
            action=action,
            confirm=confirm,
            project_id=project_id
        )

    async def handle_suggestion_action(
        self,
        workspace_id: str,
        profile_id: str,
        action: str,
        action_params: Dict[str, Any],
        project_id: Optional[str] = None,
        message_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Handle action from dynamic suggestion

        Delegates to SuggestionActionHandler module.

        Args:
            workspace_id: Workspace ID
            profile_id: User profile ID
            action: Action type (e.g., 'execute_playbook', 'use_tool', 'create_intent')
            action_params: Action parameters
            project_id: Optional project ID
            message_id: Optional message/event ID for ExecutionPlan

        Returns:
            Response dict with conversation message and results
        """
        return await self.suggestion_action_handler.handle_action(
            workspace_id=workspace_id,
            profile_id=profile_id,
            action=action,
            action_params=action_params,
            project_id=project_id,
            message_id=message_id
        )

    async def generate_readonly_feedback(
        self,
        timeline_item: Dict[str, Any],
        task_result: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Generate feedback message for readonly task completion

        Delegates to MessageGenerator module.

        Args:
            timeline_item: Timeline item dict with task results
            task_result: Task execution result (optional)

        Returns:
            Natural feedback message text describing what was automatically analyzed
        """
        from backend.app.services.agent_runner import LLMProviderManager
        import os

        openai_key = os.getenv("OPENAI_API_KEY")
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        # Get Vertex AI configuration from system settings
        from backend.app.services.system_settings_store import SystemSettingsStore
        settings_store = SystemSettingsStore()
        service_account_setting = settings_store.get_setting("vertex_ai_service_account_json")
        vertex_project_setting = settings_store.get_setting("vertex_ai_project_id")
        vertex_location_setting = settings_store.get_setting("vertex_ai_location")

        # Get Vertex AI config - handle empty strings as None
        vertex_service_account_json = None
        if service_account_setting and service_account_setting.value:
            val = str(service_account_setting.value).strip()
            vertex_service_account_json = val if val else None
        if not vertex_service_account_json:
            vertex_service_account_json = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

        vertex_project_id = None
        if vertex_project_setting and vertex_project_setting.value:
            val = str(vertex_project_setting.value).strip()
            vertex_project_id = val if val else None
        if not vertex_project_id:
            vertex_project_id = os.getenv("GOOGLE_CLOUD_PROJECT")

        vertex_location = None
        if vertex_location_setting and vertex_location_setting.value:
            val = str(vertex_location_setting.value).strip()
            vertex_location = val if val else None
        from backend.app.shared.llm_provider_helper import create_llm_provider_manager

        if not vertex_location:
            vertex_location = os.getenv("VERTEX_LOCATION", "us-central1")

        llm_manager = create_llm_provider_manager(
            openai_key=openai_key,
            anthropic_key=anthropic_key,
            vertex_api_key=vertex_service_account_json,
            vertex_project_id=vertex_project_id,
            vertex_location=vertex_location
        )
        llm_provider = get_llm_provider_from_settings(llm_manager)

        message_generator = MessageGenerator(
            llm_provider=llm_provider,
            default_locale=self.default_locale
        )

        return await message_generator.generate_readonly_feedback(
            timeline_item=timeline_item,
            task_result=task_result,
            locale=self.default_locale
        )
