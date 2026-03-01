"""
Chat Orchestrator Service

Decoupled service for managing chat generation in background tasks.
Persists intermediate states to MindscapeStore as events.

Implementation logic is delegated to:
- chat_session_setup: Unified session initialization
- thread_stats_updater: Thread statistics updates
- pipeline_core: PipelineCore feature-flag routing
"""

import logging
import json
import asyncio
from typing import Optional
from datetime import datetime, timezone

from backend.app.models.mindscape import MindEvent, EventType, EventActor
from backend.app.models.workspace import Workspace, WorkspaceChatRequest
from backend.app.services.conversation_orchestrator import ConversationOrchestrator
from backend.app.services.stores.workspace_runtime_profile_store import (
    WorkspaceRuntimeProfileStore,
)
from backend.app.shared.i18n_loader import get_locale_from_context, load_i18n_string
from backend.app.utils.runtime_profile import get_resolved_mode
from backend.features.workspace.chat.streaming.llm_streaming import stream_llm_response
from backend.features.workspace.chat.streaming.chat_session_setup import (
    setup_chat_session,
    smart_truncate_message,
)
from backend.app.services.conversation.thread_stats_updater import update_thread_stats

logger = logging.getLogger(__name__)


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


import uuid


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
        logger.info("Starting background task for workspace %s", workspace_id)

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

            # 2. PipelineCore routing (feature flag)
            from backend.app.services.conversation.pipeline_core import (
                PipelineCore,
                should_use_pipeline_core,
            )

            if should_use_pipeline_core(workspace):
                logger.info("PipelineCore enabled for workspace %s", workspace_id)
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
                # Final thread stats update
                await update_thread_stats(
                    self.orchestrator.store, workspace_id, session.thread_id
                )
                logger.info("PipelineCore completed for %s", session.user_event.id)
                return

            # 3. Legacy path (feature flag off)

            # Intent extraction stage (execution/hybrid modes)
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

            # Context building stage
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

            # 4. Agent dispatch (if workspace has executor_runtime)
            executor_runtime = getattr(
                workspace, "resolved_executor_runtime", None
            ) or getattr(workspace, "executor_runtime", None)
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

            # 5. Default LLM path
            await self._handle_llm_path(
                request=request,
                workspace=workspace,
                workspace_id=workspace_id,
                profile_id=profile_id,
                session=session,
            )

            # Final thread stats update
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

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _handle_agent_dispatch(
        self, request, workspace, workspace_id, profile_id, session, executor_runtime
    ):
        """Route to WorkspaceAgentExecutor when agent runtime is configured."""
        logger.info(
            "Workspace has executor_runtime=%s, routing to agent", executor_runtime
        )

        from backend.app.services.workspace_agent_executor import (
            WorkspaceAgentExecutor,
            AgentExecutionResponse,
        )

        executor = WorkspaceAgentExecutor(workspace)
        agent_available = await executor.check_agent_available(executor_runtime)

        if not agent_available:
            # P0 Fail-Loud: check for explicit fallback model
            fallback_model = getattr(workspace, "fallback_model", None)
            if fallback_model:
                logger.info(
                    "Agent %s unavailable, using fallback model %s",
                    executor_runtime,
                    fallback_model,
                )
                await self._create_pipeline_event(
                    workspace_id,
                    profile_id,
                    session.thread_id,
                    session.project_id,
                    "agent_fallback",
                    f"Executor {executor_runtime} unavailable, using fallback model {fallback_model}",
                    session.user_event.id,
                )
                return await self._handle_llm_path(
                    request,
                    workspace,
                    workspace_id,
                    profile_id,
                    session,
                    model_name_override=fallback_model,
                    is_fallback=True,
                )
            await self._create_error_event(
                workspace_id,
                profile_id,
                session.thread_id,
                f"Executor {executor_runtime} unavailable: no runtime connected. "
                f"Start the CLI bridge or configure a fallback model.",
            )
            logger.warning(
                "Agent %s unavailable, no runtime connected", executor_runtime
            )
            return

        # Agent is available -- dispatch
        await self._create_pipeline_event(
            workspace_id,
            profile_id,
            session.thread_id,
            session.project_id,
            "agent_dispatching",
            f"Dispatching task to agent {executor_runtime}...",
            session.user_event.id,
        )

        # Build conversation context
        from backend.features.workspace.chat.streaming.context_builder import (
            build_streaming_context,
        )
        from backend.app.services.stores.postgres.timeline_items_store import (
            PostgresTimelineItemsStore,
        )

        timeline_items_store = PostgresTimelineItemsStore()
        conversation_context = await build_streaming_context(
            workspace_id=workspace_id,
            message=request.message,
            profile_id=profile_id,
            workspace=workspace,
            store=self.orchestrator.store,
            timeline_items_store=timeline_items_store,
            model_name=None,
            thread_id=session.thread_id,
        )

        # Resolve file IDs to enriched metadata for agent
        raw_files = getattr(request, "files", None) or []
        enriched_files = []
        if raw_files:
            import os as _os
            import json as _json
            from pathlib import Path as _Path

            uploads_dir = (
                _Path(_os.getenv("UPLOADS_DIR", "data/uploads")) / workspace_id
            )
            for file_id in raw_files:
                if not isinstance(file_id, str):
                    enriched_files.append(file_id)
                    continue
                # Read .meta.json sidecar for original filename
                meta_path = uploads_dir / f"{file_id}.meta.json"
                original_name = None
                if meta_path.exists():
                    try:
                        with open(meta_path) as mf:
                            original_name = _json.load(mf).get("original_name")
                    except Exception:
                        pass
                # Glob for actual file
                matched = (
                    list(uploads_dir.glob(f"{file_id}.*"))
                    if uploads_dir.exists()
                    else []
                )
                matched = [
                    m
                    for m in matched
                    if not m.name.endswith(".meta.json")
                    and not m.name.endswith(".analysis.json")
                ]
                if matched:
                    fpath = matched[0]
                    enriched_files.append(
                        {
                            "file_id": file_id,
                            "file_name": original_name or fpath.name,
                            "file_path": str(fpath),
                            "file_type": fpath.suffix.lstrip("."),
                        }
                    )
                    logger.info(
                        "Enriched file %s -> %s (%s)",
                        file_id,
                        fpath.name,
                        fpath.suffix,
                    )
                else:
                    logger.warning("File ID %s not found in %s", file_id, uploads_dir)

        agent_response: AgentExecutionResponse = await executor.execute(
            task=request.message,
            agent_id=executor_runtime,
            context_overrides={
                "conversation_context": conversation_context or "",
                "thread_id": session.thread_id,
                "project_id": session.project_id,
                "uploaded_files": enriched_files,
            },
        )

        exec_time = agent_response.execution_time_seconds
        if agent_response.success:
            await self._create_pipeline_event(
                workspace_id,
                profile_id,
                session.thread_id,
                session.project_id,
                "agent_completed",
                f"Agent completed in {exec_time:.0f}s",
                session.user_event.id,
            )

            # Persist agent response
            assistant_event = MindEvent(
                id=str(uuid.uuid4()),
                timestamp=_utc_now(),
                actor=EventActor.ASSISTANT,
                channel="local_workspace",
                profile_id=profile_id,
                project_id=session.project_id,
                workspace_id=workspace_id,
                thread_id=session.thread_id,
                event_type=EventType.MESSAGE,
                payload={
                    "message": agent_response.output,
                    "agent_id": executor_runtime,
                    "trace_id": agent_response.trace_id,
                    "execution_time": agent_response.execution_time_seconds,
                },
                entity_ids=[],
                metadata={
                    "external_agent": True,
                    "agent_id": executor_runtime,
                },
            )
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                lambda: self.orchestrator.store.create_event(assistant_event),
            )
            logger.info(
                "External agent %s completed, trace_id=%s",
                executor_runtime,
                agent_response.trace_id,
            )
            return

        # Agent failed -- P0 Fail-Loud: check for fallback
        error_msg = agent_response.error or "External agent execution failed"
        fallback_model = getattr(workspace, "fallback_model", None)
        if fallback_model:
            logger.info(
                "Agent %s failed, using fallback model %s",
                executor_runtime,
                fallback_model,
            )
            await self._create_pipeline_event(
                workspace_id,
                profile_id,
                session.thread_id,
                session.project_id,
                "agent_fallback",
                f"Executor {executor_runtime} failed: {error_msg}, using fallback model {fallback_model}",
                session.user_event.id,
            )
            return await self._handle_llm_path(
                request,
                workspace,
                workspace_id,
                profile_id,
                session,
                model_name_override=fallback_model,
                is_fallback=True,
            )
        await self._create_error_event(
            workspace_id,
            profile_id,
            session.thread_id,
            f"Executor {executor_runtime} execution failed: {error_msg}. "
            f"Configure a fallback model to avoid this.",
            retry_data={
                "message": request.message,
                "agent_id": executor_runtime,
            },
        )
        logger.error("External agent %s failed: %s", executor_runtime, error_msg)

    async def _handle_llm_path(
        self,
        request,
        workspace,
        workspace_id,
        profile_id,
        session,
        model_name_override: str = None,
        is_fallback: bool = False,
    ):
        """Generate response via default LLM streaming path.

        Args:
            model_name_override: If set (e.g. from fallback_model),
                use this model instead of request.model_name.
            is_fallback: True when using fallback model after agent failure.
        """
        from backend.features.workspace.chat.streaming.llm_streaming import (
            stream_llm_response,
        )
        from backend.features.workspace.chat.utils.llm_provider import (
            get_llm_provider_manager,
            get_llm_provider,
        )

        # Resolve model name
        model_name = model_name_override or request.model_name
        if not model_name:
            try:
                from backend.app.services.system_settings_store import (
                    SystemSettingsStore,
                )

                settings_store = SystemSettingsStore()
                chat_setting = settings_store.get_setting("chat_model")
                if chat_setting and chat_setting.value:
                    model_name = str(chat_setting.value)
            except Exception as e:
                logger.warning("Failed to fetch default chat model: %s", e)

        if not model_name or str(model_name).strip() == "":
            await self._create_error_event(
                workspace_id,
                profile_id,
                session.thread_id,
                "No chat model configured. Set chat_model in system settings.",
            )
            return

        provider_manager = get_llm_provider_manager()
        provider, provider_type = get_llm_provider(
            model_name=model_name,
            llm_provider_manager=provider_manager,
            profile_id=profile_id,
            db_path=self.orchestrator.store.db_path,
        )

        # Build context
        from backend.features.workspace.chat.streaming.context_builder import (
            build_streaming_context,
        )
        from backend.app.services.stores.postgres.timeline_items_store import (
            PostgresTimelineItemsStore,
        )

        timeline_items_store = PostgresTimelineItemsStore()
        context_str = await build_streaming_context(
            workspace_id=workspace_id,
            message=request.message,
            profile_id=profile_id,
            workspace=workspace,
            store=self.orchestrator.store,
            timeline_items_store=timeline_items_store,
            model_name=model_name,
            thread_id=session.thread_id,
        )

        # Inject workspace instruction into system message
        from backend.app.services.workspace_instruction_helper import (
            build_workspace_instruction_block,
        )

        ws_instruction, _src = build_workspace_instruction_block(
            workspace, caller="background"
        )
        if ws_instruction:
            context_str = (
                ws_instruction + "\n\n" + (context_str or "")
                if context_str
                else ws_instruction
            )

        messages = []
        if context_str:
            messages.append({"role": "system", "content": context_str})
        messages.append({"role": "user", "content": request.message})

        # SGR prompt injection (feature-gated)
        sgr_enabled = False
        try:
            ws_metadata = workspace.metadata or {}
            sgr_enabled = ws_metadata.get("sgr_enabled", False)
        except Exception:
            pass

        if sgr_enabled:
            from backend.app.services.sgr_reasoning_service import SGRReasoningService

            sgr_service = SGRReasoningService()
            messages = sgr_service.inject_sgr_prompt(messages)
            logger.info("SGR prompt injected into messages")

        context_token_count = len(context_str) // 4 if context_str else 0

        logger.info("Consuming LLM stream for mode %s", session.execution_mode)

        async for _ in stream_llm_response(
            provider=provider,
            provider_type=provider_type,
            messages=messages,
            model_name=model_name,
            execution_mode=session.execution_mode,
            user_event_id=session.user_event.id,
            profile_id=profile_id,
            project_id=session.project_id,
            workspace_id=workspace_id,
            thread_id=session.thread_id,
            workspace=workspace,
            message=request.message,
            profile=session.profile,
            store=self.orchestrator.store,
            context_token_count=context_token_count,
            execution_playbook_result=None,
            openai_key=None,
            is_fallback=is_fallback,
        ):
            pass  # Consume stream to trigger internal logic

    async def _create_pipeline_event(
        self, workspace_id, profile_id, thread_id, project_id, stage, message, run_id
    ):
        """Create a persisted pipeline stage event."""
        event = MindEvent(
            id=str(uuid.uuid4()),
            timestamp=_utc_now(),
            actor=EventActor.SYSTEM,
            channel="local_workspace",
            profile_id=profile_id,
            project_id=project_id,
            workspace_id=workspace_id,
            thread_id=thread_id,
            event_type=EventType.PIPELINE_STAGE,
            payload={
                "stage": stage,
                "message": message,
                "run_id": run_id,
                "status": "running",
            },
            entity_ids=[],
            metadata={},
        )
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        await loop.run_in_executor(
            None, lambda: self.orchestrator.store.create_event(event)
        )
        logger.info("Persisted pipeline event: %s", stage)

    async def _create_error_event(
        self, workspace_id, profile_id, thread_id, error_msg, retry_data=None
    ):
        """Create a persisted error event."""
        metadata = {"is_error": True}
        if retry_data:
            metadata["retry_data"] = retry_data
        event = MindEvent(
            id=str(uuid.uuid4()),
            timestamp=_utc_now(),
            actor=EventActor.SYSTEM,
            channel="local_workspace",
            profile_id=profile_id,
            workspace_id=workspace_id,
            thread_id=thread_id,
            event_type=EventType.MESSAGE,
            payload={
                "message": f"Error processing request: {error_msg}",
                "type": "error",
            },
            entity_ids=[],
            metadata=metadata,
        )
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        await loop.run_in_executor(
            None, lambda: self.orchestrator.store.create_event(event)
        )
