"""
Chat Orchestrator Service

Decoupled service for managing chat generation in background tasks.
Persists intermediate states to MindscapeStore as events.

Implementation logic is delegated to:
- chat_session_setup: Unified session initialization
- thread_stats_updater: Thread statistics updates
- pipeline_core: PipelineCore feature-flag routing
- chat_orchestrator_core: retained helper seams
"""

import logging
from typing import Optional

from backend.app.models.workspace import Workspace, WorkspaceChatRequest
from backend.app.services.chat_orchestrator_core.agent_dispatch import (
    handle_agent_dispatch,
)
from backend.app.services.chat_orchestrator_core.events import (
    create_error_event as persist_error_event,
    create_pipeline_event as persist_pipeline_event,
)
from backend.app.services.chat_orchestrator_core.llm_path import handle_llm_path
from backend.app.services.conversation.thread_stats_updater import update_thread_stats
from backend.app.services.conversation_orchestrator import ConversationOrchestrator
from backend.app.shared.i18n_loader import load_i18n_string
from backend.features.workspace.chat.streaming.chat_session_setup import (
    setup_chat_session,
    smart_truncate_message,
)

logger = logging.getLogger(__name__)


class ChatOrchestratorService:
    def __init__(self, orchestrator: ConversationOrchestrator):
        self.orchestrator = orchestrator

    async def run_background_chat(
        self,
        request: WorkspaceChatRequest,
        workspace: Workspace,
        workspace_id: str,
        profile_id: str,
        user_event_id: Optional[str] = None,
    ):
        """
        Run chat generation in background, persisting events to DB.

        Handles: session setup, PipelineCore routing, agent dispatch,
        LLM streaming, and thread summarization.
        """

        try:
            # 1. Unified session setup
            session = await setup_chat_session(
                request=request,
                workspace=workspace,
                workspace_id=workspace_id,
                profile_id=profile_id,
                store=self.orchestrator.store,
                user_event_id=user_event_id,
            )

            # 2. PipelineCore routing (sole path after hard cutover)
            from backend.app.services.conversation.pipeline_core import PipelineCore

            pipeline = PipelineCore(
                orchestrator_store=self.orchestrator.store,
                workspace=workspace,
                profile=session.profile,
                runtime_profile=session.runtime_profile,
            )

            pipeline_result = await pipeline.process(
                workspace_id=workspace_id,
                profile_id=profile_id,
                thread_id=session.thread_id,
                project_id=session.project_id,
                message=request.message,
                user_event_id=session.user_event.id,
                execution_mode=session.execution_mode,
                model_name=request.model_name,
                request=request,
            )

            if not pipeline_result.success:
                await self._create_error_event(
                    workspace_id,
                    profile_id,
                    session.thread_id,
                    pipeline_result.error or "Pipeline processing failed",
                    retry_data={"message": request.message},
                )

            await update_thread_stats(
                self.orchestrator.store, workspace_id, session.thread_id
            )
            logger.info("PipelineCore completed for %s", session.user_event.id)
            return pipeline_result

            # 3. Below: retained legacy LLM streaming path (non-PipelineCore features)
            if session.execution_mode in ("execution", "hybrid"):
                user_message_preview = smart_truncate_message(
                    request.message, max_length=60
                )
                intent_message = load_i18n_string(
                    "workspace.pipeline_stage.intent_extraction",
                    locale=session.locale,
                    default=f"Analyzing: understanding your request '{user_message_preview}', finding a suitable Playbook.",
                ).format(user_message=user_message_preview)

                await self._create_pipeline_event(
                    workspace_id,
                    profile_id,
                    session.thread_id,
                    session.project_id,
                    "intent_extraction",
                    intent_message,
                    session.user_event.id,
                )

            context_message = load_i18n_string(
                "workspace.pipeline_stage.context_building",
                locale=session.locale,
                default="Preparing context: gathering relevant documents and project context.",
            )
            await self._create_pipeline_event(
                workspace_id,
                profile_id,
                session.thread_id,
                session.project_id,
                "context_building",
                context_message,
                session.user_event.id,
            )

            from backend.app.services.executor_routing_policy_service import (
                ExecutorRoutingPolicyService,
            )

            executor_runtime = (
                ExecutorRoutingPolicyService.extract_workspace_policy_snapshot(
                    workspace
                ).get("primary_executor_runtime")
            )
            if executor_runtime:
                await self._handle_agent_dispatch(
                    request=request,
                    workspace=workspace,
                    workspace_id=workspace_id,
                    profile_id=profile_id,
                    session=session,
                    executor_runtime=executor_runtime,
                )
                return

            await self._handle_llm_path(
                request=request,
                workspace=workspace,
                workspace_id=workspace_id,
                profile_id=profile_id,
                session=session,
            )

            await update_thread_stats(
                self.orchestrator.store, workspace_id, session.thread_id
            )

            logger.info("Background task completed for %s", session.user_event.id)

        except Exception as e:
            logger.error("Error in background task: %s", e, exc_info=True)
            await self._create_error_event(
                workspace_id,
                profile_id,
                getattr(locals().get("session"), "thread_id", None) or "",
                str(e),
                retry_data={"message": request.message},
            )

    async def _handle_agent_dispatch(
        self, request, workspace, workspace_id, profile_id, session, executor_runtime
    ):
        """Route to the configured external agent runtime."""
        return await handle_agent_dispatch(
            request=request,
            workspace=workspace,
            workspace_id=workspace_id,
            profile_id=profile_id,
            session=session,
            executor_runtime=executor_runtime,
            store=self.orchestrator.store,
            create_pipeline_event=self._create_pipeline_event,
            create_error_event=self._create_error_event,
        )

    async def _handle_llm_path(
        self,
        request,
        workspace,
        workspace_id,
        profile_id,
        session,
        model_name_override: str = None,
    ):
        """Generate response via default LLM streaming path."""
        return await handle_llm_path(
            request=request,
            workspace=workspace,
            workspace_id=workspace_id,
            profile_id=profile_id,
            session=session,
            orchestrator_store=self.orchestrator.store,
            create_error_event=self._create_error_event,
            model_name_override=model_name_override,
        )

    async def _create_pipeline_event(
        self, workspace_id, profile_id, thread_id, project_id, stage, message, run_id
    ):
        """Create a persisted pipeline stage event."""
        return await persist_pipeline_event(
            store=self.orchestrator.store,
            workspace_id=workspace_id,
            profile_id=profile_id,
            thread_id=thread_id,
            project_id=project_id,
            stage=stage,
            message=message,
            run_id=run_id,
        )

    async def _create_error_event(
        self, workspace_id, profile_id, thread_id, error_msg, retry_data=None
    ):
        """Create a persisted error event."""
        return await persist_error_event(
            store=self.orchestrator.store,
            workspace_id=workspace_id,
            profile_id=profile_id,
            thread_id=thread_id,
            error_msg=error_msg,
            retry_data=retry_data,
        )
