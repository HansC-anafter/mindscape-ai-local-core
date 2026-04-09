"""
Meeting Engine — slim orchestrator.

Composes mixin modules for event emission, governance, prompts,
action items, text generation, dispatch, session lifecycle,
tool discovery, IR compilation, and L2/L3 bridge into a single
MeetingEngine class.

The run() method drives a bounded multi-round governance meeting.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.app.models.meeting_session import MeetingSession, MeetingStatus
from backend.app.services.conversation.execution_launcher import ExecutionLauncher
from backend.app.services.orchestration.meeting_agents import (
    MEETING_TOPOLOGY,
    build_meeting_roster,
    DeliberationDepth,
    DEPTH_ROUND_CAPS,
    select_deliberation_depth,
)
from backend.app.services.orchestration.multi_agent_orchestrator import (
    MultiAgentOrchestrator,
)
from backend.app.services.stores.meeting_session_store import MeetingSessionStore
from backend.app.services.stores.tasks_store import TasksStore

from backend.app.services.orchestration.meeting._action_items import (
    MeetingActionItemsMixin,
)
from backend.app.services.orchestration.meeting._dispatch import MeetingDispatchMixin
from backend.app.services.orchestration.meeting._dispatch_pipeline import (
    stage_decompose_and_dispatch as meeting_stage_decompose_and_dispatch,
    stage_finalize as meeting_stage_finalize,
)
from backend.app.services.orchestration.meeting._events import MeetingEventsMixin
from backend.app.services.orchestration.meeting._generation import (
    MeetingGenerationMixin,
)
from backend.app.services.orchestration.meeting._governance import (
    MeetingGovernanceMixin,
)
from backend.app.services.orchestration.meeting._ir_compiler import (
    MeetingIRCompilerMixin,
)
from backend.app.services.orchestration.meeting._l2_bridge import MeetingL2BridgeMixin
from backend.app.services.orchestration.meeting._prompts import MeetingPromptsMixin
from backend.app.services.orchestration.meeting._session import MeetingSessionMixin
from backend.app.services.orchestration.meeting._tool_discovery import (
    MeetingToolDiscoveryMixin,
)
from backend.app.services.orchestration.meeting.round_router import (
    build_routing_warning_payload,
    build_executor_routing_graph,
    build_round_routing_graph,
    is_dynamic_sparse_routing_enabled,
    is_round_router_trace_enabled,
    ROUND_ROUTING_CONTEXT_COMPRESS_CHARS,
)

logger = logging.getLogger(__name__)

COMPILE_CONTRACT_PLAYBOOK_DISCOVERY_TIMEOUT_S = 8.0
COMPILE_CONTRACT_REQUEST_TIMEOUT_S = 20.0


def _utc_now_iso() -> str:
    """Return a timezone-aware UTC timestamp encoded for metadata storage."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RoleTurnResult:
    """Result of a single deliberation role turn in a meeting round."""

    role_id: str
    role_name: str
    round_number: int
    content: str
    converged: bool = False


@dataclass
class MeetingResult:
    """Final output of a completed meeting session."""

    session_id: str
    minutes_md: str
    decision: str
    action_items: List[Dict[str, Any]] = field(default_factory=list)
    event_ids: List[str] = field(default_factory=list)
    task_ir: Optional[Any] = None
    dispatch_result: Optional[Dict[str, Any]] = None
    completion_status: str = "accepted"  # ExecutionCompletionStatus value


class MeetingEngine(
    MeetingEventsMixin,
    MeetingGovernanceMixin,
    MeetingPromptsMixin,
    MeetingActionItemsMixin,
    MeetingGenerationMixin,
    MeetingIRCompilerMixin,
    MeetingDispatchMixin,
    MeetingL2BridgeMixin,
    MeetingSessionMixin,
    MeetingToolDiscoveryMixin,
):
    """Drives a bounded multi-role meeting with real LLM turns and action landing."""

    AGENDA_RAG_QUERY_TIMEOUT_S: float = 5.0
    AGENDA_RAG_TOTAL_BUDGET_S: float = 12.0

    def __init__(
        self,
        session: MeetingSession,
        store: Any,
        workspace: Any,
        runtime_profile: Any,
        profile_id: str,
        thread_id: Optional[str],
        project_id: Optional[str] = None,
        execution_launcher: Optional[ExecutionLauncher] = None,
        model_name: Optional[str] = None,
        executor_runtime: Optional[str] = None,
        uploaded_files: Optional[List[Dict[str, Any]]] = None,
        execution_context: Optional["MeetingExecutionContext"] = None,
    ):
        self.session = session
        # Pre-0: store contract — never None
        if store is None:
            from backend.app.services.mindscape_store import MindscapeStore

            store = MindscapeStore()
            logger.warning(
                "MeetingEngine received store=None, using fallback MindscapeStore"
            )
        self.store = store
        self.workspace = workspace
        self.runtime_profile = runtime_profile
        self.profile_id = profile_id
        self.thread_id = thread_id
        self.project_id = project_id
        self.session_store = MeetingSessionStore()
        self.execution_launcher = execution_launcher
        self.model_name = model_name
        self.executor_runtime = executor_runtime
        self.provider = None
        self._agent_executor = None
        self.tasks_store: Optional[TasksStore] = None
        try:
            self.tasks_store = TasksStore()
        except Exception as exc:
            logger.warning("MeetingEngine failed to initialize TasksStore: %s", exc)
        self._events: List[Any] = []
        self._turn_history: List[Dict[str, Any]] = []
        self._uploaded_files: List[Dict[str, Any]] = list(uploaded_files or [])
        self._pending_program_spec = None
        self._pending_program_spec_source = None
        self._governance_packet: Optional[Dict[str, Any]] = None
        self._memory_context_summary: str = ""
        self._world_memory_packet: Optional[Dict[str, Any]] = None
        self._world_card_projection: Optional[Dict[str, Any]] = None
        self._world_card_text: str = ""

        # Resolve locale from workspace settings
        self._locale = self._resolve_locale(workspace)

        # A1: Resolve EffectiveLens for prompt injection + hash
        self._effective_lens = None
        self._lens_hash = None
        try:
            from backend.app.services.stores.graph_store import GraphStore
            from backend.app.services.lens.effective_lens_resolver import (
                EffectiveLensResolver,
            )
            from backend.app.services.lens.session_override_store import (
                InMemorySessionStore,
            )

            graph_store = GraphStore()
            session_override_store = InMemorySessionStore()
            resolver = EffectiveLensResolver(graph_store, session_override_store)
            workspace_id = getattr(workspace, "id", None) or session.workspace_id
            self._effective_lens = resolver.resolve(
                profile_id=profile_id,
                workspace_id=workspace_id,
            )
            self._lens_hash = self._effective_lens.hash
        except Exception as exc:
            logger.warning("MeetingEngine failed to resolve EffectiveLens: %s", exc)

        # A1: Cache active intent IDs for prompt injection
        self._active_intent_ids = self._get_active_intent_ids()

        # Fetch project data for meeting context
        self._project_context = self._build_project_context()

        # Build workspace group asset map for cross-workspace dispatch
        self._asset_map_context = self._build_asset_map_context()

        # Build recent workflow evidence packet for meeting deliberation.
        self._workflow_evidence_context = self._build_workflow_evidence_context()

        # A4: Build dynamic roster from workspace/project context
        workspace_id = getattr(workspace, "id", None) or session.workspace_id
        self._roster = build_meeting_roster(
            workspace_id=workspace_id,
            project_id=self.project_id,
            workspace_metadata=getattr(workspace, "metadata", None),
        )

        self.orchestrator = MultiAgentOrchestrator(
            agent_roster=self._roster,
            topology=MEETING_TOPOLOGY,
            loop_budget=runtime_profile.loop_budget if runtime_profile else None,
            stop_conditions=(
                runtime_profile.stop_conditions if runtime_profile else None
            ),
        )
        stop_conditions = getattr(runtime_profile, "stop_conditions", None)
        self.max_retries = int(getattr(stop_conditions, "max_retries", 2) or 2)
        recovery_policy = getattr(runtime_profile, "recovery_policy", None)
        self.retry_strategy = str(
            getattr(recovery_policy, "retry_strategy", "exponential_backoff")
        )

        # Assemble MeetingExecutionContext
        from backend.app.models.meeting_execution_context import (
            MeetingExecutionContext,
        )

        if execution_context is not None:
            self.ctx = execution_context
        else:
            self.ctx = MeetingExecutionContext.assemble(
                workspace=workspace,
                runtime_profile=runtime_profile,
                route_decision=None,  # caller can pass via execution_context
            )

    def _get_handoff_registry_store(self):
        """Lazily instantiate HandoffRegistryStore for idempotency guard.

        Returns None if the store cannot be imported (fail-open at
        construction time — the store itself is fail-close at INSERT time).
        """
        try:
            from backend.app.services.stores.handoff_registry_store import (
                HandoffRegistryStore,
            )
            return HandoffRegistryStore()
        except Exception as exc:
            logger.warning(
                "MeetingEngine: HandoffRegistryStore unavailable, "
                "idempotency guard disabled: %s",
                exc,
            )
            return None

    def _get_pack_dispatch_adapter(self):
        """Lazily instantiate PackDispatchAdapter for spec-aware dispatch.

        Returns None if the adapter cannot be imported.
        """
        try:
            from backend.app.services.orchestration.pack_dispatch_adapter import (
                PackDispatchAdapter,
            )
            return PackDispatchAdapter()
        except Exception as exc:
            logger.warning(
                "MeetingEngine: PackDispatchAdapter unavailable: %s", exc
            )
            return None

    async def _emit_meeting_stage(self, stage: str, message: str) -> None:
        """Publish a meeting stage indicator via Redis for frontend display."""
        try:
            from backend.app.services.cache.async_redis import publish_meeting_chunk

            workspace_id = (
                getattr(self.workspace, "id", None) or self.session.workspace_id
            )
            session_id = getattr(self.session, "id", None) or ""
            await publish_meeting_chunk(
                workspace_id,
                {
                    "type": "meeting_stage",
                    "stage": stage,
                    "message": message,
                    "session_id": session_id,
                },
                getattr(self, "thread_id", None) or getattr(self.session, "thread_id", None) or session_id,
            )
        except Exception:
            pass  # non-fatal: UI just won't show the stage

    async def run(
        self,
        user_message: str,
        handoff_in: Optional[Any] = None,
    ) -> MeetingResult:
        """Execute a bounded meeting and return generated minutes + action items.

        Orchestrates a 7-stage pipeline:
          S1 agenda + RAG → S2 contract → S3 deliberation →
          S4 action extraction → S5 policy gate → S6 dispatch → S7 finalize.

        Args:
            user_message: User message that triggered the meeting.
            handoff_in: Optional HandoffIn for governance context.
        """
        # Cache user_message for _build_tool_query_from_context()
        # MUST be set before _rag_tool_cache pre-fetch below.
        self._last_user_message = user_message
        current_stage = "agenda_and_rag"

        try:
            # S1: Agenda decomposition + RAG pre-fetch
            self._mark_pipeline_stage_start(current_stage)
            await self._stage_agenda_and_rag(user_message)
            self._mark_pipeline_stage_complete(current_stage)

            # S2: Playbook cache + RequestContract compile
            current_stage = "compile_contract"
            self._mark_pipeline_stage_start(current_stage)
            await self._stage_compile_contract(user_message)
            self._mark_pipeline_stage_complete(current_stage)

            # S3: Multi-round deliberation
            current_stage = "deliberation"
            self._mark_pipeline_stage_start(current_stage)
            decision, planner_proposals, critic_notes, converged = (
                await self._stage_deliberation(user_message)
            )
            self._mark_pipeline_stage_complete(current_stage)

            # S4: Action intent extraction + null-tool gate
            current_stage = "extract_actions"
            self._mark_pipeline_stage_start(current_stage)
            action_intents, action_items = await self._stage_extract_actions(
                decision=decision,
                user_message=user_message,
                critic_notes=critic_notes,
                planner_proposals=planner_proposals,
            )
            self._mark_pipeline_stage_complete(current_stage)

            # S5: Policy gate check + emit action items
            current_stage = "policy_gate"
            self._mark_pipeline_stage_start(current_stage)
            self._stage_policy_gate_and_emit(action_items)
            self._mark_pipeline_stage_complete(current_stage)

            # S6: Decompose + IR compile + DAG dispatch
            current_stage = "dispatch"
            self._mark_pipeline_stage_start(current_stage)
            compiled_ir, dispatch_result = await self._stage_decompose_and_dispatch(
                decision=decision,
                action_intents=action_intents,
                action_items=action_items,
                handoff_in=handoff_in,
            )
            self._mark_pipeline_stage_complete(current_stage)

            # S7: Finalize (minutes, supervisor, completion status)
            current_stage = "finalize"
            self._mark_pipeline_stage_start(current_stage)
            result = self._stage_finalize(
                user_message=user_message,
                decision=decision,
                critic_notes=critic_notes,
                action_items=action_items,
                converged=converged,
                compiled_ir=compiled_ir,
                dispatch_result=dispatch_result,
            )
            self._mark_pipeline_stage_complete(current_stage)
            return result
        except Exception as exc:
            self._mark_pipeline_stage_failed(current_stage, exc)
            self._persist_pre_deliberation_failure_if_needed(current_stage, exc)
            raise

    def _mark_pipeline_stage_start(self, stage: str) -> None:
        """Persist the current pipeline stage for mid-run inspection."""
        self._pipeline_stage_started_at_monotonic = time.monotonic()
        if self.session.metadata is None:
            self.session.metadata = {}
        self.session.metadata["pipeline_stage"] = stage
        self.session.metadata["pipeline_stage_status"] = "started"
        self.session.metadata["pipeline_stage_started_at"] = _utc_now_iso()
        self.session.metadata["pipeline_stage_updated_at"] = (
            self.session.metadata["pipeline_stage_started_at"]
        )
        self._append_pipeline_stage_history(stage, "started")
        self._persist_session_diagnostics(
            f"Meeting pipeline stage started: session={self.session.id} stage={stage}"
        )

    def _mark_pipeline_stage_complete(self, stage: str) -> None:
        """Persist stage completion timing for postmortem analysis."""
        duration_ms = self._pipeline_stage_duration_ms()
        if self.session.metadata is None:
            self.session.metadata = {}
        self.session.metadata["pipeline_stage"] = stage
        self.session.metadata["pipeline_stage_status"] = "completed"
        self.session.metadata["pipeline_stage_duration_ms"] = duration_ms
        self.session.metadata["pipeline_stage_updated_at"] = _utc_now_iso()
        self._append_pipeline_stage_history(
            stage,
            "completed",
            duration_ms=duration_ms,
        )
        self._persist_session_diagnostics(
            "Meeting pipeline stage completed: "
            f"session={self.session.id} stage={stage} duration_ms={duration_ms}"
        )

    def _mark_pipeline_stage_failed(self, stage: str, exc: Exception) -> None:
        """Persist the last known failing stage even if the session never started."""
        duration_ms = self._pipeline_stage_duration_ms()
        if self.session.metadata is None:
            self.session.metadata = {}
        self.session.metadata["pipeline_stage"] = stage
        self.session.metadata["pipeline_stage_status"] = "failed"
        self.session.metadata["pipeline_stage_duration_ms"] = duration_ms
        self.session.metadata["pipeline_stage_error"] = str(exc)
        self.session.metadata["pipeline_stage_updated_at"] = _utc_now_iso()
        self._append_pipeline_stage_history(
            stage,
            "failed",
            duration_ms=duration_ms,
            error=str(exc),
        )
        self._persist_session_diagnostics(
            "Meeting pipeline stage failed: "
            f"session={self.session.id} stage={stage} duration_ms={duration_ms} "
            f"error={exc}"
        )

    def _append_pipeline_stage_history(
        self,
        stage: str,
        status: str,
        *,
        duration_ms: Optional[int] = None,
        error: Optional[str] = None,
    ) -> None:
        """Append a compact pipeline-stage history entry to session metadata."""
        if self.session.metadata is None:
            self.session.metadata = {}
        history = self.session.metadata.setdefault("pipeline_stage_history", [])
        entry: Dict[str, Any] = {
            "stage": stage,
            "status": status,
            "timestamp": _utc_now_iso(),
        }
        if duration_ms is not None:
            entry["duration_ms"] = duration_ms
        if error:
            entry["error"] = error
        history.append(entry)

    def _pipeline_stage_duration_ms(self) -> int:
        started = getattr(self, "_pipeline_stage_started_at_monotonic", None)
        if started is None:
            return 0
        return int(max(0.0, time.monotonic() - started) * 1000)

    def _persist_session_diagnostics(self, log_message: str) -> None:
        try:
            self.session_store.update(self.session)
        except Exception as exc:
            logger.warning("Failed to persist meeting session diagnostics: %s", exc)
        logger.info(log_message)

    def _persist_round_progress(self, round_number: int, status: str) -> None:
        """Persist the latest deliberation round progress for live polling."""
        if self.session.metadata is None:
            self.session.metadata = {}
        self.session.metadata["last_round_status"] = status
        self.session.metadata["last_round_updated_at"] = _utc_now_iso()
        try:
            self.session_store.update(self.session)
        except Exception as exc:
            logger.warning(
                "Failed to persist meeting round progress: session=%s round=%s status=%s error=%s",
                self.session.id,
                round_number,
                status,
                exc,
            )
        else:
            logger.info(
                "Persisted meeting round progress: session=%s round=%s status=%s",
                self.session.id,
                round_number,
                status,
            )

    def _persist_round_routing_graph(self, graph: Any) -> None:
        """Persist the latest round routing graph for session-first polling."""
        if self.session.metadata is None:
            self.session.metadata = {}
        graph_payload = graph.model_dump(mode="json")
        self.session.metadata["last_round_routing_graph"] = graph_payload
        history = self.session.metadata.setdefault("round_routing_graph_history", [])
        history.append(graph_payload)
        if len(history) > 10:
            del history[:-10]
        try:
            self.session_store.update(self.session)
        except Exception as exc:
            logger.warning(
                "Failed to persist round routing graph: session=%s round=%s error=%s",
                self.session.id,
                graph_payload.get("round_number"),
                exc,
            )
        else:
            logger.info(
                "Persisted round routing graph: session=%s round=%s edges=%s",
                self.session.id,
                graph_payload.get("round_number"),
                len(graph_payload.get("edges", [])),
            )

    def _persist_round_routing_warning(
        self,
        warning_payload: Dict[str, Any],
    ) -> None:
        """Persist the latest routing warning for session-first polling."""
        if self.session.metadata is None:
            self.session.metadata = {}
        payload = {
            **warning_payload,
            "meeting_session_id": self.session.id,
            "detected_at": _utc_now_iso(),
        }
        self.session.metadata["last_round_routing_warning"] = payload
        history = self.session.metadata.setdefault("round_routing_warning_history", [])
        history.append(payload)
        if len(history) > 10:
            del history[:-10]
        try:
            self.session_store.update(self.session)
        except Exception as exc:
            logger.warning(
                "Failed to persist round routing warning: session=%s round=%s error=%s",
                self.session.id,
                payload.get("round_number"),
                exc,
            )
        else:
            logger.info(
                "Persisted round routing warning: session=%s round=%s types=%s",
                self.session.id,
                payload.get("round_number"),
                payload.get("warning_types"),
            )

    def _persist_round_routing_prompt_decision(self, graph: Any) -> None:
        """Persist prompt-mode history so session polling can show routing behavior."""
        metadata = getattr(graph, "metadata", None)
        if not isinstance(metadata, dict):
            return

        prompt_mode = str(metadata.get("routing_prompt_mode") or "").strip()
        prompt_role_id = str(metadata.get("routing_prompt_role_id") or "").strip()
        if not prompt_mode or not prompt_role_id:
            return

        if self.session.metadata is None:
            self.session.metadata = {}

        role_packet_stats = metadata.get("role_packet_stats") or {}
        role_stats = role_packet_stats.get(prompt_role_id) or {}
        payload = {
            "meeting_session_id": self.session.id,
            "round_number": getattr(graph, "round_number", None),
            "routing_stage": metadata.get("routing_stage"),
            "role_id": prompt_role_id,
            "prompt_mode": prompt_mode,
            "reason": metadata.get("routing_prompt_reason"),
            "estimated_context_chars": int(
                role_stats.get("estimated_context_chars") or 0
            ),
            "visible_packet_count": int(role_stats.get("visible_packet_count") or 0),
            "sparse_packet_count": int(role_stats.get("sparse_packet_count") or 0),
            "compressed_packet_char_limit": metadata.get(
                "compressed_packet_char_limit"
            ),
            "recorded_at": _utc_now_iso(),
        }
        self.session.metadata["last_round_routing_prompt_decision"] = payload
        history = self.session.metadata.setdefault(
            "round_routing_prompt_mode_history", []
        )
        history.append(payload)
        if len(history) > 20:
            del history[:-20]
        counts = self.session.metadata.setdefault("round_routing_prompt_mode_counts", {})
        counts[prompt_mode] = int(counts.get(prompt_mode) or 0) + 1
        total_decisions = sum(int(value or 0) for value in counts.values())
        sparse_count = int(counts.get("sparse") or 0)
        compressed_count = int(counts.get("compressed_sparse") or 0)
        fallback_count = int(counts.get("full_context_fallback") or 0)
        adaptive_count = compressed_count + fallback_count
        fallback_ratio = (
            round(fallback_count / total_decisions, 3) if total_decisions else 0.0
        )
        compressed_ratio = (
            round(compressed_count / total_decisions, 3) if total_decisions else 0.0
        )
        adaptive_ratio = (
            round(adaptive_count / total_decisions, 3) if total_decisions else 0.0
        )
        sparse_ratio = round(sparse_count / total_decisions, 3) if total_decisions else 0.0
        health_status = "healthy"
        health_reason = "stable_sparse"
        if fallback_count >= 2 or fallback_ratio >= 0.5:
            health_status = "critical"
            health_reason = "fallback_pressure"
        elif fallback_count >= 1:
            health_status = "warning"
            health_reason = "fallback_present"
        elif compressed_ratio >= 0.5 or adaptive_ratio >= 0.5:
            health_status = "warning"
            health_reason = "compression_pressure"
        self.session.metadata["round_routing_prompt_mode_summary"] = {
            "total_decisions": total_decisions,
            "sparse_count": sparse_count,
            "compressed_count": compressed_count,
            "fallback_count": fallback_count,
            "adaptive_count": adaptive_count,
            "sparse_ratio": sparse_ratio,
            "compressed_ratio": compressed_ratio,
            "fallback_ratio": fallback_ratio,
            "adaptive_ratio": adaptive_ratio,
            "health_status": health_status,
            "health_reason": health_reason,
            "last_prompt_mode": payload["prompt_mode"],
            "last_prompt_role_id": payload["role_id"],
            "last_prompt_reason": payload["reason"],
            "last_round_number": payload["round_number"],
            "last_recorded_at": payload["recorded_at"],
        }
        try:
            self.session_store.update(self.session)
        except Exception as exc:
            logger.warning(
                "Failed to persist round routing prompt decision: session=%s round=%s role=%s mode=%s error=%s",
                self.session.id,
                payload.get("round_number"),
                prompt_role_id,
                prompt_mode,
                exc,
            )
        else:
            logger.info(
                "Persisted round routing prompt decision: session=%s round=%s role=%s mode=%s",
                self.session.id,
                payload.get("round_number"),
                prompt_role_id,
                prompt_mode,
            )

    def _handle_round_routing_warning(
        self,
        graph: Any,
    ) -> Dict[str, Any] | None:
        """Emit and persist routing warnings when diagnostics detect anomalies."""
        warning_payload = build_routing_warning_payload(graph)
        if not warning_payload:
            return None
        payload = {
            "meeting_session_id": self.session.id,
            **warning_payload,
        }
        self._emit_round_routing_warning(payload)
        self._persist_round_routing_warning(payload)
        return payload

    def _mark_round_routing_fallback(
        self,
        graph: Any,
        *,
        next_role_id: str,
    ) -> bool:
        """Mark full-context fallback when sparse routing starves the next role."""
        metadata = getattr(graph, "metadata", None)
        if not isinstance(metadata, dict):
            return False

        starved_role_ids = set(metadata.get("starved_role_ids") or [])
        role_packet_stats = metadata.get("role_packet_stats") or {}
        next_role_stats = role_packet_stats.get(next_role_id) or {}
        role_status = str(next_role_stats.get("status") or "").strip().lower()

        if next_role_id in starved_role_ids or role_status == "starved":
            metadata["fallback_to_full_context"] = True
            metadata["fallback_role_id"] = next_role_id
            metadata["fallback_reason"] = "starved_role"
            return True

        metadata["fallback_to_full_context"] = False
        metadata.pop("fallback_role_id", None)
        metadata.pop("fallback_reason", None)
        return False

    def _mark_round_routing_prompt_mode(
        self,
        graph: Any,
        *,
        next_role_id: str,
    ) -> str:
        """Select sparse/compressed/full-context mode for the next role turn."""
        metadata = getattr(graph, "metadata", None)
        if not isinstance(metadata, dict):
            return "sparse"

        fallback_applied = self._mark_round_routing_fallback(
            graph,
            next_role_id=next_role_id,
        )
        if fallback_applied:
            metadata["routing_prompt_mode"] = "full_context_fallback"
            metadata["routing_prompt_role_id"] = next_role_id
            metadata["routing_prompt_reason"] = "starved_role"
            metadata["routing_health_status"] = "critical"
            metadata["routing_health_reason"] = "fallback_pressure"
            metadata.pop("compressed_packet_char_limit", None)
            return "full_context_fallback"

        role_packet_stats = metadata.get("role_packet_stats") or {}
        next_role_stats = role_packet_stats.get(next_role_id) or {}
        estimated_context_chars = int(
            next_role_stats.get("estimated_context_chars") or 0
        )
        if estimated_context_chars >= ROUND_ROUTING_CONTEXT_COMPRESS_CHARS:
            metadata["routing_prompt_mode"] = "compressed_sparse"
            metadata["routing_prompt_role_id"] = next_role_id
            metadata["routing_prompt_reason"] = "context_pressure"
            metadata["routing_health_status"] = "warning"
            metadata["routing_health_reason"] = "compression_pressure"
            metadata["compressed_packet_char_limit"] = 96
            return "compressed_sparse"

        metadata["routing_prompt_mode"] = "sparse"
        metadata["routing_prompt_role_id"] = next_role_id
        metadata["routing_prompt_reason"] = "normal"
        metadata["routing_health_status"] = "healthy"
        metadata["routing_health_reason"] = "stable_sparse"
        metadata.pop("compressed_packet_char_limit", None)
        return "sparse"

    def _prepare_round_routing_graph(
        self,
        *,
        round_number: int,
        next_role_id: str,
        facilitator_summary: str,
        decision: Optional[str] = None,
        planner_proposals: List[str],
        critic_notes: List[str],
    ) -> Any | None:
        """Build routing graph for sparse routing and optionally emit trace."""
        if not (
            is_round_router_trace_enabled() or is_dynamic_sparse_routing_enabled()
        ):
            self._current_round_routing_graph = None
            return

        if next_role_id == "executor":
            graph = build_executor_routing_graph(
                session_id=self.session.id,
                round_number=round_number,
                agenda=getattr(self.session, "agenda", None) or [],
                facilitator_summary=facilitator_summary,
                decision=decision or facilitator_summary,
                planner_proposals=planner_proposals,
                critic_notes=critic_notes,
            )
        else:
            graph = build_round_routing_graph(
                session_id=self.session.id,
                round_number=round_number,
                agenda=getattr(self.session, "agenda", None) or [],
                facilitator_summary=facilitator_summary,
                planner_proposals=planner_proposals,
                critic_notes=critic_notes,
            )
        graph.metadata["next_role_id"] = next_role_id
        self._mark_round_routing_prompt_mode(graph, next_role_id=next_role_id)
        self._current_round_routing_graph = graph
        self._persist_round_routing_prompt_decision(graph)
        self._handle_round_routing_warning(graph)
        if is_round_router_trace_enabled():
            self._emit_round_routing_graph(graph)
            self._persist_round_routing_graph(graph)
        return graph

    def _persist_pre_deliberation_failure_if_needed(
        self,
        stage: str,
        exc: Exception,
    ) -> None:
        """Close out planned sessions that fail before `_start_session()` runs."""
        if self.session.status != MeetingStatus.PLANNED or self.session.ended_at:
            return
        if self.session.metadata is None:
            self.session.metadata = {}
        self.session.status = MeetingStatus.FAILED
        self.session.metadata["pipeline_failure"] = {
            "stage": stage,
            "error": str(exc),
            "failed_at": _utc_now_iso(),
            "before_deliberation": True,
        }
        self.session.end()
        self._persist_session_diagnostics(
            "Meeting pipeline failed before deliberation: "
            f"session={self.session.id} stage={stage} error={exc}"
        )

    # ------------------------------------------------------------------ #
    # Pipeline stage methods (extracted from run())                        #
    # ------------------------------------------------------------------ #

    async def _stage_agenda_and_rag(self, user_message: str) -> None:
        """S1: Agenda decomposition + RAG tool pre-fetch."""
        await self._emit_meeting_stage("agenda", "Analyzing agenda...")
        await self._ensure_agenda_decomposed(user_message)

        # Pre-fetch RAG tool results using per-agenda multi-query strategy.
        # Each agenda item gets its own focused query so that mixed requests
        # (e.g. "research + content + images") don't let one dominant capability
        # crowd out the others.
        self._rag_tool_cache: list = []
        try:
            from backend.app.services.tool_rag import retrieve_relevant_tools

            agenda = getattr(self.session, "agenda", None) or []
            ws_id = self.session.workspace_id
            rag_deadline = time.monotonic() + self.AGENDA_RAG_TOTAL_BUDGET_S

            async def _retrieve_with_budget(
                query: str,
                *,
                top_k: int,
                label: str,
            ) -> list | None:
                remaining = self._layer_c_remaining_budget(rag_deadline)
                if remaining <= 0:
                    logger.info(
                        "Agenda RAG pre-fetch budget exhausted for session %s before %s",
                        self.session.id,
                        label,
                    )
                    return None
                try:
                    return await self._run_isolated_async_call(
                        lambda: retrieve_relevant_tools(
                            query,
                            top_k=top_k,
                            workspace_id=ws_id,
                        ),
                        timeout=min(self.AGENDA_RAG_QUERY_TIMEOUT_S, remaining),
                    )
                except asyncio.TimeoutError:
                    logger.info(
                        "Agenda RAG pre-fetch timed out for session %s on %s",
                        self.session.id,
                        label,
                    )
                    return []

            if agenda and len(agenda) > 1:
                per_k = max(5, 40 // len(agenda))
                seen_ids: set = set()
                combined: list = []
                for idx, item in enumerate(agenda, start=1):
                    aug = self._verb_augment(str(item))
                    q = f"{item} {aug}".strip() if aug else str(item)
                    hits = await _retrieve_with_budget(
                        q,
                        top_k=per_k,
                        label=f"agenda[{idx}]",
                    )
                    if hits is None:
                        break
                    for h in hits:
                        if h["tool_id"] not in seen_ids:
                            seen_ids.add(h["tool_id"])
                            combined.append(h)

                msg_aug = self._verb_augment(str(user_message))
                msg_q = f"{user_message} {msg_aug}".strip()
                msg_hits = await _retrieve_with_budget(
                    msg_q,
                    top_k=per_k,
                    label="user_message",
                )
                if msg_hits is not None:
                    for h in msg_hits:
                        if h["tool_id"] not in seen_ids:
                            seen_ids.add(h["tool_id"])
                            combined.append(h)

                self._rag_tool_cache = combined
            else:
                hits = await _retrieve_with_budget(
                    self._build_tool_query_from_context(),
                    top_k=40,
                    label="context_query",
                )
                self._rag_tool_cache = hits or []

            logger.debug(
                "Meeting RAG pre-fetch: %d tools cached for session %s (queries=%d)",
                len(self._rag_tool_cache),
                self.session.id if hasattr(self, "session") and self.session else "?",
                max(len(agenda), 1),
            )
        except Exception as exc:
            logger.warning(
                "Meeting RAG pre-fetch failed (manifest fallback active): %s", exc
            )

        await self._emit_meeting_stage("tool_discovery", "Discovering available tools...")

    async def _stage_compile_contract(self, user_message: str) -> None:
        """S2: Preload playbooks + compile RequestContract."""
        try:
            self._available_playbooks_cache = await asyncio.wait_for(
                self._async_load_installed_playbooks(),
                timeout=COMPILE_CONTRACT_PLAYBOOK_DISCOVERY_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "Installed playbook discovery timed out after %.1fs; continuing with fallback cache",
                COMPILE_CONTRACT_PLAYBOOK_DISCOVERY_TIMEOUT_S,
            )
            self._available_playbooks_cache = "(playbook discovery timed out)"
        except Exception as exc:
            logger.warning(
                "Installed playbook discovery failed before contract compile: %s",
                exc,
            )
            self._available_playbooks_cache = "(playbook discovery unavailable)"

        await self._emit_meeting_stage("deliberation", "Starting multi-role deliberation...")

        self._request_contract = None
        try:
            from backend.app.models.request_contract import RequestContract

            agenda = getattr(self.session, "agenda", None) or []
            self._request_contract = await asyncio.wait_for(
                RequestContract.compile_with_llm(
                    user_message=user_message,
                    agenda=agenda,
                    workspace_id=getattr(self.session, "workspace_id", ""),
                    model_name=self.model_name,
                ),
                timeout=COMPILE_CONTRACT_REQUEST_TIMEOUT_S,
            )
            if self.session.metadata is None:
                self.session.metadata = {}
            self.session.metadata["request_contract"] = (
                self._request_contract.model_dump()
            )
            logger.info(
                "RequestContract compiled: %d deliverables, scale=%s",
                len(self._request_contract.deliverables),
                self._request_contract.scale_estimate.value,
            )
        except Exception as exc:
            logger.warning("RequestContract compile failed (non-fatal): %s", exc)

    async def _stage_deliberation(
        self,
        user_message: str,
    ) -> tuple:
        """S3: Multi-round role deliberation loop.

        Returns:
            (decision, planner_proposals, critic_notes, converged)
        """
        await self._prefetch_governed_context_packet()
        self._start_session()
        base_max_rounds = max(1, int(getattr(self.session, "max_rounds", 1)))

        agenda = getattr(self.session, "agenda", None) or []
        depth = select_deliberation_depth(
            agenda_items=len(agenda),
            estimated_action_count=len(agenda),
            has_tool_ambiguity=len(self._rag_tool_cache) > 15,
            budget_headroom_pct=self.ctx.budget_headroom_pct,
        )
        self._deliberation_depth = depth
        max_rounds = min(
            base_max_rounds, DEPTH_ROUND_CAPS.get(depth.value, base_max_rounds)
        )
        logger.info(
            "Meeting depth=%s max_rounds=%d (base=%d) session=%s",
            depth.value,
            max_rounds,
            base_max_rounds,
            self.session.id,
        )

        planner_proposals: List[str] = []
        critic_notes: List[str] = []
        converged = False
        run_error: Optional[Exception] = None

        try:
            for round_num in range(1, max_rounds + 1):
                if self.orchestrator.should_stop():
                    self._emit_round_event(round_num, status="budget_exhausted")
                    break

                self.orchestrator.record_iteration()
                self._emit_round_event(round_num, status="started")

                await self._emit_meeting_stage(
                    "deliberation",
                    f"Round {round_num}/{max_rounds} - Facilitator turn in progress...",
                )
                facilitator_turn = await self._role_turn(
                    "facilitator",
                    round_num,
                    user_message,
                    planner_proposals=planner_proposals,
                    critic_notes=critic_notes,
                )
                self._emit_turn(facilitator_turn)
                self._current_round_number = round_num
                self._current_round_facilitator_summary = facilitator_turn.content
                self._prepare_round_routing_graph(
                    round_number=round_num,
                    next_role_id="planner",
                    facilitator_summary=facilitator_turn.content,
                    planner_proposals=planner_proposals,
                    critic_notes=critic_notes,
                )

                await self._emit_meeting_stage(
                    "deliberation",
                    f"Round {round_num}/{max_rounds} - Planner turn in progress...",
                )
                planner_turn = await self._role_turn(
                    "planner",
                    round_num,
                    user_message,
                    planner_proposals=planner_proposals,
                    critic_notes=critic_notes,
                )
                planner_proposals.append(planner_turn.content)
                self._emit_turn(planner_turn)
                self._emit_decision_proposal(planner_turn)

                # G2: Run CoverageAuditor after planner turn
                await self._try_coverage_audit(planner_turn.content, round_num)

                # Skip critic in SHALLOW depth to reduce latency
                if depth != DeliberationDepth.SHALLOW:
                    self._prepare_round_routing_graph(
                        round_number=round_num,
                        next_role_id="critic",
                        facilitator_summary=facilitator_turn.content,
                        planner_proposals=planner_proposals,
                        critic_notes=critic_notes,
                    )
                    await self._emit_meeting_stage(
                        "deliberation",
                        f"Round {round_num}/{max_rounds} - Critic review in progress...",
                    )
                    critic_turn = await self._role_turn(
                        "critic",
                        round_num,
                        user_message,
                        planner_proposals=planner_proposals,
                        critic_notes=critic_notes,
                    )
                    critic_notes.append(critic_turn.content)
                    self._emit_turn(critic_turn)

                self.session.round_count = round_num
                if self._is_converged(round_num, max_rounds, facilitator_turn.content):
                    converged = True
                    self._emit_round_event(round_num, status="converged")
                    self._persist_round_progress(round_num, "converged")
                    break

                self._emit_round_event(round_num, status="completed")
                self._persist_round_progress(round_num, "completed")
        except Exception as exc:
            if await self._try_salvage_deliberation_runtime_failure(
                error=exc,
                planner_proposals=planner_proposals,
                critic_notes=critic_notes,
            ):
                run_error = None
            else:
                run_error = exc
        if run_error:
            logger.error(
                "Meeting engine failed at round %s: %s",
                self.session.round_count,
                run_error,
            )
            self.session.status = MeetingStatus.FAILED
            self.session.end()

            # Generate partial minutes from completed rounds
            if self.session.round_count > 0 and planner_proposals:
                self.session.metadata["partial_rounds"] = self.session.round_count
                try:
                    partial_decision = planner_proposals[-1]
                    self._emit_decision_final(
                        decision=partial_decision,
                        round_number=self.session.round_count,
                    )
                    minutes_md = self._render_minutes(
                        user_message=user_message,
                        decision=partial_decision,
                        critic_notes=critic_notes,
                        action_items=[],
                        converged=False,
                    )
                    self.session.minutes_md = minutes_md
                    self._emit_minutes_message(minutes_md)
                    logger.info(
                        "Partial minutes generated for %d completed rounds",
                        self.session.round_count,
                    )
                except Exception as minutes_err:
                    logger.warning(
                        "Failed to generate partial minutes: %s", minutes_err
                    )

            try:
                self.session_store.update(self.session)
            except Exception:
                logger.warning("Failed to persist partial meeting session state")

        if run_error:
            raise RuntimeError(
                f"Meeting failed at round {self.session.round_count}: {run_error}"
            ) from run_error

        decision = (
            planner_proposals[-1] if planner_proposals else "No decision proposed."
        )
        self._emit_decision_final(
            decision=decision, round_number=self.session.round_count
        )
        return decision, planner_proposals, critic_notes, converged

    async def _try_salvage_deliberation_runtime_failure(
        self,
        *,
        error: Exception,
        planner_proposals: List[str],
        critic_notes: List[str],
    ) -> bool:
        """Convert late-round quota failures into a recoverable deliberation fallback.

        If the runtime quota/rate limit is hit after we already have at least one
        planner proposal, proceed with the latest planner proposal instead of
        failing the whole meeting. This keeps the pipeline moving into action
        extraction/dispatch when the only blocker is the next role turn budget.
        """
        if not self._is_runtime_quota_or_rate_limit_error(error):
            return False
        if not planner_proposals:
            return False

        fallback_round = max(int(getattr(self.session, "round_count", 0) or 0), len(planner_proposals))
        if self.session.metadata is None:
            self.session.metadata = {}

        self.session.metadata["partial_rounds"] = max(
            int(self.session.metadata.get("partial_rounds") or 0),
            fallback_round,
        )
        self.session.metadata["last_round_status"] = "quota_fallback"
        self.session.metadata["last_round_updated_at"] = _utc_now_iso()
        self.session.metadata["deliberation_fallback"] = {
            "reason": "runtime_quota_or_rate_limit",
            "decision_source": "latest_planner_proposal",
            "planner_proposal_count": len(planner_proposals),
            "critic_note_count": len(critic_notes),
            "error": str(error),
            "round_count_at_fallback": int(getattr(self.session, "round_count", 0) or 0),
            "fallback_round_number": fallback_round,
        }

        await self._emit_meeting_stage(
            "deliberation",
            "Runtime quota hit during deliberation; proceeding with the latest planner proposal.",
        )
        logger.warning(
            "Deliberation quota fallback engaged for session %s after %d planner proposal(s): %s",
            self.session.id,
            len(planner_proposals),
            error,
        )
        try:
            self.session_store.update(self.session)
        except Exception:
            logger.warning("Failed to persist deliberation quota fallback state")
        return True

    async def _stage_extract_actions(
        self,
        decision: str,
        user_message: str,
        critic_notes: List[str],
        planner_proposals: List[str],
    ) -> tuple:
        """S4: Build ActionIntents + null-tool gate retry.

        Returns:
            (action_intents, action_items) where action_items are legacy dicts.
        """
        await self._emit_meeting_stage("action_items", "Expanding action items...")
        action_intents = await self._build_action_items(
            decision=decision,
            user_message=user_message,
            critic_notes=critic_notes,
            planner_proposals=planner_proposals,
        )
        skip_null_actuator_retries = (
            getattr(self, "_pending_program_spec_source", None)
            == "request_contract_fallback"
        )
        if skip_null_actuator_retries:
            logger.info(
                "Skipping null-actuator retries for session %s because "
                "request-contract fallback ProgramSpec is already active.",
                self.session.id,
            )
        else:
            action_intents = await self._gap_refetch_for_null_actuators(
                action_intents,
                decision=decision,
                user_message=user_message,
                critic_notes=critic_notes,
                planner_proposals=planner_proposals,
            )

        # Pre-dispatch null-tool gate (fires only when ALL null)
        all_null = action_intents and not any(
            i.tool_name or i.playbook_code for i in action_intents
        )
        has_tool_context = self._has_workspace_tool_bindings() or bool(
            getattr(self, "_rag_tool_cache", [])
        )
        if all_null and has_tool_context and not skip_null_actuator_retries:
            logger.info(
                "Pre-dispatch null-tool gate triggered for session %s: "
                "workspace has explicit TOOL bindings but all action_items "
                "have tool_name=null and playbook_code=null.  Retrying executor turn.",
                self.session.id,
            )
            try:
                retry_intents = await self._build_action_items(
                    decision=decision,
                    user_message=user_message,
                    critic_notes=critic_notes,
                    planner_proposals=planner_proposals,
                )
                has_actuator_retry = any(
                    i.tool_name or i.playbook_code for i in retry_intents
                )
                if has_actuator_retry:
                    action_intents = retry_intents
                    actuator_count = sum(
                        1 for i in action_intents if i.tool_name or i.playbook_code
                    )
                    logger.info(
                        "Null-tool gate retry produced %d actuator-linked items",
                        actuator_count,
                    )
                    self._emit_event(
                        "tool_name_self_heal",
                        payload={
                            "session_id": self.session.id,
                            "trigger": "null_tool_gate_retry",
                            "actuator_count": actuator_count,
                        },
                    )
                else:
                    logger.warning(
                        "Null-tool gate retry did not produce actuator items; "
                        "keeping original action_items."
                    )
            except Exception as exc:
                logger.warning("Null-tool gate retry failed (non-fatal): %s", exc)
        elif all_null and has_tool_context and skip_null_actuator_retries:
            logger.info(
                "Pre-dispatch null-tool gate skipped for session %s because "
                "request-contract fallback ProgramSpec will bind deliverables during dispatch.",
                self.session.id,
            )

        self._persist_program_spec_from_final_intents(
            action_intents,
            decision=decision,
        )

        # Bridge: convert ActionIntents to dicts for legacy consumers
        action_items = [i.to_action_item_dict() for i in action_intents]
        return action_intents, action_items

    def _stage_policy_gate_and_emit(self, action_items: List[Dict[str, Any]]) -> None:
        """S5: Policy gate validation + emit action items via SSE."""
        try:
            from backend.app.services.orchestration.dispatch_orchestrator_core.planner import (
                normalize_action_item_inputs,
            )
            from backend.app.services.orchestration.meeting.dispatch_policy_gate import (
                check_dispatch_policy,
            )
            from backend.app.services.stores.workspace_resource_binding_store import (
                WorkspaceResourceBindingStore,
            )

            normalize_action_item_inputs(
                action_items=action_items,
                session=self.session,
            )

            policy_gate_report = check_dispatch_policy(
                action_items,
                workspace_id=self.session.workspace_id,
                available_playbooks_cache=getattr(
                    self, "_available_playbooks_cache", ""
                ),
                binding_store=WorkspaceResourceBindingStore(),
                workspace_data_sources=(
                    getattr(getattr(self, "workspace", None), "data_sources", None)
                    or {}
                ),
                contract_gate_mode=getattr(self, "_contract_gate_mode", "auto"),
                session_metadata=self.session.metadata,
                meeting_session_id=self.session.id,
                project_id=self.project_id,
            )
            if self.session.metadata is None:
                self.session.metadata = {}
            self.session.metadata["policy_gate"] = policy_gate_report
        except Exception as exc:
            logger.warning("Policy gate check failed (non-fatal): %s", exc)

        # Emit final action_items AFTER policy gate (SSE events carry landing_status)
        for item in action_items:
            self._emit_action_item(item)

    async def _stage_decompose_and_dispatch(
        self,
        decision: str,
        action_intents: list,
        action_items: List[Dict[str, Any]],
        handoff_in: Optional[Any] = None,
    ) -> tuple:
        """S6: Dispatch gate → TaskDecomposer → IR compile → DispatchOrchestrator.

        Returns:
            (compiled_ir, dispatch_result)
        """
        return await meeting_stage_decompose_and_dispatch(
            self,
            decision=decision,
            action_intents=action_intents,
            action_items=action_items,
            handoff_in=handoff_in,
        )

    def _stage_finalize(
        self,
        user_message: str,
        decision: str,
        critic_notes: List[str],
        action_items: List[Dict[str, Any]],
        converged: bool,
        compiled_ir: Optional[Any],
        dispatch_result: Optional[Dict[str, Any]],
    ) -> "MeetingResult":
        """S7: Minutes render, session close, L2 bridge, supervisor, completion status."""
        return meeting_stage_finalize(
            self,
            meeting_result_cls=MeetingResult,
            user_message=user_message,
            decision=decision,
            critic_notes=critic_notes,
            action_items=action_items,
            converged=converged,
            compiled_ir=compiled_ir,
            dispatch_result=dispatch_result,
        )

    async def _role_turn(
        self,
        role_id: str,
        round_num: int,
        user_message: str,
        decision: Optional[str] = None,
        planner_proposals: Optional[List[str]] = None,
        critic_notes: Optional[List[str]] = None,
    ) -> RoleTurnResult:
        """Execute a single deliberation role turn with prompt construction and LLM generation."""
        self.orchestrator.record_turn()
        role_def = self._roster[role_id]
        role = role_def.agent_name

        prompt = self._build_turn_prompt(
            role_id=role_id,
            round_num=round_num,
            user_message=user_message,
            decision=decision,
            planner_proposals=planner_proposals or [],
            critic_notes=critic_notes or [],
        )
        system_content = self._assemble_system_message(role_def)
        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": prompt},
        ]

        try:
            content = (
                await self._generate_text(
                    messages,
                    capability_profile=role_def.capability_profile,
                )
            ).strip()
            if not content:
                raise ValueError("empty LLM content")
        except Exception as exc:
            self.orchestrator.record_error()
            logger.error(
                "MeetingEngine turn failed for %s (round=%s): %s",
                role_id,
                round_num,
                exc,
            )
            raise RuntimeError(
                f"Meeting turn failed for role '{role_id}' at round {round_num}: {exc}"
            ) from exc

        turn = RoleTurnResult(
            role_id=role_id,
            role_name=role,
            round_number=round_num,
            content=content,
            converged=round_num >= 2,
        )
        self._turn_history.append(
            {
                "round": round_num,
                "role_id": role_id,
                "role": role,
                "content": content,
            }
        )
        return turn
