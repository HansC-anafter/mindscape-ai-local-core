"""
DispatchOrchestrator — DAG walker with dependency gating.

Replaces BridgeDispatcher with a proper DAG-walking dispatcher that
tracks PhaseAttempts, respects dependency ordering, and writes
projection records for backward-compatible task queries.

Design:
  1. Build dependency graph from PhaseIR.depends_on
  2. Topological walk: dispatch ready phases (all deps completed)
  3. Dependency gate: if upstream FAILED → downstream SKIPPED
  4. Per-phase PhaseAttempt lifecycle tracking
  5. Projection: update legacy tasks store for API consumers
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.app.models.phase_attempt import PhaseAttempt
from backend.app.models.task_ir import PhaseIR, TaskIR
from backend.app.services.orchestration.dispatch_orchestrator_core.execution import (
    execute_task_ir,
)
from backend.app.services.orchestration.dispatch_orchestrator_core.execution_paths import (
    dispatch_agent,
    dispatch_tool,
    launch_playbook,
    project_to_task,
)
from backend.app.services.orchestration.dispatch_orchestrator_core.phase_dispatch import (
    dispatch_phase,
)
from backend.app.services.orchestration.playbook_alias_resolution import (
    load_playbook_spec,
    parse_playbook_codes,
    resolve_tool_name_playbook_alias,
)
from backend.app.services.orchestration.dispatch_orchestrator_core.runtime_context import (
    apply_meeting_command_transport_context,
    build_agent_conversation_context,
    build_agent_task,
    create_attempt,
    load_workspace,
    meeting_command_transport_context,
    publish_activity,
    resolve_agent_runtime,
    should_skip,
)
from backend.app.services.orchestration.dispatch_orchestrator_core.planner import (
    build_ir_provenance,
    derive_research_context,
    extract_playbook_code,
    looks_like_ig_work,
    normalize_phase_inputs,
)


class DispatchOrchestrator:
    """DAG-walking dispatch orchestrator.

    Accepts a compiled TaskIR and walks its phase graph, dispatching
    phases whose dependencies are satisfied. Tracks each dispatch as
    a PhaseAttempt for audit and retry.

    Args:
        execution_launcher: Callable for playbook/task dispatch (may be None).
        tasks_store: Legacy tasks store for projection writes.
        session: MeetingSession providing routing defaults.
        profile_id: Current user profile.
        project_id: Current project (may be None).
        skip_policy: 'skip_on_dep_failure' (default) or 'continue_on_dep_failure'.
    """

    def __init__(
        self,
        execution_launcher: Any = None,
        tasks_store: Any = None,
        session: Any = None,
        profile_id: str = "",
        project_id: Optional[str] = None,
        skip_policy: str = "skip_on_dep_failure",
        on_wave_complete=None,
        lens_injector=None,
        handoff_registry_store=None,
        pack_dispatch_adapter=None,
        available_playbooks_cache: str = "",
    ):
        self.execution_launcher = execution_launcher
        self.tasks_store = tasks_store
        self.session = session
        self.profile_id = profile_id
        self.project_id = project_id
        self.skip_policy = skip_policy

        # Optional supervisor callback after each wave.
        # Signature: async (wave_summary, task_ir) -> Optional[List[PhaseIR]]
        self._on_wave_complete = on_wave_complete

        self._attempts: Dict[str, PhaseAttempt] = {}

        # Result tracking for the artifact pipeline.
        self._phase_results: Dict[str, Dict[str, Any]] = {}

        # Optional lens injector for per-phase persona context.
        self._lens_injector = lens_injector

        # Optional idempotency registry (fail-open if unavailable).
        self._handoff_registry_store = handoff_registry_store

        # Optional spec-aware dispatch adapter.
        self._pack_dispatch_adapter = pack_dispatch_adapter
        self._available_playbooks_cache = available_playbooks_cache or ""
        self._known_playbook_codes = parse_playbook_codes(self._available_playbooks_cache)
        self._playbook_spec_cache: Dict[str, Optional[Dict[str, Any]]] = {}
        self._workspace_cache: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def execute(
        self,
        task_ir: Optional[TaskIR],
        action_items: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Walk the TaskIR DAG and dispatch all phases.

        Returns:
            Dict with dispatch summary (status, total, succeeded, failed,
            skipped, workspaces, attempts).
        """
        return await execute_task_ir(self, task_ir, action_items)

    # ------------------------------------------------------------------
    # Phase dispatch
    # ------------------------------------------------------------------

    async def _dispatch_phase(
        self,
        phase: PhaseIR,
        action_item: Dict[str, Any],
        task_ir_id: str,
    ) -> Dict[str, Any]:
        """Dispatch a single phase, creating a PhaseAttempt."""
        return await dispatch_phase(self, phase, action_item, task_ir_id)

    # ------------------------------------------------------------------
    # Adapter methods
    # ------------------------------------------------------------------

    async def _launch_playbook(
        self,
        playbook_code: str,
        action_item: Dict[str, Any],
        target_workspace_id: str,
        attempt: PhaseAttempt,
        ir_provenance: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Launch a playbook via execution_launcher.

        Matches the proven contract from _land_action_item:
        - inputs: meeting context dict (task, meeting_session_id, thread_id, workspace_id)
        - ctx: LocalDomainContext with actor_id + workspace_id
        - trace_id: unique per dispatch for tracking
        - session metadata: appends execution_id to session.metadata["execution_ids"]
        """
        return await launch_playbook(
            self,
            playbook_code=playbook_code,
            action_item=action_item,
            target_workspace_id=target_workspace_id,
            attempt=attempt,
            ir_provenance=ir_provenance,
        )

    async def _dispatch_tool(
        self,
        phase: PhaseIR,
        action_item: Dict[str, Any],
        target_workspace_id: str,
        attempt: PhaseAttempt,
        ir_provenance: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Dispatch a tool_execution task."""
        return await dispatch_tool(
            self,
            phase=phase,
            action_item=action_item,
            target_workspace_id=target_workspace_id,
            attempt=attempt,
            ir_provenance=ir_provenance,
        )

    async def _dispatch_agent(
        self,
        *,
        phase: PhaseIR,
        action_item: Dict[str, Any],
        target_workspace_id: str,
        attempt: PhaseAttempt,
        ir_provenance: Dict[str, Any],
        engine: str,
    ) -> Dict[str, Any]:
        """Dispatch a phase directly to the workspace executor runtime."""
        return await dispatch_agent(
            self,
            phase=phase,
            action_item=action_item,
            target_workspace_id=target_workspace_id,
            attempt=attempt,
            ir_provenance=ir_provenance,
            engine=engine,
        )

    def _project_to_task(
        self,
        phase: PhaseIR,
        action_item: Dict[str, Any],
        target_workspace_id: str,
        ir_provenance: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Write a projection record to legacy tasks store."""
        return project_to_task(
            self,
            phase=phase,
            action_item=action_item,
            target_workspace_id=target_workspace_id,
            ir_provenance=ir_provenance,
        )

    # ------------------------------------------------------------------
    # Dependency gating
    # ------------------------------------------------------------------

    def _should_skip(self, phase_id: str, phase_map: Dict[str, PhaseIR]) -> bool:
        """Check if a phase should be skipped due to failed dependencies.

        Respects PhaseIR.rollback_strategy (G3):
        - 'retry': do NOT skip — supervisor should re-queue
        - 'revert': skip and signal checkpoint rollback
        - 'skip' or default: skip propagation (original behavior)
        """
        return should_skip(self, phase_id, phase_map)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _create_attempt(self, phase: PhaseIR, task_ir_id: str) -> PhaseAttempt:
        """Create and register a new PhaseAttempt for a phase."""
        return create_attempt(self, phase, task_ir_id)

    def _meeting_command_transport_context(self) -> Dict[str, Any]:
        """Extract command-ledger correlation from the active MeetingEngine session."""
        return meeting_command_transport_context(self)

    def _apply_meeting_command_transport_context(
        self,
        inputs: Dict[str, Any],
    ) -> Dict[str, Any]:
        return apply_meeting_command_transport_context(self, inputs)

    async def _load_workspace(self, workspace_id: str) -> Any:
        return await load_workspace(self, workspace_id)

    @staticmethod
    def _resolve_agent_runtime(*, engine: str, workspace: Any) -> Optional[str]:
        return resolve_agent_runtime(engine=engine, workspace=workspace)

    @staticmethod
    def _build_agent_task(
        *,
        phase: PhaseIR,
        action_item: Dict[str, Any],
        inputs: Dict[str, Any],
    ) -> str:
        return build_agent_task(
            phase=phase,
            action_item=action_item,
            inputs=inputs,
        )

    @staticmethod
    def _build_agent_conversation_context(
        *,
        action_item: Dict[str, Any],
        inputs: Dict[str, Any],
        ir_provenance: Dict[str, Any],
    ) -> str:
        return build_agent_conversation_context(
            action_item=action_item,
            inputs=inputs,
            ir_provenance=ir_provenance,
        )

    @staticmethod
    def _resolve_capability_profile_model(action_item: Dict[str, Any]) -> Optional[str]:
        del action_item
        return None

    def _normalize_phase_inputs(
        self,
        phases: List[PhaseIR],
        action_items: List[Dict[str, Any]],
    ) -> None:
        """Hydrate weakly-specified meeting phases into executable inputs."""
        normalize_phase_inputs(
            phases=phases,
            action_items=action_items,
            session=self.session,
            available_playbooks_cache=self._available_playbooks_cache,
            project_id=self.project_id,
        )

    def _derive_research_context(
        self,
        phase: PhaseIR,
        phase_map: Dict[str, PhaseIR],
    ) -> tuple[Optional[str], Optional[int]]:
        """Infer a research query/max_results from upstream dependency hints."""
        return derive_research_context(
            phase=phase,
            phase_map=phase_map,
            session=self.session,
        )

    @staticmethod
    def _looks_like_ig_work(text: str) -> bool:
        """Detect caption/post-oriented phases and route them to IG mode."""
        return looks_like_ig_work(text)

    @staticmethod
    def _extract_playbook_code(engine: Optional[str]) -> Optional[str]:
        """Extract playbook code from engine string (e.g. 'playbook:generic')."""
        return extract_playbook_code(engine)

    def _build_ir_provenance(
        self,
        *,
        phase: PhaseIR,
        action_item: Dict[str, Any],
        engine: str,
    ) -> Dict[str, Any]:
        """Build a provenance snapshot without assuming optional PhaseIR fields exist."""
        return build_ir_provenance(
            phase=phase,
            action_item=action_item,
            engine=engine,
            session=self.session,
        )

    def _resolve_phase_playbook_alias(self, tool_name: Optional[str]) -> Optional[str]:
        """Recover playbook dispatch from tool-like decomposed phase output."""
        if not tool_name:
            return None
        return resolve_tool_name_playbook_alias(
            tool_name,
            known_playbook_codes=self._known_playbook_codes,
            get_playbook_spec=self._get_playbook_spec,
        )

    def _get_playbook_spec(self, playbook_code: str) -> Optional[Dict[str, Any]]:
        if playbook_code not in self._playbook_spec_cache:
            self._playbook_spec_cache[playbook_code] = load_playbook_spec(playbook_code)
        return self._playbook_spec_cache[playbook_code]

    async def _publish_activity(self, event_type: str, data: dict) -> None:
        """Publish event to workspace activity stream (fire-and-forget)."""
        await publish_activity(self, event_type, data)

    def get_attempt(self, phase_id: str) -> Optional[PhaseAttempt]:
        """Get the latest attempt for a phase."""
        return self._attempts.get(phase_id)

    def get_all_attempts(self) -> Dict[str, PhaseAttempt]:
        """Get all phase attempts."""
        return dict(self._attempts)
