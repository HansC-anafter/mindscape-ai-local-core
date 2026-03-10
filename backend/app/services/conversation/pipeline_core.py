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
    completion_status: Optional[str] = None  # ExecutionCompletionStatus value
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
            finalize_meeting_session,
        )
        from backend.app.services.conversation.ingress_router import IngressRouter
        from backend.app.models.route_decision import (
            RouteKind,
            TransitionKind,
        )

        result = PipelineResult()

        try:
            # --- Stage 0: Routing Decision (ADR-R1) ---
            executor_runtime = getattr(
                self.workspace, "resolved_executor_runtime", None
            ) or getattr(self.workspace, "executor_runtime", None)

            router = IngressRouter()
            route_decision = await router.decide(
                execution_mode=execution_mode,
                meeting_enabled=False,  # IngressRouter resolves via _check_project_meeting
                executor_runtime=executor_runtime,
                entry_point="chat",
                store=self.store,
                project_id=project_id,
            )

            # RouteDecision is authoritative (hard cutover complete)
            meeting_enabled = route_decision.route_kind == RouteKind.MEETING

            session = None
            if meeting_enabled:
                session = await ensure_meeting_session(
                    workspace_id,
                    thread_id,
                    self.session_store,
                    project_id,
                    user_message=message,
                    model_name=model_name,
                    executor_runtime=executor_runtime,
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

                # Enrich uploaded file metadata (aligned with pipeline_dispatch)
                raw_files = getattr(request, "files", None) or []
                uploaded_files = []
                if raw_files:
                    import os
                    import json as _json
                    from pathlib import Path

                    workspace_id_str = getattr(self.workspace, "id", None) or ""
                    uploads_dir = (
                        Path(os.getenv("UPLOADS_DIR", "data/uploads"))
                        / workspace_id_str
                    )
                    for f in raw_files:
                        if isinstance(f, dict):
                            uploaded_files.append(f)
                        elif isinstance(f, str):
                            file_id = f
                            # Read .meta.json sidecar for original filename
                            original_name = None
                            meta_path = uploads_dir / f"{file_id}.meta.json"
                            if meta_path.exists():
                                try:
                                    with open(meta_path) as mf:
                                        meta = _json.load(mf)
                                    original_name = meta.get("original_name")
                                except Exception:
                                    pass

                            # Glob for actual file, filter out sidecars
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
                                display_name = original_name or fpath.name
                                file_info = {
                                    "file_id": file_id,
                                    "file_name": display_name,
                                    "file_path": str(fpath),
                                    "file_type": fpath.suffix.lstrip("."),
                                }
                            else:
                                file_info = {"file_id": file_id}
                            uploaded_files.append(file_info)

                    # Step 2: FileDispatchEnricher for detected_type + analysis
                    if uploaded_files:
                        try:
                            from backend.app.services.conversation.file_dispatch_enricher import (
                                FileDispatchEnricher,
                            )

                            enricher = FileDispatchEnricher()
                            workspace_id_for_enrich = getattr(
                                self.workspace, "id", None
                            )
                            if workspace_id_for_enrich:
                                file_ctx = await enricher.enrich(
                                    workspace_id_for_enrich, uploaded_files
                                )
                                uploaded_files = file_ctx.files
                        except Exception as e:
                            logger.warning(
                                "FileDispatchEnricher failed in meeting branch: %s", e
                            )

                # Assemble MeetingExecutionContext with runtime snapshot
                from backend.app.models.meeting_execution_context import (
                    MeetingExecutionContext,
                )

                # Build RuntimeObservabilitySnapshot from selected runtime
                runtime_snapshot = None
                try:
                    from backend.app.models.runtime_observability_snapshot import (
                        RuntimeObservabilitySnapshot,
                    )
                    from backend.app.models.runtime_environment import (
                        RuntimeEnvironment,
                    )
                    from backend.app.database.engine import SessionLocalCore

                    if executor_runtime:
                        db = SessionLocalCore()
                        try:
                            runtime_env = (
                                db.query(RuntimeEnvironment)
                                .filter(RuntimeEnvironment.id == executor_runtime)
                                .first()
                            )
                            if runtime_env:
                                runtime_snapshot = RuntimeObservabilitySnapshot.from_runtime_environment(
                                    runtime_env, selection_reason="primary"
                                )
                        finally:
                            db.close()
                except Exception as rt_exc:
                    logger.warning("Q0 runtime snapshot failed (non-fatal): %s", rt_exc)

                execution_context = MeetingExecutionContext.assemble(
                    workspace=self.workspace,
                    runtime_profile=self.runtime_profile,
                    route_decision=route_decision,
                    runtime_snapshot=runtime_snapshot,
                )

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
                    execution_context=execution_context,
                )

                handoff_in = extract_handoff_in(request)

                meeting_result = await meeting_engine.run(
                    message, handoff_in=handoff_in
                )
                result.response_text = meeting_result.minutes_md
                result.events = [{"id": eid} for eid in meeting_result.event_ids]
                result.meeting_session_id = meeting_result.session_id
                result.completion_status = meeting_result.completion_status

                # Persist compiled TaskIR if present
                if meeting_result.task_ir:
                    await persist_meeting_task_ir(meeting_result.task_ir)
                    result.task_ir_id = meeting_result.task_ir.task_id
                    # Dispatch is handled inside engine.run() via DispatchOrchestrator
                    if meeting_result.dispatch_result:
                        result.dispatch_result = meeting_result.dispatch_result

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

            # --- Stage 3: Dispatch (uses RouteDecision) ---
            use_agent = route_decision.route_kind == RouteKind.GOVERNED

            if use_agent:
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
                # Record explicit RouteTransition
                router.record_transition(
                    route_decision,
                    TransitionKind.POST_RESPONSE_PLAYBOOK,
                    reason=f"post_response: execution_mode={execution_mode}",
                )
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
