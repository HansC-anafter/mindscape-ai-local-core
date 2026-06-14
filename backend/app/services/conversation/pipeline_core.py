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

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.app.services.conversation.pipeline_core_core.events import (
    emit_pipeline_stage,
)
from backend.app.services.conversation.pipeline_core_core.runtime import (
    process_pipeline,
)


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
    task_ir_artifacts: List[Dict[str, Any]] = field(default_factory=list)
    artifact_ids: List[str] = field(default_factory=list)
    artifact_file_paths: List[str] = field(default_factory=list)
    completion_status: Optional[str] = None
    run_intent_envelope: Optional[Dict[str, Any]] = None
    run_harness_selection: Optional[Dict[str, Any]] = None
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

        from backend.app.services.conversation.recovery_handler import RecoveryHandler

        stop_cond = runtime_profile.stop_conditions
        self.recovery_handler = RecoveryHandler(
            recovery_policy=runtime_profile.recovery_policy,
            max_retries=stop_cond.max_retries,
        )

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
        return await process_pipeline(
            pipeline=self,
            result_factory=PipelineResult,
            workspace_id=workspace_id,
            profile_id=profile_id,
            thread_id=thread_id,
            project_id=project_id,
            message=message,
            user_event_id=user_event_id,
            execution_mode=execution_mode,
            model_name=model_name,
            request=request,
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
        await emit_pipeline_stage(
            pipeline=self,
            workspace_id=workspace_id,
            profile_id=profile_id,
            thread_id=thread_id,
            project_id=project_id,
            stage=stage,
            message_text=message_text,
            run_id=run_id,
        )
