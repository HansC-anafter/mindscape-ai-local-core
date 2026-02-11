"""
Chat Orchestrator Service
Decoupled service for managing chat generation in background tasks.
Persists intermediate states to MindscapeStore as events.
"""

import logging
import uuid
import sys
import json
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)

from backend.app.models.mindscape import MindEvent, EventType, EventActor
from backend.app.models.workspace import Workspace, WorkspaceChatRequest
from backend.app.services.conversation_orchestrator import ConversationOrchestrator
from backend.app.services.stores.workspace_runtime_profile_store import (
    WorkspaceRuntimeProfileStore,
)
from backend.app.shared.i18n_loader import get_locale_from_context, load_i18n_string
from backend.app.utils.runtime_profile import get_resolved_mode
from backend.features.workspace.chat.streaming.llm_streaming import stream_llm_response

# Re-use helpers (could be moved to shared utils later)
from backend.features.workspace.chat.streaming.generator import (
    _get_or_create_default_thread,
    _smart_truncate_message,
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
        """
        logger.info(
            f"[AsyncChat] Starting background task for workspace {workspace_id}"
        )

        try:
            # 1. Setup Context (Profile, Thread, Project)
            profile = None
            try:
                if profile_id:
                    # [FIX] Offload blocking DB call
                    loop = asyncio.get_running_loop()
                    profile = await loop.run_in_executor(
                        None, lambda: self.orchestrator.store.get_profile(profile_id)
                    )
            except Exception:
                pass

            # Detect Project (simplified from generator.py)
            from backend.app.services.project.project_creation_helper import (
                detect_and_create_project_if_needed,
            )

            project_id, _ = await detect_and_create_project_if_needed(
                message=request.message,
                workspace_id=workspace_id,
                profile_id=profile_id,
                store=self.orchestrator.store,
                workspace=workspace,
                existing_project_id=None,
                create_on_medium_confidence=True,
            )

            # Thread ID
            thread_id = request.thread_id
            if not thread_id:
                thread_id = _get_or_create_default_thread(
                    workspace_id, self.orchestrator.store
                )

            # 2. Create User Event (Persist immediately)
            event_id = user_event_id or str(uuid.uuid4())
            user_event = MindEvent(
                id=event_id,
                timestamp=_utc_now(),
                actor=EventActor.USER,
                channel="local_workspace",
                profile_id=profile_id,
                project_id=project_id,
                workspace_id=workspace_id,
                thread_id=thread_id,
                event_type=EventType.MESSAGE,
                payload={
                    "message": request.message,
                    "files": request.files,
                    "mode": request.mode,
                },
                entity_ids=[],
                metadata={"async_processed": True},
            )
            # [FIX] Offload blocking DB call
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None, lambda: self.orchestrator.store.create_event(user_event)
            )
            logger.info(f"[AsyncChat] Created user event {user_event.id}")

            # Update thread stats
            try:
                # [FIX] Offload blocking DB calls to thread pool
                loop = asyncio.get_running_loop()
                message_count = await loop.run_in_executor(
                    None,
                    lambda: self.orchestrator.store.events.count_messages_by_thread(
                        workspace_id=workspace_id, thread_id=thread_id
                    ),
                )
                await loop.run_in_executor(
                    None,
                    lambda: self.orchestrator.store.conversation_threads.update_thread(
                        thread_id=thread_id,
                        last_message_at=datetime.now(timezone.utc),
                        message_count=message_count,
                    ),
                )
            except Exception as e:
                logger.warning(f"Failed to update thread stats: {e}")

            # 3. Pipeline Stages (Persist as events)

            # Determine Mode
            runtime_profile_store = WorkspaceRuntimeProfileStore(
                db_path=self.orchestrator.store.db_path
            )
            runtime_profile = runtime_profile_store.get_runtime_profile(workspace_id)
            if not runtime_profile:
                runtime_profile = runtime_profile_store.create_default_profile(
                    workspace_id
                )

            resolved_mode_enum = get_resolved_mode(workspace, runtime_profile)
            execution_mode = (
                resolved_mode_enum.value
                if resolved_mode_enum
                else (getattr(workspace, "execution_mode", None) or "qa")
            )

            # Intent Extraction Stage
            if execution_mode in ("execution", "hybrid"):
                locale = get_locale_from_context(profile=profile, workspace=workspace)
                user_message_preview = _smart_truncate_message(
                    request.message, max_length=60
                )
                intent_message = load_i18n_string(
                    "workspace.pipeline_stage.intent_extraction",
                    locale=locale,
                    default=f"分析中：理解你的需求「{user_message_preview}」，尋找適合的 Playbook。",
                ).format(user_message=user_message_preview)

                await self._create_pipeline_event(
                    workspace_id,
                    profile_id,
                    thread_id,
                    project_id,
                    "intent_extraction",
                    intent_message,
                    user_event.id,
                )

            # Context Building Stage
            locale = (
                get_locale_from_context(profile=profile, workspace=workspace) or "zh-TW"
            )
            context_message = load_i18n_string(
                "workspace.pipeline_stage.context_building",
                locale=locale,
                default="準備背景資訊：正在整理相關的文件與專案上下文。",
            )
            await self._create_pipeline_event(
                workspace_id,
                profile_id,
                thread_id,
                project_id,
                "context_building",
                context_message,
                user_event.id,
            )

            # 4. Check if workspace has preferred_agent (e.g., moltbot)
            # If so, route to WorkspaceAgentExecutor instead of LLM
            preferred_agent = getattr(workspace, "preferred_agent", None)

            if preferred_agent:
                logger.info(
                    f"[AsyncChat] Workspace has preferred_agent={preferred_agent}, "
                    f"routing to WorkspaceAgentExecutor"
                )

                from backend.app.services.workspace_agent_executor import (
                    WorkspaceAgentExecutor,
                    AgentExecutionResponse,
                )

                executor = WorkspaceAgentExecutor(workspace)
                agent_response: AgentExecutionResponse = await executor.execute(
                    task=request.message,
                    agent_id=preferred_agent,
                )

                # Create assistant event with agent response
                if agent_response.success:
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
                            "message": agent_response.output,
                            "agent_id": preferred_agent,
                            "trace_id": agent_response.trace_id,
                            "execution_time": agent_response.execution_time_seconds,
                        },
                        entity_ids=[],
                        metadata={
                            "external_agent": True,
                            "agent_id": preferred_agent,
                        },
                    )
                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(
                        None,
                        lambda: self.orchestrator.store.create_event(assistant_event),
                    )
                    logger.info(
                        f"[AsyncChat] External agent {preferred_agent} completed, "
                        f"trace_id={agent_response.trace_id}"
                    )
                else:
                    # Create error event for failed execution
                    error_msg = (
                        agent_response.error or "External agent execution failed"
                    )
                    await self._create_error_event(
                        workspace_id, profile_id, thread_id, error_msg
                    )
                    logger.error(
                        f"[AsyncChat] External agent {preferred_agent} failed: {error_msg}"
                    )

                logger.info(
                    f"[AsyncChat] Background task completed for {user_event.id}"
                )
                return  # Exit early, don't fall through to LLM

            # 5. Generate Response (Consume Stream) - Default LLM path

            # Setup dependencies for stream_llm_response
            from backend.features.workspace.chat.streaming.llm_streaming import (
                stream_llm_response,
            )
            from backend.features.workspace.chat.utils.llm_provider import (
                get_llm_provider_manager,
                get_llm_provider,
            )

            # Resolve Model Name with ultimate fallback
            model_name = request.model_name
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
                    logger.warning(
                        f"Failed to fetch default chat model from settings: {e}"
                    )

            if not model_name or str(model_name).strip() == "":
                model_name = "gpt-4"  # Ultimate safety fallback
                logger.info(f"Using ultimate fallback model_name: {model_name}")

            provider_manager = get_llm_provider_manager()
            provider, provider_type = get_llm_provider(
                model_name=model_name,
                llm_provider_manager=provider_manager,
                profile_id=profile_id,
                db_path=self.orchestrator.store.db_path,
            )

            # Build Context (Logic from generator.py)
            from backend.features.workspace.chat.streaming.context_builder import (
                build_streaming_context,
            )
            from backend.app.services.stores.timeline_items_store import (
                TimelineItemsStore,
            )

            # Instantiate TimelineItemsStore locally as it's required by context builder
            timeline_items_store = TimelineItemsStore(self.orchestrator.store.db_path)

            context_str = await build_streaming_context(
                workspace_id=workspace_id,
                message=request.message,
                profile_id=profile_id,
                workspace=workspace,
                store=self.orchestrator.store,
                timeline_items_store=timeline_items_store,
                model_name=model_name,
                thread_id=thread_id,
            )

            # Construct messages list for LLM
            messages = []
            if context_str:
                messages.append({"role": "system", "content": context_str})
            messages.append({"role": "user", "content": request.message})

            # Estimate token count (approx 4 chars per token)
            context_token_count = len(context_str) // 4 if context_str else 0

            logger.info(f"[AsyncChat] Consuming LLM stream for mode {execution_mode}")

            async for chunk in stream_llm_response(
                provider=provider,
                provider_type=provider_type,
                messages=messages,
                model_name=model_name,
                execution_mode=execution_mode,
                user_event_id=user_event.id,
                profile_id=profile_id,
                project_id=project_id,
                workspace_id=workspace_id,
                thread_id=thread_id,
                workspace=workspace,
                message=request.message,
                profile=profile,
                store=self.orchestrator.store,
                context_token_count=context_token_count,
                execution_playbook_result=None,
                openai_key=None,
            ):
                # We consume the stream to trigger internal logic (Assistant Event creation, Playbook Execution)
                pass

            logger.info(f"[AsyncChat] Background task completed for {user_event.id}")

            # Final update to thread stats
            try:
                message_count = self.orchestrator.store.events.count_messages_by_thread(
                    workspace_id=workspace_id, thread_id=thread_id
                )
                self.orchestrator.store.conversation_threads.update_thread(
                    thread_id=thread_id,
                    last_message_at=datetime.now(timezone.utc),
                    message_count=message_count,
                )
            except Exception:
                pass

        except Exception as e:
            logger.error(f"[AsyncChat] Error in background task: {e}", exc_info=True)
            # Create Error Event
            await self._create_error_event(workspace_id, profile_id, thread_id, str(e))

    async def _create_pipeline_event(
        self, workspace_id, profile_id, thread_id, project_id, stage, message, run_id
    ):
        """Create a persisted pipeline stage event"""
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
        # [FIX] Offload blocking DB call
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        await loop.run_in_executor(
            None, lambda: self.orchestrator.store.create_event(event)
        )
        logger.info(f"[AsyncChat] Persisted pipeline event: {stage}")

    async def _create_error_event(self, workspace_id, profile_id, thread_id, error_msg):
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
            metadata={"is_error": True},
        )
        # Offload blocking DB call
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        await loop.run_in_executor(
            None, lambda: self.orchestrator.store.create_event(event)
        )
