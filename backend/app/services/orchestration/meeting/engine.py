"""
Meeting Engine — slim orchestrator.

Composes mixin modules for event emission, governance, prompts,
action items, text generation, dispatch, session lifecycle,
tool discovery, IR compilation, and L2/L3 bridge into a single
MeetingEngine class.

The run() method drives a bounded multi-round governance meeting.
"""

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.app.models.meeting_session import MeetingSession, MeetingStatus
from backend.app.models.mindscape import EventType
from backend.app.services.conversation.execution_launcher import ExecutionLauncher
from backend.app.services.orchestration.meeting_agents import (
    MEETING_ROLE_ROSTER,
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

logger = logging.getLogger(__name__)


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

        # S1: Agenda decomposition + RAG pre-fetch
        await self._stage_agenda_and_rag(user_message)

        # S2: Playbook cache + RequestContract compile
        await self._stage_compile_contract(user_message)

        # S3: Multi-round deliberation
        decision, planner_proposals, critic_notes, converged = (
            await self._stage_deliberation(user_message)
        )

        # S4: Action intent extraction + null-tool gate
        action_intents, action_items = await self._stage_extract_actions(
            decision=decision,
            user_message=user_message,
            critic_notes=critic_notes,
            planner_proposals=planner_proposals,
        )

        # S5: Policy gate check + emit action items
        self._stage_policy_gate_and_emit(action_items)

        # S6: Decompose + IR compile + DAG dispatch
        compiled_ir, dispatch_result = await self._stage_decompose_and_dispatch(
            decision=decision,
            action_intents=action_intents,
            action_items=action_items,
            handoff_in=handoff_in,
        )

        # S7: Finalize (minutes, supervisor, completion status)
        return self._stage_finalize(
            user_message=user_message,
            decision=decision,
            critic_notes=critic_notes,
            action_items=action_items,
            converged=converged,
            compiled_ir=compiled_ir,
            dispatch_result=dispatch_result,
        )

    # ------------------------------------------------------------------ #
    # Pipeline stage methods (extracted from run())                        #
    # ------------------------------------------------------------------ #

    async def _stage_agenda_and_rag(self, user_message: str) -> None:
        """S1: Agenda decomposition + RAG tool pre-fetch."""
        await self._emit_meeting_stage("agenda", "分析議程中…")
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

            if agenda and len(agenda) > 1:
                per_k = max(5, 40 // len(agenda))
                seen_ids: set = set()
                combined: list = []
                for item in agenda:
                    aug = self._verb_augment(str(item))
                    q = f"{item} {aug}".strip() if aug else str(item)
                    hits = await retrieve_relevant_tools(
                        q,
                        top_k=per_k,
                        workspace_id=ws_id,
                    )
                    for h in hits:
                        if h["tool_id"] not in seen_ids:
                            seen_ids.add(h["tool_id"])
                            combined.append(h)

                msg_aug = self._verb_augment(str(user_message))
                msg_q = f"{user_message} {msg_aug}".strip()
                msg_hits = await retrieve_relevant_tools(
                    msg_q,
                    top_k=per_k,
                    workspace_id=ws_id,
                )
                for h in msg_hits:
                    if h["tool_id"] not in seen_ids:
                        seen_ids.add(h["tool_id"])
                        combined.append(h)

                self._rag_tool_cache = combined
            else:
                self._rag_tool_cache = await retrieve_relevant_tools(
                    self._build_tool_query_from_context(),
                    top_k=40,
                    workspace_id=ws_id,
                )

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

        await self._emit_meeting_stage("tool_discovery", "搜尋可用工具…")

    async def _stage_compile_contract(self, user_message: str) -> None:
        """S2: Preload playbooks + compile RequestContract."""
        self._available_playbooks_cache = await self._async_load_installed_playbooks()

        await self._emit_meeting_stage("deliberation", "開始多角色討論…")

        self._request_contract = None
        try:
            from backend.app.models.request_contract import RequestContract

            agenda = getattr(self.session, "agenda", None) or []
            self._request_contract = await RequestContract.compile_with_llm(
                user_message=user_message,
                agenda=agenda,
                workspace_id=getattr(self.session, "workspace_id", ""),
                model_name=self.model_name,
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
                    f"第 {round_num}/{max_rounds} 輪 — Facilitator 發言中…",
                )
                facilitator_turn = await self._role_turn(
                    "facilitator",
                    round_num,
                    user_message,
                    planner_proposals=planner_proposals,
                    critic_notes=critic_notes,
                )
                self._emit_turn(facilitator_turn)

                await self._emit_meeting_stage(
                    "deliberation",
                    f"第 {round_num}/{max_rounds} 輪 — Planner 規劃中…",
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
                    await self._emit_meeting_stage(
                        "deliberation",
                        f"第 {round_num}/{max_rounds} 輪 — Critic 審查中…",
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
                    break

                self._emit_round_event(round_num, status="completed")
        except Exception as exc:
            run_error = exc
            logger.error(
                "Meeting engine failed at round %s: %s",
                self.session.round_count,
                exc,
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
        await self._emit_meeting_stage("action_items", "正在拆解行動項目…")
        action_intents = await self._build_action_items(
            decision=decision,
            user_message=user_message,
            critic_notes=critic_notes,
            planner_proposals=planner_proposals,
        )
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
        if all_null and has_tool_context:
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

        # Bridge: convert ActionIntents to dicts for legacy consumers
        action_items = [i.to_action_item_dict() for i in action_intents]
        return action_intents, action_items

    def _stage_policy_gate_and_emit(self, action_items: List[Dict[str, Any]]) -> None:
        """S5: Policy gate validation + emit action items via SSE."""
        try:
            from backend.app.services.orchestration.meeting.dispatch_policy_gate import (
                check_dispatch_policy,
            )
            from backend.app.services.stores.workspace_resource_binding_store import (
                WorkspaceResourceBindingStore,
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
        await self._emit_meeting_stage("dispatch", "準備派遣任務…")

        # L3 Dispatch Gate with real L5 supervision signals
        from backend.app.services.orchestration.meeting.dispatch_gate import (
            DispatchGate,
        )
        from backend.app.services.orchestration.supervision_signals_emitter import (
            SupervisionSignalsEmitter,
        )
        from backend.app.models.supervision_signals import SupervisionSignals

        real_signals = SupervisionSignals()  # safe default
        try:
            emitter = SupervisionSignalsEmitter()
            session_attempts = []
            try:
                from backend.app.models.phase_attempt import PhaseAttempt

                phase_attempts_meta = (self.session.metadata or {}).get(
                    "phase_attempts", {}
                )
                for attempt_dict in phase_attempts_meta.values():
                    try:
                        session_attempts.append(
                            PhaseAttempt.model_validate(attempt_dict)
                        )
                    except Exception:
                        pass
            except Exception:
                pass

            session_start = getattr(self.session, "created_at", None)
            real_signals = emitter.compute(
                attempts=session_attempts,
                session_start=session_start,
                session_metadata=self.session.metadata or {},
            )
            logger.debug(
                "L5→L3 signals: risk_remaining=%.2f retries=%d failure_rate=%.2f "
                "quality=%.2f acceptance=%.2f remediation_round=%d "
                "session_age=%.0fs budget_pressure=%s",
                real_signals.risk_budget_remaining,
                real_signals.retry_budget_remaining,
                real_signals.historical_failure_rate,
                real_signals.quality_score,
                real_signals.acceptance_pass_rate,
                real_signals.remediation_round,
                real_signals.session_age_s,
                real_signals.budget_pressure_high,
            )
        except Exception as exc:
            logger.warning("L5 signal computation failed, using safe defaults: %s", exc)

        dispatch_gate = DispatchGate(signals=real_signals)
        gate_result = dispatch_gate.evaluate(action_intents)

        dispatch_intent_ids = set(gate_result.dispatch_intents)
        dispatchable_intents = [
            i for i in action_intents if i.intent_id in dispatch_intent_ids
        ]

        for d in gate_result.clarify_intents:
            logger.info("L3 Gate CLARIFY: intent=%s reason=%s", d.intent_id, d.reason)
        for d in gate_result.deferred_intents:
            logger.info("L3 Gate DEFER: intent=%s reason=%s", d.intent_id, d.reason)
        for d in gate_result.shrunk_intents:
            logger.info(
                "L3 Gate SHRINK_SCOPE: intent=%s reason=%s", d.intent_id, d.reason
            )

        # Task Decomposer — expand action items into full phase DAG
        from backend.app.services.orchestration.task_decomposer import TaskDecomposer

        decomposer = None
        decomposed_phases = None
        try:
            from backend.app.services.orchestration.meeting.meeting_llm_adapter import (
                MeetingLLMAdapter,
            )

            llm_adapter = MeetingLLMAdapter.from_engine(self)

            from backend.app.services.orchestration.task_decomposer import (
                DecompositionPolicy,
            )

            scale = "standard"
            if self._request_contract:
                scale = self._request_contract.scale_estimate.value
            policy = DecompositionPolicy.from_scale(scale)

            decomposer = TaskDecomposer(
                llm_adapter=llm_adapter,
                model_name=self.model_name or "",
                decomposition_policy=policy,
                max_phases=policy.max_phases_per_wave,
            )
            decomposed_phases = await decomposer.decompose(
                decision=decision,
                action_items=action_items,
                available_playbooks=getattr(self, "_available_playbooks_cache", ""),
                available_tools=self._build_tool_inventory_block(),
                force=True,
            )
            logger.info(
                "TaskDecomposer produced %d phases from %d action items",
                len(decomposed_phases) if decomposed_phases else 0,
                len(action_items),
            )
        except Exception as exc:
            logger.warning("TaskDecomposer failed (non-fatal): %s", exc)

        # Compile TaskIR (only approved intents)
        compiled_ir = None
        try:
            compiled_ir = self._compile_to_task_ir(
                decision=decision,
                action_items=action_items,
                handoff_in=handoff_in,
                action_intents=dispatchable_intents,
            )
            if compiled_ir and decomposed_phases:
                compiled_ir.phases = decomposed_phases
                logger.info(
                    "TaskIR phases replaced by decomposer output (%d phases)",
                    len(decomposed_phases),
                )
        except Exception as exc:
            logger.warning("Failed to compile TaskIR from meeting: %s", exc)

        # Build supervisor callback for iterative decomposition (G3)
        async def _on_wave_complete(wave_summary, task_ir):
            """Supervisor callback — ask decomposer if more phases needed."""
            if not decomposer:
                return None
            try:
                return await decomposer.extend(
                    existing_phases=task_ir.phases,
                    wave_results=wave_summary.get("phase_results", {}),
                    decision=decision,
                    available_playbooks=getattr(self, "_available_playbooks_cache", ""),
                )
            except Exception as ext_exc:
                logger.warning(
                    "Iterative decomposition failed (non-fatal): %s", ext_exc
                )
                return None

        # DAG-walking dispatch via DispatchOrchestrator
        from backend.app.services.orchestration.dispatch_orchestrator import (
            DispatchOrchestrator,
        )

        orchestrator = DispatchOrchestrator(
            execution_launcher=self.execution_launcher,
            tasks_store=self.tasks_store,
            session=self.session,
            profile_id=self.profile_id,
            project_id=self.project_id,
            on_wave_complete=_on_wave_complete,
            handoff_registry_store=self._get_handoff_registry_store(),
            pack_dispatch_adapter=self._get_pack_dispatch_adapter(),
        )
        dispatch_result = await orchestrator.execute(
            task_ir=compiled_ir,
            action_items=action_items,
        )
        return compiled_ir, dispatch_result

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
        minutes_md = self._render_minutes(
            user_message=user_message,
            decision=decision,
            critic_notes=critic_notes,
            action_items=action_items,
            converged=converged,
        )

        self._close_session(
            minutes_md=minutes_md,
            action_items=action_items,
            dispatch_result=dispatch_result,
        )

        # B8: Run L2 Bridge extraction pipeline (non-fatal)
        self._run_l2_bridge_pipeline()

        self._emit_minutes_message(minutes_md)

        # 5C: Post-session supervision (true fire-and-forget)
        try:
            from backend.app.services.orchestration.meeting.meeting_supervisor import (
                MeetingSupervisor,
            )

            supervisor = MeetingSupervisor(
                tasks_store=self.tasks_store,
                session_store=self.session_store,
            )

            async def _supervisor_task():
                try:
                    summary = await supervisor.on_session_closed(self.session.id)
                    logger.info(
                        "Session %s quality score: %.2f (%d/%d succeeded)",
                        self.session.id,
                        summary.get("score", 0),
                        summary.get("succeeded", 0),
                        summary.get("total_tasks", 0),
                    )
                except Exception as inner_exc:
                    logger.warning(
                        "Supervisor scoring failed for session %s: %s",
                        self.session.id,
                        inner_exc,
                    )

            asyncio.create_task(_supervisor_task())
        except Exception as exc:
            logger.warning(
                "Supervisor hook failed for session %s: %s", self.session.id, exc
            )

        # Derive completion_status from dispatch results
        from backend.app.models.completion_status import ExecutionCompletionStatus

        completion_status = ExecutionCompletionStatus.ACCEPTED
        if dispatch_result:
            task_statuses = []
            for phase_result in dispatch_result.get("phase_results", []):
                status = phase_result.get("status", "")
                if status:
                    task_statuses.append(status)
            if task_statuses:
                completion_status = ExecutionCompletionStatus.from_task_statuses(
                    task_statuses, has_dispatched=True
                )
            elif not dispatch_result.get("phase_results"):
                completion_status = ExecutionCompletionStatus.COMPLETED

        return MeetingResult(
            session_id=self.session.id,
            minutes_md=minutes_md,
            decision=decision,
            action_items=action_items,
            event_ids=[e.id for e in self._events],
            task_ir=compiled_ir,
            dispatch_result=dispatch_result,
            completion_status=completion_status.value,
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
