"""
Conversation Orchestrator Service

Central coordinator for all workspace interactions.

MODULARIZATION POLICY:
This file serves as a thin coordinator layer. All implementation logic MUST be
delegated to specialized modules in conversation/ directory:

Module Responsibilities:
- CoordinatorFacade: Pack/playbook execution, suggestion card creation
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
from backend.app.services.playbook_service import PlaybookService, ExecutionMode as PlaybookExecutionMode
from backend.app.services.i18n_service import get_i18n_service
from backend.app.services.stores.tasks_store import TasksStore
from backend.app.services.stores.timeline_items_store import TimelineItemsStore
from backend.app.services.stores.artifacts_store import ArtifactsStore
from backend.app.services.conversation.plan_builder import PlanBuilder
from backend.app.services.conversation.task_manager import TaskManager
from backend.app.services.conversation.cta_handler import CTAHandler
from backend.app.services.conversation.file_processor import FileProcessor
from backend.app.services.conversation.suggestion_action_handler import SuggestionActionHandler
from backend.app.services.conversation.coordinator_facade import CoordinatorFacade
from backend.app.services.conversation.qa_response_generator import QAResponseGenerator
from backend.app.services.conversation.message_generator import MessageGenerator
from backend.app.services.conversation.intent_extractor import IntentExtractor
from backend.app.services.conversation.intent_steward import IntentStewardService
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
        self.playbook_service = PlaybookService(store=store)
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

        # Initialize IntentSteward (Phase 1: observation mode)
        self.intent_steward = IntentStewardService(
            store=store,
            default_locale=default_locale
        )

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

        from backend.app.shared.llm_provider_helper import create_llm_provider_manager

        llm_manager = create_llm_provider_manager()
        llm_provider = get_llm_provider_from_settings(llm_manager)

        message_generator = MessageGenerator(
            llm_provider=llm_provider,
            default_locale=default_locale
        )

        self.execution_coordinator = CoordinatorFacade(
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

        # Update SuggestionActionHandler with CoordinatorFacade reference
        self.suggestion_action_handler.execution_coordinator = self.execution_coordinator

        self.qa_response_generator = QAResponseGenerator(
            store=store,
            timeline_items_store=self.timeline_items_store,
            default_locale=default_locale
        )

        # Initialize ProjectAssignmentService
        from backend.app.services.project.project_assignment_service import ProjectAssignmentService
        self.project_assignment_service = ProjectAssignmentService(store=self.store)

        from backend.app.services.playbook.playbook_scope_resolver import PlaybookScopeResolver
        self.playbook_scope_resolver = PlaybookScopeResolver(store=self.store)

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
            # Create execution context for file processing and other operations
            from backend.app.core.execution_context import ExecutionContext
            ctx = ExecutionContext(
                actor_id=profile_id,
                workspace_id=workspace_id,
                tags={"mode": "local"}
            )

            file_document_ids = []
            if files:
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

            conversation_id = None

            project_assignment = await self.project_assignment_service.assign_project(
                message=message,
                workspace_id=workspace_id,
                message_id=user_event.id,
                conversation_id=conversation_id,
                ui_selected_project_id=project_id
            )

            final_project_id = project_assignment.project_id

            logger.info(
                f"Project assignment: project_id={final_project_id}, "
                f"relation={project_assignment.relation}, "
                f"confidence={project_assignment.confidence:.2f}, "
                f"requires_ui_confirmation={project_assignment.requires_ui_confirmation}"
            )

            if user_event.metadata is None:
                user_event.metadata = {}
            user_event.metadata["project_assignment"] = project_assignment.to_dict()
            self.store.events.update_event(user_event.id, user_event)

            if final_project_id:
                user_event.project_id = final_project_id
                self.store.events.update_event(user_event.id, user_event)

            ctx = await self.identity_port.get_current_context(
                workspace_id=workspace_id,
                profile_id=profile_id
            )

            project_profile = None
            if final_project_id:
                from backend.app.services.project.project_manager import ProjectManager
                project_manager = ProjectManager(self.store)
                project = await project_manager.get_project(final_project_id, workspace_id=workspace_id)
                if project:
                    project_profile = project.metadata.get("capability_profile") if hasattr(project, "metadata") and project.metadata else None

            tenant_id = None
            user_id = profile_id

            effective_playbooks = await self.playbook_scope_resolver.resolve_effective_playbooks(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                user_id=user_id,
                project_id=final_project_id,
                project_profile=project_profile
            )

            logger.info(
                f"Resolved {len(effective_playbooks)} effective playbooks "
                f"(workspace={workspace_id}, user={user_id}, project={final_project_id})"
            )
            logger.info(f"ConversationOrchestrator: BEFORE calling intent_extractor.extract_and_create_timeline_item")
            import sys
            print(f"ConversationOrchestrator: BEFORE calling intent_extractor.extract_and_create_timeline_item", file=sys.stderr)
            timeline_item = await self.intent_extractor.extract_and_create_timeline_item(
                ctx=ctx,
                message=message,
                message_id=user_event.id,
                locale=self.default_locale
            )
            logger.info(f"ConversationOrchestrator: AFTER intent_extractor call, result: {timeline_item is not None}")
            print(f"ConversationOrchestrator: AFTER intent_extractor call, result: {timeline_item is not None}", file=sys.stderr)

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
            except Exception as e:
                logger.warning(f"Intent analysis failed, falling back to QA: {str(e)}")

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
                        orchestrator = WorkflowOrchestrator(store=self.store)
                        workflow_result = await orchestrator.execute_workflow(
                            handoff_plan,
                            execution_id=None,
                            workspace_id=ctx.workspace_id,
                            profile_id=ctx.actor_id
                        )

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

            execution_plan = await self.plan_builder.generate_execution_plan(
                message=message,
                files=files,
                workspace_id=workspace_id,
                profile_id=profile_id,
                message_id=user_event.id,
                use_llm=True,
                project_id=final_project_id,
                project_assignment_decision=project_assignment.to_dict(),
                effective_playbooks=effective_playbooks
            )
            logger.info(f"ConversationOrchestrator: Generated execution plan with {len(execution_plan.tasks)} tasks")
            import sys
            print(f"ConversationOrchestrator: Generated execution plan with {len(execution_plan.tasks)} tasks", file=sys.stderr)

            if execution_plan:
                execution_plan.project_id = final_project_id
                execution_plan.project_assignment_decision = project_assignment.to_dict()

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
                if not intent_result.handoff_plan:
                    raise ValueError(
                        f"Playbook {intent_result.selected_playbook_code} does not have playbook.json. "
                        f"HandoffPlan is required for execution. Please create playbook.json for structured workflow execution."
                    )

                execution_result_obj = await self.playbook_service.execute_playbook(
                    playbook_code=intent_result.selected_playbook_code,
                    workspace_id=workspace_id,
                    profile_id=profile_id,
                    inputs=intent_result.playbook_context,
                    execution_mode=PlaybookExecutionMode.ASYNC,
                    locale=intent_result.playbook_context.get("locale")
                )
                execution_result = {
                    "execution_id": execution_result_obj.execution_id,
                    "execution_mode": "workflow" if execution_result_obj.status == "running" else "conversation",
                    "result": execution_result_obj.result or {},
                }

                if execution_result.get("execution_mode") == "workflow":
                    triggered_playbook = {
                        "playbook_code": intent_result.selected_playbook_code,
                        "execution_id": execution_result.get("result", {}).get("execution_id"),
                        "context": intent_result.playbook_context,
                        "status": "started",
                        "message": f"Executing {intent_result.selected_playbook_code} using structured workflow"
                    }
                    assistant_response = triggered_playbook.get("message")
                else:
                    triggered_playbook = {
                        "playbook_code": intent_result.selected_playbook_code,
                        "execution_id": execution_result.get("result", {}).get("execution_id"),
                        "context": intent_result.playbook_context,
                        "status": "started",
                        "message": execution_result.get("result", {}).get("message", "")
                    }
                    assistant_response = triggered_playbook.get("message")
            else:
                logger.info("Using QA mode (no playbook selected)")
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

                if assistant_response:
                    logger.info(f"Generated assistant response: {assistant_response[:100]}... (length: {len(assistant_response)})")
                else:
                    logger.warning("Assistant response is empty or None")

                if assistant_event:
                    logger.info(f"Created assistant event: {assistant_event.id}, timestamp: {assistant_event.timestamp}")
                else:
                    logger.warning("Assistant event is None")

            import asyncio
            await asyncio.sleep(0.1)

            recent_events = self.store.get_events_by_workspace(
                workspace_id=workspace_id,
                limit=20
            )

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

            try:
                await self.intent_steward.analyze_turn(
                    workspace_id=workspace_id,
                    profile_id=profile_id,
                    turn_id=user_event.id,
                    conversation_id=None
                )
            except Exception as e:
                logger.warning(f"IntentSteward analysis failed (non-blocking): {e}", exc_info=True)

            if triggered_playbook and triggered_playbook.get("playbook_code"):
                try:
                    from ...services.conversation.intent_cluster_service import IntentClusterService
                    cluster_service = IntentClusterService(store=self.store)
                    import asyncio
                    async def trigger_clustering():
                        try:
                            await cluster_service.cluster_intents(
                                workspace_id=workspace_id,
                                profile_id=profile_id
                            )
                        except Exception as e:
                            logger.warning(f"Background intent clustering failed: {e}")

                    asyncio.create_task(trigger_clustering())
                    logger.info(f"Scheduled intent clustering after playbook execution")
                except Exception as e:
                    logger.warning(f"Intent clustering trigger failed (non-blocking): {e}", exc_info=True)

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
        from backend.app.shared.llm_provider_helper import create_llm_provider_manager

        llm_manager = create_llm_provider_manager()
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
