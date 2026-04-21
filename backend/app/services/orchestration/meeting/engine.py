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
import re
from copy import deepcopy
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
from backend.app.services.orchestration.default_input_resolvers import (
    apply_declarative_input_defaults,
    load_playbook_meeting_input_defaults,
)
from backend.app.services.orchestration.meeting._prompts import MeetingPromptsMixin
from backend.app.services.orchestration.meeting._session import MeetingSessionMixin
from backend.app.services.orchestration.meeting._tool_discovery import (
    MeetingToolDiscoveryMixin,
)

logger = logging.getLogger(__name__)

_MEETING_RAG_PREFETCH_TIMEOUT_SECONDS = 5.0


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
            if self.session.metadata is None:
                self.session.metadata = {}
            self.session.metadata["pipeline_stage"] = stage
            self.session.metadata["pipeline_stage_message"] = message
            self.session.metadata["pipeline_stage_updated_at"] = datetime.now(
                timezone.utc
            ).isoformat()
            self.session_store.update(self.session)
        except Exception:
            logger.debug("Meeting stage persistence failed for %s", self.session.id)
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
        await self._stage_compile_contract(user_message, handoff_in=handoff_in)

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
        action_intents, action_items = self._stage_policy_gate_and_emit(
            action_items,
            action_intents,
        )

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

            async def _lookup_tools(query: str, top_k: int) -> list[dict]:
                try:
                    return await asyncio.wait_for(
                        retrieve_relevant_tools(
                            query,
                            top_k=top_k,
                            workspace_id=ws_id,
                        ),
                        timeout=_MEETING_RAG_PREFETCH_TIMEOUT_SECONDS,
                    )
                except asyncio.TimeoutError:
                    logger.warning(
                        "Meeting RAG pre-fetch timed out for session %s query=%r",
                        getattr(self.session, "id", "?"),
                        str(query)[:120],
                    )
                    return []

            if agenda and len(agenda) > 1:
                per_k = max(5, 40 // len(agenda))
                seen_ids: set = set()
                combined: list = []
                for item in agenda:
                    aug = self._verb_augment(str(item))
                    q = f"{item} {aug}".strip() if aug else str(item)
                    hits = await _lookup_tools(q, per_k)
                    for h in hits:
                        if h["tool_id"] not in seen_ids:
                            seen_ids.add(h["tool_id"])
                            combined.append(h)

                msg_aug = self._verb_augment(str(user_message))
                msg_q = f"{user_message} {msg_aug}".strip()
                msg_hits = await _lookup_tools(msg_q, per_k)
                for h in msg_hits:
                    if h["tool_id"] not in seen_ids:
                        seen_ids.add(h["tool_id"])
                        combined.append(h)

                self._rag_tool_cache = combined
            else:
                self._rag_tool_cache = await _lookup_tools(
                    self._build_tool_query_from_context(),
                    40,
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

        await self._emit_meeting_stage("tool_discovery", "Discovering available tools...")

    async def _stage_compile_contract(
        self,
        user_message: str,
        handoff_in: Optional[Any] = None,
    ) -> None:
        """S2: Preload playbooks + compile RequestContract."""
        self._available_playbooks_cache = await self._async_load_installed_playbooks()

        await self._emit_meeting_stage("deliberation", "Starting multi-role deliberation...")

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

        request_contract_metadata = self._merge_request_contract_metadata(
            contract_data=(
                self._request_contract.model_dump()
                if self._request_contract is not None
                else None
            ),
            handoff_in=handoff_in,
            user_message=user_message,
        )
        if request_contract_metadata:
            if self.session.metadata is None:
                self.session.metadata = {}
            self.session.metadata["request_contract"] = request_contract_metadata
            try:
                from backend.app.models.request_contract import RequestContract

                self._request_contract = RequestContract.model_validate(
                    request_contract_metadata
                )
            except Exception:
                logger.debug(
                    "RequestContract metadata contains extensions beyond the core schema"
                )

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
        await self._emit_meeting_stage("action_items", "Expanding action items...")
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

    def _stage_policy_gate_and_emit(
        self,
        action_items: List[Dict[str, Any]],
        action_intents: Optional[List[Any]] = None,
    ) -> tuple[List[Any], List[Dict[str, Any]]]:
        """S5: Policy gate validation + emit action items via SSE."""
        action_intents, action_items = self._apply_request_contract_playbook_requests(
            action_items=action_items,
            action_intents=action_intents,
        )
        self._hydrate_action_items_for_policy_gate(action_items)
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

        action_intents, action_items = self._apply_request_contract_fallback_if_needed(
            action_items=action_items,
            action_intents=action_intents,
        )

        # Emit final action_items AFTER policy gate (SSE events carry landing_status)
        for item in action_items:
            self._emit_action_item(item)
        return action_intents or [], action_items

    def _merge_request_contract_metadata(
        self,
        *,
        contract_data: Optional[Dict[str, Any]],
        handoff_in: Optional[Any],
        user_message: str,
    ) -> Dict[str, Any]:
        """Merge handoff governance payload into request-contract metadata."""
        metadata = dict(contract_data or {})
        if not metadata and handoff_in is None:
            return {}
        metadata.setdefault("source_message", user_message)
        metadata.setdefault("workspace_scope", getattr(self.session, "workspace_id", ""))

        if handoff_in is None:
            normalized_playbook_requests = (
                self._extract_request_contract_playbook_requests(metadata)
            )
            normalized_playbook_input_defaults = (
                self._extract_request_contract_playbook_input_defaults(metadata)
            )
            if normalized_playbook_requests:
                metadata["playbook_requests"] = normalized_playbook_requests
            elif isinstance(metadata.get("playbook_requests"), list):
                metadata["playbook_requests"] = []
            if normalized_playbook_input_defaults:
                metadata["playbook_input_defaults"] = (
                    normalized_playbook_input_defaults
                )
            elif isinstance(metadata.get("playbook_input_defaults"), list):
                metadata["playbook_input_defaults"] = []
            return metadata

        goals = getattr(handoff_in, "goals", None) or []
        if goals and not metadata.get("goals"):
            metadata["goals"] = list(goals)

        acceptance_tests = getattr(handoff_in, "acceptance_tests", None)
        if acceptance_tests and not metadata.get("acceptance_tests"):
            metadata["acceptance_tests"] = list(acceptance_tests)

        if not metadata.get("deliverables"):
            deliverables = getattr(handoff_in, "deliverables", None) or []
            serialized_deliverables = [
                deliverable.model_dump()
                if hasattr(deliverable, "model_dump")
                else dict(deliverable)
                for deliverable in deliverables
                if isinstance(deliverable, dict) or hasattr(deliverable, "model_dump")
            ]
            if serialized_deliverables:
                metadata["deliverables"] = serialized_deliverables

        contract_constraints = metadata.get("constraints")
        if not isinstance(contract_constraints, dict):
            contract_constraints = {}
        governance_constraints = getattr(handoff_in, "governance_constraints", None)
        if isinstance(governance_constraints, dict) and governance_constraints:
            merged_constraints = dict(contract_constraints)
            for field_name, value in governance_constraints.items():
                if field_name not in merged_constraints or merged_constraints[field_name] in (
                    None,
                    "",
                    [],
                    {},
                ):
                    merged_constraints[field_name] = value
            metadata["constraints"] = merged_constraints
            metadata["governance_constraints"] = dict(governance_constraints)
        elif contract_constraints:
            metadata["constraints"] = contract_constraints

        context_attachments = getattr(handoff_in, "context_attachments", None)
        if isinstance(context_attachments, list) and context_attachments:
            metadata["context_attachments"] = [
                item for item in context_attachments if isinstance(item, dict)
            ]

        human_instructions = getattr(handoff_in, "human_instructions", None)
        if isinstance(human_instructions, str) and human_instructions.strip():
            metadata["human_instructions"] = human_instructions.strip()

        requested_output_type = getattr(handoff_in, "requested_output_type", None)
        if (
            isinstance(requested_output_type, str)
            and requested_output_type.strip()
            and not metadata.get("requested_output_type")
        ):
            metadata["requested_output_type"] = requested_output_type.strip()

        playbook_requests = getattr(handoff_in, "playbook_requests", None)
        if isinstance(playbook_requests, list) and not metadata.get("playbook_requests"):
            metadata["playbook_requests"] = list(playbook_requests)

        playbook_input_defaults = getattr(handoff_in, "playbook_input_defaults", None)
        if isinstance(playbook_input_defaults, list) and not metadata.get(
            "playbook_input_defaults"
        ):
            metadata["playbook_input_defaults"] = list(playbook_input_defaults)

        normalized_playbook_requests = self._extract_request_contract_playbook_requests(
            metadata
        )
        normalized_playbook_input_defaults = (
            self._extract_request_contract_playbook_input_defaults(metadata)
        )
        if normalized_playbook_requests:
            metadata["playbook_requests"] = normalized_playbook_requests
        elif isinstance(metadata.get("playbook_requests"), list):
            metadata["playbook_requests"] = []
        if normalized_playbook_input_defaults:
            metadata["playbook_input_defaults"] = normalized_playbook_input_defaults
        elif isinstance(metadata.get("playbook_input_defaults"), list):
            metadata["playbook_input_defaults"] = []

        return metadata

    def _apply_request_contract_playbook_requests(
        self,
        *,
        action_items: List[Dict[str, Any]],
        action_intents: Optional[List[Any]],
    ) -> tuple[List[Any], List[Dict[str, Any]]]:
        """Apply deterministic playbook requests carried by the request contract."""
        contract = self._get_request_contract_metadata()
        requested_items = self._extract_request_contract_playbook_requests(contract)
        if not requested_items:
            return action_intents or [], action_items
        replace_codes = {
            code
            for item in requested_items
            for code in self._clean_string_list(item.get("replace_existing_playbook_codes"))
        }
        normalized_items: List[Dict[str, Any]] = []
        replaced_count = 0
        for item in action_items:
            playbook_code = str(item.get("playbook_code") or "").strip()
            if playbook_code and playbook_code in replace_codes:
                replaced_count += 1
                continue
            normalized_items.append(item)
        normalized_items.extend(requested_items)

        from backend.app.models.action_intent import ActionIntent

        normalized_intents = [
            ActionIntent.from_action_item_dict(item) for item in normalized_items
        ]
        if self.session.metadata is None:
            self.session.metadata = {}
        self.session.metadata["request_contract_playbook_requests"] = [
            {
                "playbook_code": item.get("playbook_code"),
                "intent_id": item.get("intent_id"),
                "source": item.get("request_contract_source", "explicit"),
                "replace_existing_playbook_codes": self._clean_string_list(
                    item.get("replace_existing_playbook_codes")
                ),
                "handled_deliverable_ids": self._clean_string_list(
                    item.get("handled_deliverable_ids")
                ),
            }
            for item in requested_items
        ]
        return normalized_intents, normalized_items

    def _extract_request_contract_playbook_requests(
        self,
        contract: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Read explicit deterministic playbook requests from the request contract."""
        if not isinstance(contract, dict):
            return []

        raw_requests: List[Dict[str, Any]] = []
        explicit_request_markers = False

        direct_requests = contract.get("playbook_requests")
        if isinstance(direct_requests, list):
            explicit_request_markers = True
            raw_requests.extend(
                request for request in direct_requests if isinstance(request, dict)
            )

        governance_constraints = contract.get("governance_constraints")
        if not isinstance(governance_constraints, dict):
            governance_constraints = contract.get("constraints")
        if isinstance(governance_constraints, dict):
            nested_requests = governance_constraints.get("playbook_requests")
            if isinstance(nested_requests, list):
                explicit_request_markers = True
                raw_requests.extend(
                    request for request in nested_requests if isinstance(request, dict)
                )

        attachments = contract.get("context_attachments")
        attachment_requests, attachment_markers = self._collect_playbook_requests_from_attachments(
            attachments
        )
        explicit_request_markers = explicit_request_markers or attachment_markers
        raw_requests.extend(attachment_requests)

        normalized_requests: List[Dict[str, Any]] = []
        seen_requests = set()
        for raw_request in raw_requests:
            normalized = self._normalize_request_contract_playbook_request(
                raw_request=raw_request,
                contract=contract,
            )
            if not normalized:
                continue
            request_key = (
                str(normalized.get("playbook_code") or "").strip(),
                str(normalized.get("intent_id") or "").strip(),
            )
            if request_key in seen_requests:
                continue
            seen_requests.add(request_key)
            normalized_requests.append(normalized)
        return normalized_requests

    def _collect_playbook_requests_from_attachments(
        self,
        attachments: Any,
    ) -> tuple[List[Dict[str, Any]], bool]:
        if not isinstance(attachments, list):
            return [], False
        requests: List[Dict[str, Any]] = []
        found_marker = False
        for attachment in attachments:
            if not isinstance(attachment, dict):
                continue
            typed_marker = str(
                attachment.get("type")
                or attachment.get("kind")
                or attachment.get("name")
                or attachment.get("attachment_type")
                or ""
            ).strip()
            payload = attachment.get("payload")
            nested_request = attachment.get("playbook_request")
            nested_requests = attachment.get("playbook_requests")

            if typed_marker in {"playbook_request", "atomic_playbook_request"}:
                found_marker = True
                if isinstance(payload, dict):
                    requests.append(payload)
                elif isinstance(nested_request, dict):
                    requests.append(nested_request)
                continue

            if typed_marker in {"playbook_requests", "atomic_playbook_requests"}:
                found_marker = True
                if isinstance(payload, list):
                    requests.extend(
                        request for request in payload if isinstance(request, dict)
                    )
                elif isinstance(nested_requests, list):
                    requests.extend(
                        request
                        for request in nested_requests
                        if isinstance(request, dict)
                    )
                continue

            if isinstance(nested_request, dict):
                found_marker = True
                requests.append(nested_request)
            if isinstance(nested_requests, list):
                found_marker = True
                requests.extend(
                    request for request in nested_requests if isinstance(request, dict)
                )
        return requests, found_marker

    def _normalize_request_contract_playbook_request(
        self,
        *,
        raw_request: Dict[str, Any],
        contract: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        if not isinstance(raw_request, dict):
            return None

        playbook_code = str(raw_request.get("playbook_code") or "").strip()
        if not playbook_code:
            return None

        workspace_id = (
            str(
                raw_request.get("target_workspace_id")
                or raw_request.get("workspace_id")
                or getattr(self.session, "workspace_id", "")
            ).strip()
            or None
        )
        project_id = (
            str(
                raw_request.get("project_id")
                or getattr(self, "project_id", None)
                or ""
            ).strip()
            or None
        )

        input_params = (
            dict(raw_request.get("input_params"))
            if isinstance(raw_request.get("input_params"), dict)
            else {}
        )
        if workspace_id and "workspace_id" not in input_params:
            input_params["workspace_id"] = workspace_id
        if project_id and "project_id" not in input_params:
            input_params["project_id"] = project_id

        title = str(raw_request.get("title") or "").strip() or playbook_code
        description = str(raw_request.get("description") or "").strip() or (
            f"Execute request-contract playbook '{playbook_code}' with explicit "
            "inputs from the upstream contract."
        )
        replacement_codes = self._clean_string_list(
            raw_request.get("replace_existing_playbook_codes")
            or raw_request.get("replace_existing_codes")
        )
        if not replacement_codes:
            replacement_codes = [playbook_code]

        item: Dict[str, Any] = {
            "title": title,
            "description": description,
            "playbook_code": playbook_code,
            "engine": str(raw_request.get("engine") or "").strip()
            or f"playbook:{playbook_code}",
            "priority": str(raw_request.get("priority") or "").strip() or "high",
            "intent_id": str(raw_request.get("intent_id") or "").strip()
            or f"PB_{playbook_code}",
            "input_params": input_params,
            "replace_existing_playbook_codes": replacement_codes,
            "preserve_atomic_playbook": bool(
                raw_request.get("preserve_atomic_playbook", True)
            ),
        }
        if workspace_id:
            item["target_workspace_id"] = workspace_id

        handled_deliverable_ids = self._clean_string_list(
            raw_request.get("handled_deliverable_ids")
            or raw_request.get("deliverable_ids")
        )
        if handled_deliverable_ids:
            item["handled_deliverable_ids"] = handled_deliverable_ids

        for field_name in (
            "acceptance_tests",
            "governance_constraints",
            "context_attachments",
            "human_instructions",
            "requested_output_type",
            "capability_profile",
        ):
            candidate = raw_request.get(field_name)
            if candidate in (None, "", [], {}):
                candidate = contract.get(field_name)
            if candidate not in (None, "", [], {}):
                item[field_name] = candidate

        source = str(raw_request.get("request_contract_source") or "").strip()
        if source:
            item["request_contract_source"] = source

        return item

    def _extract_request_contract_playbook_input_defaults(
        self,
        contract: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Read generic playbook input bootstrap defaults from the contract."""
        if not isinstance(contract, dict):
            return []

        raw_defaults: List[Dict[str, Any]] = []

        direct_defaults = contract.get("playbook_input_defaults")
        if isinstance(direct_defaults, list):
            raw_defaults.extend(
                candidate for candidate in direct_defaults if isinstance(candidate, dict)
            )

        governance_constraints = contract.get("governance_constraints")
        if not isinstance(governance_constraints, dict):
            governance_constraints = contract.get("constraints")
        if isinstance(governance_constraints, dict):
            nested_defaults = governance_constraints.get("playbook_input_defaults")
            if isinstance(nested_defaults, list):
                raw_defaults.extend(
                    candidate
                    for candidate in nested_defaults
                    if isinstance(candidate, dict)
                )

        attachment_defaults = self._collect_playbook_input_defaults_from_attachments(
            contract.get("context_attachments")
        )
        raw_defaults.extend(attachment_defaults)

        normalized_defaults: List[Dict[str, Any]] = []
        seen_defaults = set()
        for raw_default in raw_defaults:
            normalized = self._normalize_request_contract_playbook_input_default(
                raw_default
            )
            if not normalized:
                continue
            default_key = (
                str(normalized.get("playbook_code") or "").strip(),
                tuple(normalized.get("deliverable_ids") or []),
                tuple(sorted(normalized.get("input_params", {}).keys())),
            )
            if default_key in seen_defaults:
                continue
            seen_defaults.add(default_key)
            normalized_defaults.append(normalized)
        return normalized_defaults

    def _collect_playbook_input_defaults_from_attachments(
        self,
        attachments: Any,
    ) -> List[Dict[str, Any]]:
        if not isinstance(attachments, list):
            return []
        defaults: List[Dict[str, Any]] = []
        for attachment in attachments:
            if not isinstance(attachment, dict):
                continue
            typed_marker = str(
                attachment.get("type")
                or attachment.get("kind")
                or attachment.get("name")
                or attachment.get("attachment_type")
                or ""
            ).strip()
            payload = attachment.get("payload")
            nested_default = attachment.get("playbook_input_default")
            nested_defaults = attachment.get("playbook_input_defaults")

            if typed_marker == "playbook_input_default":
                if isinstance(payload, dict):
                    defaults.append(payload)
                elif isinstance(nested_default, dict):
                    defaults.append(nested_default)
                continue

            if typed_marker == "playbook_input_defaults":
                if isinstance(payload, list):
                    defaults.extend(
                        candidate for candidate in payload if isinstance(candidate, dict)
                    )
                elif isinstance(nested_defaults, list):
                    defaults.extend(
                        candidate
                        for candidate in nested_defaults
                        if isinstance(candidate, dict)
                    )
                continue

            if isinstance(nested_default, dict):
                defaults.append(nested_default)
            if isinstance(nested_defaults, list):
                defaults.extend(
                    candidate for candidate in nested_defaults if isinstance(candidate, dict)
                )
        return defaults

    def _normalize_request_contract_playbook_input_default(
        self,
        raw_default: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        if not isinstance(raw_default, dict):
            return None
        input_params = raw_default.get("input_params")
        if not isinstance(input_params, dict) or not input_params:
            return None

        playbook_code = str(raw_default.get("playbook_code") or "").strip()
        deliverable_ids = self._clean_string_list(
            raw_default.get("deliverable_ids")
            or raw_default.get("handled_deliverable_ids")
        )
        if not playbook_code and not deliverable_ids:
            return None

        normalized: Dict[str, Any] = {
            "input_params": deepcopy(input_params),
        }
        if playbook_code:
            normalized["playbook_code"] = playbook_code
        if deliverable_ids:
            normalized["deliverable_ids"] = deliverable_ids

        source = str(raw_default.get("request_contract_source") or "").strip()
        if source:
            normalized["request_contract_source"] = source
        return normalized

    def _hydrate_action_items_for_policy_gate(
        self, action_items: List[Dict[str, Any]]
    ) -> None:
        """Fill deterministic bootstrap inputs before policy validation."""
        contract = self._get_request_contract_metadata()
        playbook_input_defaults = (
            self._extract_request_contract_playbook_input_defaults(contract)
        )
        deliverables = {
            d.get("id"): d
            for d in contract.get("deliverables", [])
            if isinstance(d, dict) and d.get("id")
        }
        source_message = contract.get("source_message") if contract else ""
        goals = contract.get("goals") if contract else []
        success_criteria = getattr(self.session, "success_criteria", None) or []
        agenda = getattr(self.session, "agenda", None) or []
        lens_id = getattr(self.session, "lens_id", None)
        if self.session.metadata is None:
            self.session.metadata = {}
        if playbook_input_defaults:
            self.session.metadata["request_contract_playbook_input_defaults"] = [
                {
                    "playbook_code": rule.get("playbook_code"),
                    "deliverable_ids": rule.get("deliverable_ids", []),
                    "source": rule.get("request_contract_source", "explicit"),
                    "input_param_keys": sorted(rule.get("input_params", {}).keys()),
                }
                for rule in playbook_input_defaults
            ]
        elif "request_contract_playbook_input_defaults" in self.session.metadata:
            self.session.metadata.pop("request_contract_playbook_input_defaults", None)

        for item in action_items:
            params = item.get("input_params")
            if not isinstance(params, dict):
                params = {}
                item["input_params"] = params

            deliverable_id = self._extract_deliverable_id(item)
            deliverable = deliverables.get(deliverable_id or "")
            deliverable_name = (
                deliverable.get("name")
                if isinstance(deliverable, dict)
                else params.get("deliverable_name")
            )

            if lens_id and not params.get("lens_id"):
                params["lens_id"] = lens_id

            if deliverable_id and not params.get("deliverable_id"):
                params["deliverable_id"] = deliverable_id
            if deliverable_name and not params.get("deliverable_name"):
                params["deliverable_name"] = deliverable_name
            if deliverable_id and not params.get("deliverable_path"):
                params["deliverable_path"] = self._resolve_deliverable_path(
                    deliverable_id=deliverable_id,
                    deliverable_name=deliverable_name,
                )

            self._apply_request_contract_playbook_input_defaults_to_item(
                rules=playbook_input_defaults,
                item=item,
                params=params,
                deliverable_id=deliverable_id,
            )
            self._apply_playbook_spec_input_defaults_to_item(
                item=item,
                params=params,
                deliverable_id=deliverable_id,
                deliverable_name=deliverable_name,
                source_message=source_message,
                goals=goals,
                agenda=agenda,
                success_criteria=success_criteria,
                lens_id=lens_id,
            )

    def _apply_request_contract_playbook_input_defaults_to_item(
        self,
        *,
        rules: List[Dict[str, Any]],
        item: Dict[str, Any],
        params: Dict[str, Any],
        deliverable_id: Optional[str],
    ) -> None:
        playbook_code = str(item.get("playbook_code") or "").strip()
        for rule in rules:
            rule_playbook_code = str(rule.get("playbook_code") or "").strip()
            if rule_playbook_code and rule_playbook_code != playbook_code:
                continue
            deliverable_ids = self._clean_string_list(rule.get("deliverable_ids"))
            if deliverable_ids and deliverable_id not in deliverable_ids:
                continue
            input_params = rule.get("input_params")
            if not isinstance(input_params, dict):
                continue
            for key, value in input_params.items():
                if params.get(key) in (None, "", [], {}):
                    params[key] = deepcopy(value)

    def _apply_playbook_spec_input_defaults_to_item(
        self,
        *,
        item: Dict[str, Any],
        params: Dict[str, Any],
        deliverable_id: Optional[str],
        deliverable_name: Optional[str],
        source_message: str,
        goals: List[Any],
        agenda: List[Any],
        success_criteria: List[Any],
        lens_id: Optional[str],
    ) -> None:
        playbook_code = str(item.get("playbook_code") or "").strip()
        if not playbook_code:
            return
        rules = load_playbook_meeting_input_defaults(playbook_code)
        if not rules:
            return
        apply_declarative_input_defaults(
            params=params,
            rules=rules,
            resolver_context={
                "item": item,
                "deliverable_id": deliverable_id,
                "deliverable_name": deliverable_name,
                "source_message": source_message,
                "goals": goals,
                "agenda": agenda,
                "success_criteria": success_criteria,
                "lens_id": lens_id,
            },
        )

    def _apply_request_contract_fallback_if_needed(
        self,
        *,
        action_items: List[Dict[str, Any]],
        action_intents: Optional[List[Any]],
    ) -> tuple[List[Any], List[Dict[str, Any]]]:
        """Replace blocked deliverables with executable writer agent tasks."""
        contract = self._get_request_contract_metadata()
        deliverables = contract.get("deliverables", []) if contract else []
        if not isinstance(deliverables, list) or not deliverables:
            return action_intents or [], action_items

        blocked_deliverables: List[str] = []
        blocked_reasons: List[str] = []
        for item in action_items:
            reason_code = str(item.get("policy_reason_code") or "").strip()
            if reason_code not in {"REQUIRED_INPUT_MISSING", "UNKNOWN_PLAYBOOK"}:
                continue
            deliverable_id = self._extract_deliverable_id(item)
            if deliverable_id:
                blocked_deliverables.append(deliverable_id)
                blocked_reasons.append(reason_code)

        if not blocked_deliverables:
            return action_intents or [], action_items

        from backend.app.models.action_intent import ActionIntent

        preserved_atomic_items = [
            item
            for item in action_items
            if item.get("landing_status") != "policy_blocked"
            and bool(item.get("preserve_atomic_playbook"))
        ]
        covered_deliverables = set()
        for item in preserved_atomic_items:
            handled_ids = item.get("handled_deliverable_ids")
            if isinstance(handled_ids, list):
                for raw_deliverable_id in handled_ids:
                    deliverable_id = str(raw_deliverable_id or "").strip()
                    if deliverable_id:
                        covered_deliverables.add(deliverable_id)
            deliverable_id = self._extract_deliverable_id(item)
            if deliverable_id:
                covered_deliverables.add(deliverable_id)

        source_message = contract.get("source_message") or ""
        goals = contract.get("goals") if isinstance(contract.get("goals"), list) else []
        constraints = contract.get("constraints")
        acceptance_tests = contract.get("acceptance_tests")
        deliverable_names = [
            str(d.get("name")).strip()
            for d in deliverables
            if isinstance(d, dict) and d.get("name")
        ]
        workspace = getattr(self, "workspace", None)
        resolved_runtime = None
        for candidate in (
            getattr(workspace, "resolved_executor_runtime", None),
            getattr(workspace, "executor_runtime", None),
            getattr(self, "executor_runtime", None),
        ):
            if isinstance(candidate, str) and candidate.strip():
                resolved_runtime = candidate.strip()
                break
        fallback_engine = (
            f"agent:{resolved_runtime}"
            if isinstance(resolved_runtime, str) and resolved_runtime.strip()
            else "agent:auto"
        )
        fallback_items: List[Dict[str, Any]] = []
        for raw_deliverable in deliverables:
            if not isinstance(raw_deliverable, dict):
                continue
            deliverable_id = str(raw_deliverable.get("id") or "").strip()
            deliverable_name = str(raw_deliverable.get("name") or "").strip()
            if not deliverable_id or not deliverable_name:
                continue
            if deliverable_id in covered_deliverables:
                continue
            deliverable_path = self._resolve_deliverable_path(
                deliverable_id=deliverable_id,
                deliverable_name=deliverable_name,
            )
            user_request = (
                f"Create the deliverable '{deliverable_name}' as a polished markdown "
                f"document and save the final output to '{deliverable_path}'. "
                "Use the exact target filename instead of generic defaults."
            )
            context_lines = []
            if source_message:
                context_lines.append(f"Original request: {source_message}")
            if deliverable_names:
                context_lines.append(
                    "Deliverable set: " + "; ".join(deliverable_names)
                )
            context_lines.append(
                f"Current deliverable: {deliverable_name} ({deliverable_id})"
            )
            context_lines.append(f"Target file path: {deliverable_path}")
            context_lines.append(
                "Write the final markdown to the target file path exactly. "
                "Do not stop at generic files like draft_content.md."
            )
            if goals:
                context_lines.append(
                    "Goals: " + "; ".join(str(goal).strip() for goal in goals if goal)
                )
            if constraints is not None:
                context_lines.append(
                    "Constraints: "
                    + json.dumps(constraints, ensure_ascii=False, sort_keys=True)
                )
            if acceptance_tests is not None:
                context_lines.append(
                    "Acceptance tests: "
                    + json.dumps(acceptance_tests, ensure_ascii=False, sort_keys=True)
                )
            fallback_items.append(
                {
                    "title": deliverable_name,
                    "description": (
                        f"Create the requested deliverable '{deliverable_name}'. "
                        "Proceed with request-contract fallback for the original request: "
                        f"{source_message}\n"
                        f"Deliverables: {'; '.join(deliverable_names)}\n"
                        "Preserve constraints and produce readable, file-backed outputs "
                        "for each deliverable."
                    ),
                    "intent_id": f"WS_{deliverable_id}",
                    "source_intent_id": f"WS_{deliverable_id}",
                    "source_phase_id": f"WS_{deliverable_id}",
                    "priority": "high",
                    "target_workspace_id": getattr(self.session, "workspace_id", None),
                    "engine": fallback_engine,
                    "input_params": {
                        "workspace_id": getattr(self.session, "workspace_id", None),
                        "deliverable_id": deliverable_id,
                        "deliverable_name": deliverable_name,
                        "deliverable_path": deliverable_path,
                        "user_request": user_request,
                        "context": "\n".join(
                            line for line in context_lines if line
                        ),
                    },
                }
            )

        if not fallback_items:
            if preserved_atomic_items:
                preserved_intents = [
                    ActionIntent.from_action_item_dict(item)
                    for item in preserved_atomic_items
                ]
                return preserved_intents, preserved_atomic_items
            return action_intents or [], action_items

        if self.session.metadata is None:
            self.session.metadata = {}
        self.session.metadata["policy_gate_fallback"] = {
            "reason": "policy_blocked_deliverables",
            "blocked_deliverables": sorted(set(blocked_deliverables)),
            "policy_reason_codes": sorted(set(blocked_reasons)),
            "replacement_intent_ids": [
                item.get("intent_id") for item in fallback_items if item.get("intent_id")
            ],
            "preserved_intent_ids": [
                item.get("intent_id")
                for item in preserved_atomic_items
                if item.get("intent_id")
            ],
        }
        logger.info(
            "Replacing %d action items with request-contract fallback writers for session %s (blocked deliverables=%s reasons=%s)",
            len(action_items),
            getattr(self.session, "id", "?"),
            sorted(set(blocked_deliverables)),
            sorted(set(blocked_reasons)),
        )
        merged_items = preserved_atomic_items + fallback_items
        fallback_intents = [
            ActionIntent.from_action_item_dict(item) for item in merged_items
        ]
        return fallback_intents, merged_items

    def _get_request_contract_metadata(self) -> Dict[str, Any]:
        metadata = getattr(self.session, "metadata", None)
        if not isinstance(metadata, dict):
            return {}
        contract = metadata.get("request_contract")
        return contract if isinstance(contract, dict) else {}

    def _extract_deliverable_id(self, item: Dict[str, Any]) -> Optional[str]:
        params = item.get("input_params")
        if isinstance(params, dict):
            for key in ("deliverable_id", "deliverable"):
                value = params.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        for key in ("deliverable_id", "deliverable"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        for field_name in ("title", "description"):
            raw_value = item.get(field_name)
            if not isinstance(raw_value, str) or not raw_value.strip():
                continue
            match = re.search(r"\b(D[1-9]\d*)\b", raw_value, re.IGNORECASE)
            if match:
                return match.group(1).upper()
        return None

    def _resolve_deliverable_path(
        self,
        *,
        deliverable_id: Optional[str],
        deliverable_name: Optional[str],
    ) -> str:
        name = (deliverable_name or "").strip().lower()
        if deliverable_id == "D1" or any(
            token in name
            for token in ("operating system", "角色", "語氣", "價值主張", "紅線")
        ):
            return "persona_operating_system.md"
        if deliverable_id == "D2" or any(
            token in name
            for token in ("instagram", "ig", "7 天", "7-day", "cta", "節奏")
        ):
            return "instagram_week1_calendar.md"
        if deliverable_id == "D3" or any(
            token in name for token in ("reel", "hook")
        ):
            return "reel_hook_bank.md"

        slug_source = deliverable_name or deliverable_id or "deliverable"
        slug = re.sub(r"[^a-z0-9]+", "_", slug_source.lower()).strip("_")
        return f"{slug or 'deliverable'}.md"

    @staticmethod
    def _is_storyboard_deliverable(
        *,
        deliverable_id: Optional[str],
        deliverable_name: Optional[str],
    ) -> bool:
        name = (deliverable_name or "").strip().lower()
        storyboard_tokens = (
            "storyboard",
            "pd intake",
            "mms execution",
            "mms",
            "預覽執行",
            "分鏡",
        )
        if any(token in name for token in storyboard_tokens):
            return True
        return False

    def _collect_storyboard_deliverable_ids(
        self,
        contract: Optional[Dict[str, Any]],
    ) -> List[str]:
        if not isinstance(contract, dict):
            return []
        deliverables = contract.get("deliverables")
        if not isinstance(deliverables, list):
            return []
        handled_ids: List[str] = []
        for raw_deliverable in deliverables:
            if not isinstance(raw_deliverable, dict):
                continue
            deliverable_id = str(raw_deliverable.get("id") or "").strip()
            if not deliverable_id:
                continue
            deliverable_name = str(raw_deliverable.get("name") or "").strip()
            if self._is_storyboard_deliverable(
                deliverable_id=deliverable_id,
                deliverable_name=deliverable_name,
            ):
                handled_ids.append(deliverable_id)
        return handled_ids

    @staticmethod
    def _clean_string_list(values: Any) -> List[str]:
        if not isinstance(values, list):
            return []
        normalized: List[str] = []
        for value in values:
            text = str(value or "").strip()
            if text:
                normalized.append(text)
        return normalized

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
