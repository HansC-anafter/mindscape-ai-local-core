"""
Pipeline Core - Unique decision center for chat message processing.

ADR-001: This module is the SOLE decision hub for:
- Intent extraction
- Execution plan generation
- Agent/LLM dispatch
- Quality gate checks
- Playbook trigger
- Meeting session lifecycle

llm_streaming.py is limited to pure LLM generation + SSE event output.
chat_orchestrator_service.py is the HTTP/async wrapper.
"""

import logging
import json
import uuid
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Result of a pipeline processing run."""

    events: List[Dict[str, Any]] = field(default_factory=list)
    response_text: str = ""
    playbook_code: Optional[str] = None
    execution_id: Optional[str] = None
    suggestion_cards: List[Dict[str, Any]] = field(default_factory=list)
    quality_gate_result: Optional[Dict[str, Any]] = None
    meeting_session_id: Optional[str] = None
    success: bool = True
    error: Optional[str] = None


class PipelineCore:
    """
    Unique decision center for chat message processing (ADR-001).

    Orchestrates the full pipeline:
    1. Intent extraction (execution/hybrid modes)
    2. Context building
    3. Agent or LLM dispatch
    4. Post-response: quality gate, playbook trigger
    5. Meeting session lifecycle

    Feature flag: controlled by ADR-002 priority logic.
    """

    def __init__(
        self,
        orchestrator_store,
        workspace,
        profile,
        runtime_profile,
    ):
        """
        Initialize PipelineCore.

        Args:
            orchestrator_store: MindscapeStore instance (events, threads, etc.)
            workspace: Workspace object
            profile: UserProfile object
            runtime_profile: WorkspaceRuntimeProfile with stop_conditions, recovery_policy, etc.
        """
        self.store = orchestrator_store
        self.workspace = workspace
        self.profile = profile
        self.runtime_profile = runtime_profile

        # Initialize RecoveryHandler with unified max_retries
        from app.services.conversation.recovery_handler import RecoveryHandler

        stop_cond = runtime_profile.stop_conditions
        self.recovery_handler = RecoveryHandler(
            recovery_policy=runtime_profile.recovery_policy,
            max_retries=stop_cond.max_retries,
        )

        # MeetingSession persistence (Phase 2)
        from app.services.stores.meeting_session_store import MeetingSessionStore

        self.session_store = MeetingSessionStore()

    async def process(
        self,
        workspace_id: str,
        profile_id: str,
        thread_id: str,
        project_id: str,
        message: str,
        user_event_id: str,
        execution_mode: str = "qa",
        model_name: Optional[str] = None,
        request: Optional[Any] = None,
    ) -> PipelineResult:
        """
        Process a chat message through the unified pipeline.

        This is the single entry point for ALL chat processing,
        replacing the dual paths in chat_orchestrator_service.py.

        Args:
            workspace_id: Workspace ID
            profile_id: Profile ID
            thread_id: Thread ID
            project_id: Project ID
            message: User message text
            user_event_id: User event ID (for linking response events)
            execution_mode: qa | execution | hybrid
            model_name: LLM model name (for LLM path)
            request: Original ChatRequest object (for extra fields)

        Returns:
            PipelineResult with events, response text, playbook info, etc.
        """
        result = PipelineResult()

        try:
            # --- Stage 0: MeetingSession lifecycle (Phase 2) ---
            session = await self._ensure_meeting_session(
                workspace_id,
                thread_id,
            )
            if session:
                result.meeting_session_id = session.id

            # --- Stage 1: Intent Extraction ---
            if execution_mode in ("execution", "hybrid"):
                await self._emit_pipeline_stage(
                    workspace_id,
                    profile_id,
                    thread_id,
                    project_id,
                    "intent_extraction",
                    f"Analyzing request to find suitable approach.",
                    user_event_id,
                )

            # --- Stage 2: Context Building ---
            await self._emit_pipeline_stage(
                workspace_id,
                profile_id,
                thread_id,
                project_id,
                "context_building",
                "Preparing context: gathering relevant documents and project context.",
                user_event_id,
            )

            from backend.features.workspace.chat.streaming.context_builder import (
                build_streaming_context,
            )
            from backend.app.services.stores.timeline_items_store import (
                TimelineItemsStore,
            )

            timeline_items_store = TimelineItemsStore(self.store.db_path)
            context_str = await build_streaming_context(
                workspace_id=workspace_id,
                message=message,
                profile_id=profile_id,
                workspace=self.workspace,
                store=self.store,
                timeline_items_store=timeline_items_store,
                model_name=model_name,
                thread_id=thread_id,
            )

            # --- Stage 3: Dispatch ---
            preferred_agent = getattr(self.workspace, "preferred_agent", None)

            if preferred_agent:
                result = await self._dispatch_agent(
                    workspace_id,
                    profile_id,
                    thread_id,
                    project_id,
                    message,
                    user_event_id,
                    preferred_agent,
                    context_str,
                    result,
                )
            else:
                result = await self._dispatch_llm(
                    workspace_id,
                    profile_id,
                    thread_id,
                    project_id,
                    message,
                    user_event_id,
                    execution_mode,
                    model_name,
                    context_str,
                    result,
                )

            # --- Stage 4: Post-response (playbook trigger) ---
            if result.success and execution_mode in ("execution", "hybrid"):
                result = await self._post_response_playbook(
                    workspace_id,
                    profile_id,
                    thread_id,
                    project_id,
                    message,
                    user_event_id,
                    execution_mode,
                    result,
                )

        except Exception as e:
            logger.error(f"[PipelineCore] Error: {e}", exc_info=True)
            result.success = False
            result.error = str(e)

        # --- Finalize MeetingSession (always runs) ---
        await self._finalize_meeting_session(result)

        return result

    # ============================================================
    # Stage 3a: Agent Dispatch
    # ============================================================

    async def _dispatch_agent(
        self,
        workspace_id,
        profile_id,
        thread_id,
        project_id,
        message,
        user_event_id,
        preferred_agent,
        context_str,
        result: PipelineResult,
    ) -> PipelineResult:
        """Dispatch to external agent runtime (e.g. Gemini CLI)."""
        from backend.app.services.workspace_agent_executor import (
            WorkspaceAgentExecutor,
            AgentExecutionResponse,
        )

        executor = WorkspaceAgentExecutor(self.workspace)
        agent_available = await executor.check_agent_available(preferred_agent)

        if not agent_available:
            result.success = False
            result.error = (
                f"Agent {preferred_agent} is unavailable: no runtime connected. "
                f"Start the CLI bridge or switch to Mindscape LLM."
            )
            return result

        await self._emit_pipeline_stage(
            workspace_id,
            profile_id,
            thread_id,
            project_id,
            "agent_dispatching",
            f"Dispatching task to agent {preferred_agent}...",
            user_event_id,
        )

        agent_response: AgentExecutionResponse = await executor.execute(
            task=message,
            agent_id=preferred_agent,
            context_overrides={
                "conversation_context": context_str or "",
                "thread_id": thread_id,
                "project_id": project_id,
            },
        )

        exec_time = agent_response.execution_time_seconds

        if agent_response.success:
            await self._emit_pipeline_stage(
                workspace_id,
                profile_id,
                thread_id,
                project_id,
                "agent_completed",
                f"Agent completed in {exec_time:.0f}s",
                user_event_id,
            )

            # Create assistant event
            from backend.app.models.events import MindEvent, EventActor, EventType

            assistant_event = MindEvent(
                id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc),
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
                    "execution_time": exec_time,
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
                lambda: self.store.create_event(assistant_event),
            )

            result.response_text = agent_response.output
            result.events.append(
                assistant_event.to_dict()
                if hasattr(assistant_event, "to_dict")
                else {"id": assistant_event.id}
            )
        else:
            result.success = False
            result.error = agent_response.error or "Agent execution failed"

        return result

    # ============================================================
    # Stage 3b: LLM Dispatch
    # ============================================================

    async def _dispatch_llm(
        self,
        workspace_id,
        profile_id,
        thread_id,
        project_id,
        message,
        user_event_id,
        execution_mode,
        model_name,
        context_str,
        result: PipelineResult,
    ) -> PipelineResult:
        """Dispatch to LLM streaming (pure generation, no decisions)."""
        from backend.features.workspace.chat.streaming.llm_streaming import (
            stream_llm_response,
        )
        from backend.features.workspace.chat.utils.llm_provider import (
            get_llm_provider_manager,
            get_llm_provider,
        )

        # Resolve model
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
                logger.warning(f"Failed to fetch default chat model: {e}")

        if not model_name or str(model_name).strip() == "":
            model_name = "gpt-4"

        provider_manager = get_llm_provider_manager()
        provider, provider_type = get_llm_provider(
            model_name=model_name,
            llm_provider_manager=provider_manager,
            profile_id=profile_id,
            db_path=self.store.db_path,
        )

        # Build messages
        messages = []
        if context_str:
            messages.append({"role": "system", "content": context_str})
        messages.append({"role": "user", "content": message})

        # SGR prompt injection
        sgr_enabled = False
        try:
            ws_metadata = self.workspace.metadata or {}
            sgr_enabled = ws_metadata.get("sgr_enabled", False)
        except Exception:
            pass

        if sgr_enabled:
            from app.services.sgr_reasoning_service import SGRReasoningService

            sgr_service = SGRReasoningService()
            messages = sgr_service.inject_sgr_prompt(messages)
            logger.info("[PipelineCore] SGR prompt injected")

        context_token_count = len(context_str) // 4 if context_str else 0

        # Collect full text from stream (stream_llm_response handles SSE + event creation)
        full_text = ""
        async for chunk in stream_llm_response(
            provider=provider,
            provider_type=provider_type,
            messages=messages,
            model_name=model_name,
            execution_mode=execution_mode,
            user_event_id=user_event_id,
            profile_id=profile_id,
            project_id=project_id,
            workspace_id=workspace_id,
            thread_id=thread_id,
            workspace=self.workspace,
            message=message,
            profile=self.profile,
            store=self.store,
            context_token_count=context_token_count,
            execution_playbook_result=None,
            openai_key=None,
        ):
            # Accumulate full text from chunks
            if chunk.startswith("data: "):
                try:
                    data = json.loads(chunk[6:].strip())
                    if data.get("type") == "chunk":
                        full_text += data.get("content", "")
                except Exception:
                    pass

        result.response_text = full_text
        return result

    # ============================================================
    # Stage 4: Post-response Playbook Trigger
    # ============================================================

    async def _post_response_playbook(
        self,
        workspace_id,
        profile_id,
        thread_id,
        project_id,
        message,
        user_event_id,
        execution_mode,
        result: PipelineResult,
    ) -> PipelineResult:
        """
        Handle post-response playbook decisions.

        This logic was previously scattered in llm_streaming.py
        (handle_hybrid_mode_response + handle_execution_mode_playbook_trigger).
        Now centralized here as the unique decision point.
        """
        full_text = result.response_text

        if execution_mode == "hybrid":
            result = await self._handle_hybrid_playbook(
                full_text,
                message,
                workspace_id,
                profile_id,
                result,
            )
        elif execution_mode == "execution":
            result = await self._handle_execution_playbook(
                full_text,
                workspace_id,
                profile_id,
                execution_mode,
                result,
            )

        return result

    async def _handle_hybrid_playbook(
        self,
        full_text,
        message,
        workspace_id,
        profile_id,
        result,
    ) -> PipelineResult:
        """Handle hybrid mode: parse Part1/Part2 and execute playbook."""
        try:
            from backend.features.workspace.chat.playbook.response_parser import (
                parse_agent_mode_response,
            )
            from backend.features.workspace.chat.playbook.executor import (
                execute_playbook_for_hybrid_mode,
            )

            parsed = parse_agent_mode_response(full_text)
            logger.info(
                f"[PipelineCore] Hybrid parse - Part1: {len(parsed['part1'])}, "
                f"Part2: {len(parsed['part2'])}, "
                f"Tasks: {len(parsed['executable_tasks'])}"
            )

            if parsed["executable_tasks"]:
                execution_result = await execute_playbook_for_hybrid_mode(
                    message=message,
                    executable_tasks=parsed["executable_tasks"],
                    workspace_id=workspace_id,
                    profile_id=profile_id,
                    profile=self.profile,
                    store=self.store,
                )
                if execution_result:
                    result.playbook_code = execution_result.get("playbook_code")
                    result.execution_id = execution_result.get("execution_id")
                    logger.info(
                        f"[PipelineCore] Hybrid playbook executed: "
                        f"{result.playbook_code}"
                    )
        except Exception as e:
            logger.warning(f"[PipelineCore] Hybrid playbook error: {e}", exc_info=True)

        return result

    async def _handle_execution_playbook(
        self,
        full_text,
        workspace_id,
        profile_id,
        execution_mode,
        result,
    ) -> PipelineResult:
        """Handle execution mode: check for playbook trigger."""
        try:
            from backend.features.workspace.chat.playbook.trigger import (
                check_and_trigger_playbook,
            )

            trigger_result = await check_and_trigger_playbook(
                full_text=full_text,
                workspace=self.workspace,
                workspace_id=workspace_id,
                profile_id=profile_id,
                execution_mode=execution_mode,
            )
            if trigger_result:
                result.playbook_code = trigger_result.get("playbook_code")
                result.execution_id = trigger_result.get("execution_id")
                logger.info(
                    f"[PipelineCore] Execution playbook triggered: "
                    f"{result.playbook_code}"
                )
        except Exception as e:
            logger.warning(
                f"[PipelineCore] Execution playbook error: {e}",
                exc_info=True,
            )

        return result

    # ============================================================
    # Helpers
    # ============================================================

    async def _emit_pipeline_stage(
        self,
        workspace_id,
        profile_id,
        thread_id,
        project_id,
        stage,
        message_text,
        run_id,
    ):
        """Persist a PIPELINE_STAGE event."""
        from backend.app.models.events import MindEvent, EventActor, EventType

        event = MindEvent(
            id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc),
            actor=EventActor.SYSTEM,
            channel="local_workspace",
            profile_id=profile_id,
            project_id=project_id,
            workspace_id=workspace_id,
            thread_id=thread_id,
            event_type=EventType.PIPELINE_STAGE,
            payload={
                "stage": stage,
                "message": message_text,
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
            None,
            lambda: self.store.create_event(event),
        )
        logger.info(f"[PipelineCore] Pipeline stage: {stage}")

    # ============================================================
    # MeetingSession Lifecycle (Phase 2)
    # ============================================================

    async def _ensure_meeting_session(
        self,
        workspace_id: str,
        thread_id: str,
    ):
        """Get or create the active MeetingSession for this workspace/thread.

        - If an active session exists, reuse it.
        - If not, create a new one.
        """
        try:
            loop = asyncio.get_running_loop()
            session = await loop.run_in_executor(
                None,
                lambda: self.session_store.get_active_session(
                    workspace_id,
                    thread_id,
                ),
            )
            if session:
                logger.info(f"[PipelineCore] Reusing active session {session.id}")
                return session

            # Create new session
            from app.models.meeting_session import MeetingSession

            new_session = MeetingSession.new(
                workspace_id=workspace_id,
                thread_id=thread_id,
            )
            await loop.run_in_executor(
                None,
                lambda: self.session_store.create(new_session),
            )
            logger.info(f"[PipelineCore] Created new session {new_session.id}")
            return new_session
        except Exception as e:
            logger.warning(
                f"[PipelineCore] MeetingSession lifecycle error: {e}",
                exc_info=True,
            )
            return None

    async def _finalize_meeting_session(
        self,
        result: PipelineResult,
    ):
        """Record pipeline artifacts back to the MeetingSession.

        Links playbook execution ID and traces to the session record.
        Does NOT end the session — that requires an explicit API call
        or idle timeout.
        """
        if not result.meeting_session_id:
            return

        try:
            loop = asyncio.get_running_loop()
            session = await loop.run_in_executor(
                None,
                lambda: self.session_store.get_by_id(result.meeting_session_id),
            )
            if not session:
                return

            # Append execution_id to decisions list if playbook was triggered
            if result.execution_id and result.execution_id not in session.decisions:
                session.decisions.append(result.execution_id)

            # Metadata enrichment
            run_meta = session.metadata.get("runs", [])
            run_meta.append(
                {
                    "playbook": result.playbook_code,
                    "execution_id": result.execution_id,
                    "success": result.success,
                    "error": result.error,
                }
            )
            session.metadata["runs"] = run_meta

            await loop.run_in_executor(
                None,
                lambda: self.session_store.update(session),
            )
            logger.info(
                f"[PipelineCore] Session {session.id} finalized "
                f"(decisions={len(session.decisions)})"
            )
        except Exception as e:
            logger.warning(
                f"[PipelineCore] Session finalize error: {e}",
                exc_info=True,
            )


# ============================================================
# Feature Flag Helper (ADR-002)
# ============================================================


def should_use_pipeline_core(workspace) -> bool:
    """
    ADR-002: Feature flag priority order.

    Global PIPELINE_CORE_ENABLED (kill switch) > workspace-level flag.
    """
    try:
        from backend.app.services.system_settings_store import SystemSettingsStore

        settings_store = SystemSettingsStore()
        global_setting = settings_store.get_setting("PIPELINE_CORE_ENABLED")
        global_flag = global_setting and str(global_setting.value).lower() == "true"
    except Exception:
        global_flag = False

    if not global_flag:
        return False  # Kill switch overrides everything

    # Workspace-level check
    try:
        ws_metadata = workspace.metadata or {}
        ws_flag = ws_metadata.get("pipeline_core_enabled")
        if ws_flag is None:
            return True  # Not set = follow global (full rollout stage)
        return bool(ws_flag)
    except Exception:
        return True
