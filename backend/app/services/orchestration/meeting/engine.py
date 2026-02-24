"""
Meeting Engine — slim orchestrator.

Composes mixin modules for event emission, governance, prompts,
action items, and text generation into a single MeetingEngine class.

The run() method drives a bounded multi-round governance meeting.
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.app.models.meeting_session import MeetingSession, MeetingStatus
from backend.app.models.mindscape import EventType
from backend.app.services.conversation.execution_launcher import ExecutionLauncher
from backend.app.services.orchestration.meeting_agents import (
    MEETING_AGENT_ROSTER,
    MEETING_TOPOLOGY,
)
from backend.app.services.orchestration.multi_agent_orchestrator import (
    MultiAgentOrchestrator,
)
from backend.app.services.stores.meeting_session_store import MeetingSessionStore
from backend.app.services.stores.tasks_store import TasksStore

from backend.app.services.orchestration.meeting._action_items import (
    MeetingActionItemsMixin,
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
from backend.app.services.orchestration.meeting._prompts import MeetingPromptsMixin

logger = logging.getLogger(__name__)


@dataclass
class AgentTurnResult:
    """Result of a single agent turn in a meeting round."""

    agent_id: str
    agent_role: str
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


class MeetingEngine(
    MeetingEventsMixin,
    MeetingGovernanceMixin,
    MeetingPromptsMixin,
    MeetingActionItemsMixin,
    MeetingGenerationMixin,
    MeetingIRCompilerMixin,
):
    """Drives a bounded multi-agent meeting with real LLM turns and action landing."""

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

        # Resolve locale from workspace settings
        self._locale = getattr(workspace, "default_locale", None) or "en"

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

        self.orchestrator = MultiAgentOrchestrator(
            agent_roster=MEETING_AGENT_ROSTER,
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

    async def run(
        self,
        user_message: str,
        handoff_in: Optional[Any] = None,
    ) -> MeetingResult:
        """Execute a bounded meeting and return generated minutes + action items.

        Args:
            user_message: User message that triggered the meeting.
            handoff_in: Optional HandoffIn for governance context.
        """
        self._start_session()
        max_rounds = max(1, int(getattr(self.session, "max_rounds", 1)))

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

                facilitator_turn = await self._agent_turn(
                    "facilitator",
                    round_num,
                    user_message,
                    planner_proposals=planner_proposals,
                    critic_notes=critic_notes,
                )
                self._emit_turn(facilitator_turn)

                planner_turn = await self._agent_turn(
                    "planner",
                    round_num,
                    user_message,
                    planner_proposals=planner_proposals,
                    critic_notes=critic_notes,
                )
                planner_proposals.append(planner_turn.content)
                self._emit_turn(planner_turn)
                self._emit_decision_proposal(planner_turn)

                critic_turn = await self._agent_turn(
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

        action_items = await self._build_action_items(
            decision=decision,
            user_message=user_message,
            critic_notes=critic_notes,
            planner_proposals=planner_proposals,
        )
        for item in action_items:
            self._emit_action_item(item)

        minutes_md = self._render_minutes(
            user_message=user_message,
            decision=decision,
            critic_notes=critic_notes,
            action_items=action_items,
            converged=converged,
        )

        self._close_session(minutes_md=minutes_md, action_items=action_items)

        # B8: Run L2 Bridge extraction pipeline (non-fatal)
        self._run_l2_bridge_pipeline()

        self._emit_minutes_message(minutes_md)

        # Compile structured TaskIR from meeting output
        compiled_ir = None
        try:
            compiled_ir = self._compile_to_task_ir(
                decision=decision,
                action_items=action_items,
                handoff_in=handoff_in,
            )
        except Exception as exc:
            logger.warning("Failed to compile TaskIR from meeting: %s", exc)

        return MeetingResult(
            session_id=self.session.id,
            minutes_md=minutes_md,
            decision=decision,
            action_items=action_items,
            event_ids=[e.id for e in self._events],
            task_ir=compiled_ir,
        )

    def _start_session(self) -> None:
        """Transition session to ACTIVE and capture initial state snapshot."""
        self.session.start()
        self.session.status = MeetingStatus.ACTIVE
        self.session.state_before = self._capture_state_snapshot()
        self.session_store.update(self.session)
        self._emit_event(
            EventType.MEETING_START,
            payload={
                "meeting_session_id": self.session.id,
                "meeting_type": self.session.meeting_type,
                "agenda": self.session.agenda,
                "lens_id": self.session.lens_id,
            },
        )

    def _close_session(
        self, minutes_md: str, action_items: List[Dict[str, Any]]
    ) -> None:
        """Close the session with final state snapshot and minutes."""
        self.session.begin_closing()
        self.session.minutes_md = minutes_md
        self.session.action_items = action_items
        self.session.state_after = self._capture_state_snapshot()
        self.session.status = MeetingStatus.CLOSED
        self.session.close()
        self.session_store.update(self.session)

        self._emit_event(
            EventType.MEETING_END,
            payload={
                "meeting_session_id": self.session.id,
                "round_count": self.session.round_count,
                "action_item_count": len(action_items),
                "state_diff": self.session.state_diff,
            },
        )

    def _run_l2_bridge_pipeline(self) -> None:
        """Run L2 Bridge extraction pipeline after session close.

        Pipeline: events → MeetingExtract → GoalLinking → LensPatch
        All failures are non-fatal (logged, never breaks the meeting).
        """
        try:
            from backend.app.services.orchestration.meeting.extract_service import (
                MeetingExtractService,
            )
            from backend.app.services.orchestration.meeting.lens_patch_service import (
                LensPatchService,
            )
            from backend.app.services.orchestration.meeting.goal_linking_service import (
                GoalLinkingService,
            )
            from backend.app.services.stores.meeting_extract_store import (
                MeetingExtractStore,
            )
            from backend.app.services.stores.lens_patch_store import LensPatchStore
            from backend.app.services.stores.goal_set_store import GoalSetStore

            # Step 1: Extract structured items from meeting events
            extract_svc = MeetingExtractService()
            extract = extract_svc.extract_from_events(
                meeting_session_id=self.session.id,
                events=self._events,
            )

            # Step 2: Link extract items to active GoalSet (if any)
            goal_store = GoalSetStore()
            active_goals = goal_store.list_by_project(
                workspace_id=self.session.workspace_id,
                project_id=self.project_id or "",
                limit=1,
            )
            if active_goals:
                linking_svc = GoalLinkingService()
                extract = linking_svc.link_extract_to_goals(extract, active_goals[0])
                extract.goal_set_id = active_goals[0].id

            # Step 3: Persist the extract
            extract_store = MeetingExtractStore()
            extract_store.create(extract)
            logger.info(
                "L2 Bridge: persisted MeetingExtract %s (%d items) for session %s",
                extract.id,
                len(extract.items),
                self.session.id,
            )

            # Step 4: Generate lens patch (compare before/after)
            lens_after = None
            try:
                from backend.app.services.stores.graph_store import GraphStore
                from backend.app.services.lens.effective_lens_resolver import (
                    EffectiveLensResolver,
                )
                from backend.app.services.lens.session_override_store import (
                    InMemorySessionStore,
                )

                resolver = EffectiveLensResolver(GraphStore(), InMemorySessionStore())
                lens_after = resolver.resolve(
                    profile_id=self.profile_id,
                    workspace_id=self.session.workspace_id,
                )
            except Exception as exc:
                logger.debug("L2 Bridge: could not resolve post-session lens: %s", exc)

            patch_svc = LensPatchService()
            patch = patch_svc.generate_patch_from_session(
                session=self.session,
                lens_before=self._effective_lens,
                lens_after=lens_after,
            )
            if patch:
                patch_store = LensPatchStore()
                patch_store.create(patch)
                logger.info(
                    "L2 Bridge: persisted LensPatch %s for session %s",
                    patch.id,
                    self.session.id,
                )

        except Exception as exc:
            logger.warning(
                "L2 Bridge pipeline failed (non-fatal) for session %s: %s",
                self.session.id,
                exc,
            )

    async def _agent_turn(
        self,
        agent_id: str,
        round_num: int,
        user_message: str,
        decision: Optional[str] = None,
        planner_proposals: Optional[List[str]] = None,
        critic_notes: Optional[List[str]] = None,
    ) -> AgentTurnResult:
        """Execute a single agent turn with prompt construction and LLM generation."""
        self.orchestrator.record_turn()
        role_def = MEETING_AGENT_ROSTER[agent_id]
        role = role_def.agent_name

        prompt = self._build_turn_prompt(
            agent_id=agent_id,
            round_num=round_num,
            user_message=user_message,
            decision=decision,
            planner_proposals=planner_proposals or [],
            critic_notes=critic_notes or [],
        )
        messages = [
            {"role": "system", "content": role_def.system_prompt},
            {"role": "user", "content": prompt},
        ]

        try:
            content = (await self._generate_text(messages)).strip()
            if not content:
                raise ValueError("empty LLM content")
        except Exception as exc:
            self.orchestrator.record_error()
            logger.error(
                "MeetingEngine turn failed for %s (round=%s): %s",
                agent_id,
                round_num,
                exc,
            )
            raise RuntimeError(
                f"Meeting turn failed for agent '{agent_id}' at round {round_num}: {exc}"
            ) from exc

        turn = AgentTurnResult(
            agent_id=agent_id,
            agent_role=role,
            round_number=round_num,
            content=content,
            converged=round_num >= 2,
        )
        self._turn_history.append(
            {
                "round": round_num,
                "agent_id": agent_id,
                "role": role,
                "content": content,
            }
        )
        return turn
