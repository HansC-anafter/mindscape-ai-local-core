"""
Pipeline Core - Unique decision center for chat message processing.

ADR-001: This module is the SOLE decision hub for:
- Intent extraction
- Execution plan generation
- Agent/LLM dispatch
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

from backend.app.models.mindscape import MindEvent, EventActor, EventType

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Result of a pipeline processing run."""

    events: List[Dict[str, Any]] = field(default_factory=list)
    response_text: str = ""
    playbook_code: Optional[str] = None
    execution_id: Optional[str] = None
    suggestion_cards: List[Dict[str, Any]] = field(default_factory=list)
    meeting_session_id: Optional[str] = None
    task_ir_id: Optional[str] = None
    success: bool = True
    error: Optional[str] = None


class PipelineCore:
    """
    Unique decision center for chat message processing (ADR-001).

    Orchestrates the full pipeline:
    1. Intent extraction (execution/hybrid modes)
    2. Context building
    3. Agent or LLM dispatch
    4. Post-response: playbook trigger
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
        from backend.app.services.conversation.recovery_handler import RecoveryHandler

        stop_cond = runtime_profile.stop_conditions
        self.recovery_handler = RecoveryHandler(
            recovery_policy=runtime_profile.recovery_policy,
            max_retries=stop_cond.max_retries,
        )

        # MeetingSession persistence (Phase 2)
        from backend.app.services.stores.meeting_session_store import (
            MeetingSessionStore,
        )

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
            # --- Stage 0: MeetingSession lifecycle (project-scoped when enabled) ---
            meeting_enabled = execution_mode == "meeting"
            if not meeting_enabled:
                meeting_enabled = await self._is_project_meeting_enabled(project_id)

            session = None
            if meeting_enabled:
                session = await self._ensure_meeting_session(
                    workspace_id,
                    thread_id,
                    project_id,
                )
                if session:
                    result.meeting_session_id = session.id

            # --- Stage 0.5: Meeting branch ---
            # Enter meeting engine when:
            # 1. execution_mode explicitly set to "meeting", OR
            # 2. project.metadata.meeting_enabled == true (resolved at L129-131)
            if meeting_enabled:
                if not session:
                    raise RuntimeError("Failed to initialize meeting session")

                from backend.app.services.orchestration.meeting import (
                    MeetingEngine,
                )

                execution_launcher = self._build_execution_launcher()
                executor_runtime = getattr(self.workspace, "executor_runtime", None)
                meeting_engine = MeetingEngine(
                    session=session,
                    store=self.store,
                    workspace=self.workspace,
                    runtime_profile=self.runtime_profile,
                    profile_id=profile_id,
                    thread_id=thread_id,
                    project_id=project_id,
                    execution_launcher=execution_launcher,
                    model_name=model_name,
                    executor_runtime=executor_runtime,
                )

                # Extract HandoffIn from request payload if present
                handoff_in = self._extract_handoff_in(request)

                meeting_result = await meeting_engine.run(
                    message, handoff_in=handoff_in
                )
                result.response_text = meeting_result.minutes_md
                result.events = [{"id": eid} for eid in meeting_result.event_ids]
                result.meeting_session_id = meeting_result.session_id

                # Persist compiled TaskIR if present
                if meeting_result.task_ir:
                    await self._persist_meeting_task_ir(meeting_result.task_ir)
                    result.task_ir_id = meeting_result.task_ir.task_id

                # Early return path must still finalize session metadata.
                await self._finalize_meeting_session(result)
                return result

            # --- Stage 1: Intent Extraction ---
            if execution_mode in ("execution", "hybrid"):
                await self._emit_pipeline_stage(
                    workspace_id,
                    profile_id,
                    thread_id,
                    project_id,
                    "intent_extraction",
                    "Analyzing request to find suitable approach.",
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
            executor_runtime = getattr(self.workspace, "executor_runtime", None)

            if executor_runtime:
                result = await self._dispatch_agent(
                    workspace_id,
                    profile_id,
                    thread_id,
                    project_id,
                    message,
                    user_event_id,
                    executor_runtime,
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
        executor_runtime,
        context_str,
        result: PipelineResult,
    ) -> PipelineResult:
        """Dispatch to external agent runtime (e.g. Gemini CLI)."""
        from backend.app.services.workspace_agent_executor import (
            WorkspaceAgentExecutor,
            AgentExecutionResponse,
        )

        executor = WorkspaceAgentExecutor(self.workspace)
        agent_available = await executor.check_agent_available(executor_runtime)

        if not agent_available:
            result.success = False
            result.error = (
                f"Agent {executor_runtime} is unavailable: no runtime connected. "
                f"Start the CLI bridge or switch to Mindscape LLM."
            )
            return result

        await self._emit_pipeline_stage(
            workspace_id,
            profile_id,
            thread_id,
            project_id,
            "agent_dispatching",
            f"Dispatching task to agent {executor_runtime}...",
            user_event_id,
        )

        agent_response: AgentExecutionResponse = await executor.execute(
            task=message,
            agent_id=executor_runtime,
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
            payload = {
                "message": agent_response.output,
                "agent_id": executor_runtime,
                "trace_id": agent_response.trace_id,
                "execution_time": exec_time,
            }
            metadata = {
                "external_agent": True,
                "agent_id": executor_runtime,
            }
            if result.meeting_session_id:
                payload["meeting_session_id"] = result.meeting_session_id
                metadata["meeting_session_id"] = result.meeting_session_id

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
                payload=payload,
                entity_ids=[],
                metadata=metadata,
            )
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                lambda: self.store.create_event(assistant_event),
            )

            result.response_text = agent_response.output
            result.events.append(
                assistant_event.dict()
                if hasattr(assistant_event, "dict")
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
            from backend.app.services.sgr_reasoning_service import (
                SGRReasoningService,
            )

            sgr_service = SGRReasoningService()
            messages = sgr_service.inject_sgr_prompt(messages)
            logger.info("[PipelineCore] SGR prompt injected")

        context_token_count = len(context_str) // 4 if context_str else 0

        # Collect full text from stream
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
            meeting_session_id=result.meeting_session_id,
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
        from backend.app.services.conversation.response_parser import (
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
            try:
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
                # Log but do not swallow - caller sees error in result
                logger.warning(
                    f"[PipelineCore] Hybrid playbook execution error: {e}",
                    exc_info=True,
                )

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
        from backend.features.workspace.chat.playbook.trigger import (
            check_and_trigger_playbook,
        )

        try:
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

    def _build_execution_launcher(self):
        """
        Build ExecutionLauncher for meeting action landing.

        Returns None on setup failure so meeting flow can degrade gracefully
        to task creation fallback.
        """
        try:
            from backend.app.services.playbook_service import PlaybookService
            from backend.app.services.conversation.execution_launcher import (
                ExecutionLauncher,
            )

            playbook_service = PlaybookService(store=self.store)
            return ExecutionLauncher(playbook_service=playbook_service)
        except Exception as e:
            logger.warning(
                f"[PipelineCore] Failed to initialize ExecutionLauncher for meeting mode: {e}",
                exc_info=True,
            )
            return None

    def _extract_handoff_in(self, request: Optional[Any]) -> Optional[Any]:
        """Extract HandoffIn from request payload if present.

        Args:
            request: Original ChatRequest object.

        Returns:
            HandoffIn instance or None.
        """
        if not request:
            return None
        handoff_data = getattr(request, "handoff_in", None)
        if not handoff_data:
            return None
        from backend.app.models.handoff import HandoffIn

        if isinstance(handoff_data, dict):
            return HandoffIn(**handoff_data)
        if isinstance(handoff_data, HandoffIn):
            return handoff_data
        return None

    async def _persist_meeting_task_ir(self, task_ir) -> None:
        """Persist compiled TaskIR with upsert semantics.

        Uses delete-then-create for full replacement to ensure
        governance, phases, and metadata are fully persisted.

        Args:
            task_ir: Compiled TaskIR from meeting engine.
        """
        try:
            from backend.app.services.stores.task_ir_store import TaskIRStore

            db_path = getattr(self.store, "db_path", None)
            if not db_path:
                logger.warning(
                    "[PipelineCore] Cannot persist TaskIR: no db_path on store"
                )
                return

            store = TaskIRStore(db_path=db_path)
            existing = store.get_task_ir(task_ir.task_id)
            if existing:
                store.delete_task_ir(task_ir.task_id)
                try:
                    store.create_task_ir(task_ir)
                except Exception as create_err:
                    # Recovery: re-create from existing to avoid data loss
                    logger.critical(
                        "[PipelineCore] Create failed after delete for %s, "
                        "re-inserting original: %s",
                        task_ir.task_id,
                        create_err,
                    )
                    store.create_task_ir(existing)
                    raise
            else:
                store.create_task_ir(task_ir)
            logger.info(
                "[PipelineCore] Persisted TaskIR %s (replaced=%s)",
                task_ir.task_id,
                existing is not None,
            )
        except Exception as e:
            logger.warning(
                "[PipelineCore] Failed to persist TaskIR: %s",
                e,
                exc_info=True,
            )

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
        loop = asyncio.get_running_loop()
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
        project_id: Optional[str] = None,
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
                    project_id,
                    thread_id,
                ),
            )
            if session:
                logger.info(f"[PipelineCore] Reusing active session {session.id}")
                return session

            # Create new session
            from backend.app.models.meeting_session import MeetingSession

            new_session = MeetingSession.new(
                workspace_id=workspace_id,
                project_id=project_id,
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

    async def _is_project_meeting_enabled(self, project_id: Optional[str]) -> bool:
        """Return whether persistent meeting is enabled on the project metadata."""
        if not project_id:
            return False
        try:
            loop = asyncio.get_running_loop()
            project = await loop.run_in_executor(
                None,
                lambda: self.store.get_project(project_id),
            )
            if not project:
                return False
            metadata = getattr(project, "metadata", {}) or {}
            raw = metadata.get("meeting_enabled")
            # Strict boolean: only True or "true" (not truthy strings like "1")
            return raw is True or (isinstance(raw, str) and raw.lower() == "true")
        except Exception as e:
            logger.warning(
                f"[PipelineCore] Failed to read project meeting flag: {e}",
                exc_info=True,
            )
            return False

    async def _finalize_meeting_session(
        self,
        result: PipelineResult,
    ):
        """Record pipeline artifacts back to the MeetingSession.

        Links playbook execution ID and traces to the session record.
        Does NOT end the session - that requires an explicit API call
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
