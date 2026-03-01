"""
Pipeline Core -- Unique decision center for chat message processing.

ADR-001: This module is the SOLE decision hub for:
- Intent extraction
- Execution plan generation
- Agent/LLM dispatch (via pipeline_dispatch)
- Playbook trigger (via pipeline_playbook)
- Meeting session lifecycle (via pipeline_meeting)

llm_streaming.py is limited to pure LLM generation + SSE event output.
chat_orchestrator_service.py is the HTTP/async wrapper.
"""

import asyncio
import logging
import uuid
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
    dispatch_result: Optional[Dict[str, Any]] = None
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
        from backend.app.services.conversation.pipeline_dispatch import (
            dispatch_to_agent,
            dispatch_to_llm,
        )
        from backend.app.services.conversation.pipeline_playbook import (
            handle_post_response_playbook,
        )
        from backend.app.services.conversation.pipeline_meeting import (
            ensure_meeting_session,
            is_project_meeting_enabled,
            build_execution_launcher,
            extract_handoff_in,
            persist_meeting_task_ir,
            dispatch_task_ir,
            finalize_meeting_session,
        )

        result = PipelineResult()

        try:
            # --- Stage 0: MeetingSession lifecycle ---
            meeting_enabled = execution_mode == "meeting"
            if not meeting_enabled:
                meeting_enabled = await is_project_meeting_enabled(
                    project_id, self.store
                )

            session = None
            if meeting_enabled:
                session = await ensure_meeting_session(
                    workspace_id,
                    thread_id,
                    self.session_store,
                    project_id,
                    user_message=message,
                )
                if session:
                    result.meeting_session_id = session.id

            # --- Stage 0.5: Meeting branch ---
            if meeting_enabled:
                if not session:
                    raise RuntimeError("Failed to initialize meeting session")

                from backend.app.services.orchestration.meeting import (
                    MeetingEngine,
                )

                execution_launcher = build_execution_launcher(self.store)
                executor_runtime = getattr(
                    self.workspace, "resolved_executor_runtime", None
                ) or getattr(self.workspace, "executor_runtime", None)

                # Extract uploaded file metadata for tool coverage validation
                raw_files = getattr(request, "files", None) or []
                uploaded_files = []
                if raw_files:
                    for f in raw_files:
                        if isinstance(f, dict):
                            uploaded_files.append(f)
                        elif isinstance(f, str):
                            uploaded_files.append({"file_id": f})

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
                    uploaded_files=uploaded_files,
                )

                handoff_in = extract_handoff_in(request)

                meeting_result = await meeting_engine.run(
                    message, handoff_in=handoff_in
                )
                result.response_text = meeting_result.minutes_md
                result.events = [{"id": eid} for eid in meeting_result.event_ids]
                result.meeting_session_id = meeting_result.session_id

                # Persist compiled TaskIR if present
                if meeting_result.task_ir:
                    await persist_meeting_task_ir(meeting_result.task_ir)
                    result.task_ir_id = meeting_result.task_ir.task_id
                    dispatch = await dispatch_task_ir(
                        meeting_result.task_ir, self.store
                    )
                    if dispatch:
                        result.dispatch_result = dispatch

                # Early return path must still finalize session metadata.
                await finalize_meeting_session(result, self.session_store)
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
            from backend.app.services.stores.postgres.timeline_items_store import (
                PostgresTimelineItemsStore,
            )

            timeline_items_store = PostgresTimelineItemsStore()
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

            # Inject workspace instruction into context (feeds both agent and LLM dispatch)
            from backend.app.services.workspace_instruction_helper import (
                build_workspace_instruction_block,
            )

            ws_instruction, _src = build_workspace_instruction_block(
                self.workspace, caller="pipeline"
            )
            if ws_instruction:
                context_str = (
                    ws_instruction + "\n\n" + (context_str or "")
                    if context_str
                    else ws_instruction
                )

            # --- Stage 3: Dispatch ---
            executor_runtime = getattr(
                self.workspace, "resolved_executor_runtime", None
            ) or getattr(self.workspace, "executor_runtime", None)

            if executor_runtime:
                # Extract uploaded file metadata from original request
                _uploaded_files = getattr(request, "files", None) or []

                result = await dispatch_to_agent(
                    workspace_id=workspace_id,
                    profile_id=profile_id,
                    thread_id=thread_id,
                    project_id=project_id,
                    message=message,
                    user_event_id=user_event_id,
                    executor_runtime=executor_runtime,
                    context_str=context_str,
                    store=self.store,
                    workspace=self.workspace,
                    result=result,
                    emit_pipeline_stage=self._emit_pipeline_stage,
                    execution_mode=execution_mode,
                    model_name=model_name,
                    profile=self.profile,
                    uploaded_files=_uploaded_files,
                )
            else:
                result = await dispatch_to_llm(
                    workspace_id=workspace_id,
                    profile_id=profile_id,
                    thread_id=thread_id,
                    project_id=project_id,
                    message=message,
                    user_event_id=user_event_id,
                    execution_mode=execution_mode,
                    model_name=model_name,
                    context_str=context_str,
                    store=self.store,
                    workspace=self.workspace,
                    profile=self.profile,
                    result=result,
                )

            # --- Stage 4: Post-response (playbook trigger) ---
            if result.success and execution_mode in ("execution", "hybrid"):
                result = await handle_post_response_playbook(
                    execution_mode=execution_mode,
                    message=message,
                    workspace=self.workspace,
                    workspace_id=workspace_id,
                    profile_id=profile_id,
                    profile=self.profile,
                    store=self.store,
                    result=result,
                )

        except Exception as e:
            logger.error(f"[PipelineCore] Error: {e}", exc_info=True)
            result.success = False
            result.error = str(e)

        # --- Finalize MeetingSession (always runs) ---
        await finalize_meeting_session(result, self.session_store)

        return result

    # ============================================================
    # Pipeline Stage Event Emitter
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
