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
- LegacyMessageRouter: Legacy routing path orchestration
- PipelineCoreShim: PipelineCore feature-flag routing
- ProjectDetectorHandler: Project detection and creation
- ResponseAssembler: Event serialization and response building
- ThreadStatsUpdater: Thread statistics update helper
- LLMProviderFactory: LLM provider construction

This orchestrator ONLY:
- Routes messages to appropriate modules
- Coordinates module interactions
- Formats responses for API

DO NOT add implementation logic directly in this file.
All new features must be implemented in appropriate modules and delegated here.
"""

import logging
from typing import Dict, Any, Optional, List

from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.intent_analyzer import IntentPipeline
from backend.app.services.playbook_runner import PlaybookRunner
from backend.app.services.i18n_service import get_i18n_service
from backend.app.services.stores.tasks_store import TasksStore
from backend.app.services.stores.postgres.timeline_items_store import (
    PostgresTimelineItemsStore,
)
from backend.app.services.stores.postgres.artifacts_store import PostgresArtifactsStore
from backend.app.services.conversation.plan_builder import PlanBuilder
from backend.app.services.conversation.task_manager import TaskManager
from backend.app.services.conversation.cta_handler import CTAHandler
from backend.app.services.conversation.file_processor import FileProcessor
from backend.app.services.conversation.suggestion_action_handler import (
    SuggestionActionHandler,
)
from backend.app.services.conversation.coordinator_facade import CoordinatorFacade
from backend.app.services.conversation.qa_response_generator import QAResponseGenerator
from backend.app.services.conversation.message_generator import MessageGenerator
from backend.app.services.conversation.intent_extractor import IntentExtractor
from backend.app.services.conversation.llm_provider_factory import build_llm_provider
from backend.app.core.ports.identity_port import IdentityPort
from backend.app.core.ports.intent_registry_port import IntentRegistryPort

logger = logging.getLogger(__name__)


class ConversationOrchestrator:
    """
    Conversation Orchestrator - central coordinator for workspace interactions.

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
        intent_registry: Optional[IntentRegistryPort] = None,
    ):
        self.store = store
        self.intent_pipeline = intent_pipeline
        self.playbook_runner = playbook_runner
        self.i18n = get_i18n_service(default_locale=default_locale)
        self.default_locale = default_locale

        if identity_port is None:
            from backend.app.adapters.local.local_identity_adapter import (
                LocalIdentityAdapter,
            )

            identity_port = LocalIdentityAdapter()

        if intent_registry is None:
            from backend.app.adapters.local.local_intent_registry_adapter import (
                LocalIntentRegistryAdapter,
            )

            intent_registry = LocalIntentRegistryAdapter(default_locale=default_locale)

        self.identity_port = identity_port
        self.intent_registry = intent_registry

        # Stores
        self.tasks_store = TasksStore()
        self.timeline_items_store = PostgresTimelineItemsStore()
        self.artifacts_store = PostgresArtifactsStore()

        # Core modules
        self.plan_builder = PlanBuilder(store=store, default_locale=default_locale)
        self.task_manager = TaskManager(
            tasks_store=self.tasks_store,
            timeline_items_store=self.timeline_items_store,
            plan_builder=self.plan_builder,
            playbook_runner=playbook_runner,
            default_locale=default_locale,
            artifacts_store=self.artifacts_store,
            store=store,
        )
        self.cta_handler = CTAHandler(
            store=store,
            tasks_store=self.tasks_store,
            timeline_items_store=self.timeline_items_store,
            plan_builder=self.plan_builder,
            default_locale=default_locale,
        )
        self.file_processor = FileProcessor(store=store)
        self.intent_extractor = IntentExtractor(
            store=store,
            timeline_items_store=self.timeline_items_store,
            intent_registry=intent_registry,
            default_locale=default_locale,
        )
        self.suggestion_action_handler = SuggestionActionHandler(
            store=store,
            playbook_runner=playbook_runner,
            task_manager=self.task_manager,
            execution_coordinator=None,
            default_locale=default_locale,
        )

        # Build LLM provider and coordinator facade
        llm_provider = build_llm_provider()
        message_generator = MessageGenerator(
            llm_provider=llm_provider, default_locale=default_locale
        )

        from backend.app.services.playbook_service import PlaybookService

        playbook_service = PlaybookService(store=store)

        # Use shared PlaybookRunner instance from execution_shared module
        from backend.app.routes.core.execution_shared import (
            playbook_runner as shared_playbook_runner,
        )

        playbook_runner = shared_playbook_runner

        self.execution_coordinator = CoordinatorFacade(
            store=store,
            tasks_store=self.tasks_store,
            timeline_items_store=self.timeline_items_store,
            task_manager=self.task_manager,
            plan_builder=self.plan_builder,
            playbook_runner=playbook_runner,
            message_generator=message_generator,
            default_locale=default_locale,
            playbook_service=playbook_service,
        )

        # Wire coordinator back to suggestion handler
        self.suggestion_action_handler.execution_coordinator = (
            self.execution_coordinator
        )

        self.qa_response_generator = QAResponseGenerator(
            store=store,
            timeline_items_store=self.timeline_items_store,
            default_locale=default_locale,
        )

    async def route_message(
        self,
        workspace_id: str,
        profile_id: str,
        message: str,
        files: List[str],
        mode: str,
        project_id: Optional[str] = None,
        workspace: Optional[Any] = None,
        thread_id: Optional[str] = None,
        request: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Route message through existing pipeline and sync derived data.

        Args:
            workspace_id: Workspace ID.
            profile_id: User profile ID.
            message: User message text.
            files: List of file IDs.
            mode: Interaction mode.
            project_id: Optional project ID.
            workspace: Optional workspace object.
            thread_id: Optional conversation thread ID.
            request: Optional original request object (forwarded to PipelineCore
                     for handoff/meeting data).

        Returns:
            Response dict with events, triggered_playbook, pending_tasks.
        """
        try:
            if not workspace:
                workspace = await self.store.get_workspace(workspace_id)

            # Check PipelineCore feature flag
            from backend.app.services.conversation.pipeline_core import (
                should_use_pipeline_core,
            )

            if should_use_pipeline_core(workspace):
                from backend.app.services.conversation.pipeline_core_shim import (
                    route_via_pipeline_core,
                )

                return await route_via_pipeline_core(
                    store=self.store,
                    workspace=workspace,
                    workspace_id=workspace_id,
                    profile_id=profile_id,
                    message=message,
                    files=files,
                    mode=mode,
                    project_id=project_id,
                    thread_id=thread_id,
                    tasks_store=self.tasks_store,
                    request=request,
                )

            # Legacy routing path
            from backend.app.services.conversation.legacy_message_router import (
                LegacyMessageRouter,
            )

            router = LegacyMessageRouter(
                store=self.store,
                identity_port=self.identity_port,
                intent_extractor=self.intent_extractor,
                intent_pipeline=self.intent_pipeline,
                plan_builder=self.plan_builder,
                execution_coordinator=self.execution_coordinator,
                qa_response_generator=self.qa_response_generator,
                file_processor=self.file_processor,
                tasks_store=self.tasks_store,
                task_manager=self.task_manager,
                default_locale=self.default_locale,
            )
            return await router.route(
                workspace_id=workspace_id,
                profile_id=profile_id,
                message=message,
                files=files,
                mode=mode,
                project_id=project_id,
                workspace=workspace,
                thread_id=thread_id,
            )

        except Exception as e:
            logger.error(
                "ConversationOrchestrator.route_message error: %s",
                str(e),
                exc_info=True,
            )
            raise

    async def handle_cta(
        self,
        workspace_id: str,
        profile_id: str,
        timeline_item_id: str,
        action: str,
        confirm: Optional[bool] = None,
        project_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Handle CTA action from timeline item.

        Delegates to CTAHandler module.

        Args:
            workspace_id: Workspace ID.
            profile_id: User profile ID.
            timeline_item_id: Timeline item ID.
            action: Action type (e.g., 'add_to_intents', 'publish_to_wordpress').
            confirm: Confirmation flag (for external_write).
            project_id: Optional project ID.

        Returns:
            Response dict with conversation message.
        """
        return await self.cta_handler.handle_cta(
            workspace_id=workspace_id,
            profile_id=profile_id,
            timeline_item_id=timeline_item_id,
            action=action,
            confirm=confirm,
            project_id=project_id,
        )

    async def handle_suggestion_action(
        self,
        workspace_id: str,
        profile_id: str,
        action: str,
        action_params: Dict[str, Any],
        project_id: Optional[str] = None,
        message_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Handle action from dynamic suggestion.

        Delegates to SuggestionActionHandler module.

        Args:
            workspace_id: Workspace ID.
            profile_id: User profile ID.
            action: Action type (e.g., 'execute_playbook', 'use_tool', 'create_intent').
            action_params: Action parameters.
            project_id: Optional project ID.
            message_id: Optional message/event ID for ExecutionPlan.

        Returns:
            Response dict with conversation message and results.
        """
        return await self.suggestion_action_handler.handle_action(
            workspace_id=workspace_id,
            profile_id=profile_id,
            action=action,
            action_params=action_params,
            project_id=project_id,
            message_id=message_id,
        )

    async def generate_readonly_feedback(
        self,
        timeline_item: Dict[str, Any],
        task_result: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Generate feedback message for readonly task completion.

        Delegates to MessageGenerator module.

        Args:
            timeline_item: Timeline item dict with task results.
            task_result: Task execution result (optional).

        Returns:
            Natural feedback message text describing what was automatically analyzed.
        """
        llm_provider = build_llm_provider()
        message_generator = MessageGenerator(
            llm_provider=llm_provider, default_locale=self.default_locale
        )
        return await message_generator.generate_readonly_feedback(
            timeline_item=timeline_item,
            task_result=task_result,
            locale=self.default_locale,
        )
