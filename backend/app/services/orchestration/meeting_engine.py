"""
Meeting Engine

Runs a bounded multi-round governance meeting and persists replayable events.
"""

import asyncio
import inspect
import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.app.core.domain_context import LocalDomainContext
from backend.app.models.meeting_session import MeetingSession, MeetingStatus
from backend.app.models.workspace import Task, TaskStatus
from backend.app.models.mindscape import EventActor, EventType, MindEvent
from backend.app.services.conversation.execution_launcher import ExecutionLauncher
from backend.app.services.workspace_agent_executor import WorkspaceAgentExecutor
from backend.app.services.orchestration.meeting_agents import (
    MEETING_AGENT_ROSTER,
    MEETING_TOPOLOGY,
)
from backend.app.services.orchestration.multi_agent_orchestrator import (
    MultiAgentOrchestrator,
)
from backend.app.services.stores.meeting_session_store import MeetingSessionStore
from backend.app.services.stores.tasks_store import TasksStore
from backend.features.workspace.chat.utils.llm_provider import (
    get_llm_provider,
    get_llm_provider_manager,
)

logger = logging.getLogger(__name__)


@dataclass
class AgentTurnResult:
    agent_id: str
    agent_role: str
    round_number: int
    content: str
    converged: bool = False


@dataclass
class MeetingResult:
    session_id: str
    minutes_md: str
    decision: str
    action_items: List[Dict[str, Any]] = field(default_factory=list)
    event_ids: List[str] = field(default_factory=list)


class MeetingEngine:
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
        preferred_agent: Optional[str] = None,
    ):
        self.session = session
        self.store = store
        self.workspace = workspace
        self.runtime_profile = runtime_profile
        self.profile_id = profile_id
        self.thread_id = thread_id
        self.project_id = project_id
        self.session_store = MeetingSessionStore()
        self.execution_launcher = execution_launcher
        self.model_name = model_name
        self.preferred_agent = preferred_agent
        self.provider = None
        self._agent_executor: Optional[WorkspaceAgentExecutor] = None
        self.tasks_store: Optional[TasksStore] = None
        try:
            self.tasks_store = TasksStore(db_path=getattr(store, "db_path", None))
        except Exception as exc:
            logger.warning("MeetingEngine failed to initialize TasksStore: %s", exc)
        self._events: List[MindEvent] = []
        self._turn_history: List[Dict[str, Any]] = []

        self.orchestrator = MultiAgentOrchestrator(
            agent_roster=MEETING_AGENT_ROSTER,
            topology=MEETING_TOPOLOGY,
            loop_budget=runtime_profile.loop_budget if runtime_profile else None,
            stop_conditions=runtime_profile.stop_conditions if runtime_profile else None,
        )
        stop_conditions = getattr(runtime_profile, "stop_conditions", None)
        self.max_retries = int(getattr(stop_conditions, "max_retries", 2) or 2)
        recovery_policy = getattr(runtime_profile, "recovery_policy", None)
        self.retry_strategy = str(
            getattr(recovery_policy, "retry_strategy", "exponential_backoff")
        )

    async def run(self, user_message: str) -> MeetingResult:
        """Execute a bounded meeting and return generated minutes + action items."""
        self._start_session()
        max_rounds = max(1, int(getattr(self.session, "max_rounds", 1)))

        planner_proposals: List[str] = []
        critic_notes: List[str] = []

        converged = False
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

        decision = planner_proposals[-1] if planner_proposals else "No decision proposed."
        self._emit_decision_final(decision=decision, round_number=self.session.round_count)

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
        self._emit_minutes_message(minutes_md)

        return MeetingResult(
            session_id=self.session.id,
            minutes_md=minutes_md,
            decision=decision,
            action_items=action_items,
            event_ids=[e.id for e in self._events],
        )

    def _start_session(self) -> None:
        self.session.start()
        self.session.status = MeetingStatus.ACTIVE
        self.session_store.update(self.session)
        self._emit_event(
            EventType.MEETING_START,
            payload={
                "meeting_session_id": self.session.id,
                "meeting_type": self.session.meeting_type,
                "agenda": self.session.agenda,
            },
        )

    def _close_session(self, minutes_md: str, action_items: List[Dict[str, Any]]) -> None:
        self.session.begin_closing()
        self.session.minutes_md = minutes_md
        self.session.action_items = action_items
        self.session.status = MeetingStatus.CLOSED
        self.session.close()
        self.session_store.update(self.session)

        self._emit_event(
            EventType.MEETING_END,
            payload={
                "meeting_session_id": self.session.id,
                "round_count": self.session.round_count,
                "action_item_count": len(action_items),
            },
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

    async def _build_action_items(
        self,
        decision: str,
        user_message: str,
        critic_notes: List[str],
        planner_proposals: List[str],
    ) -> List[Dict[str, Any]]:
        executor_turn = await self._agent_turn(
            "executor",
            round_num=max(1, self.session.round_count),
            user_message=user_message,
            decision=decision,
            planner_proposals=planner_proposals,
            critic_notes=critic_notes,
        )
        self._emit_turn(executor_turn)

        items = self._parse_action_items(executor_turn.content, decision)
        landed_items: List[Dict[str, Any]] = []
        for item in items:
            landed_items.append(await self._land_action_item(item))
        return landed_items

    async def _land_action_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        item.setdefault("meeting_session_id", self.session.id)
        item.setdefault("execution_id", None)
        item.setdefault("task_id", None)

        if self.execution_launcher and item.get("playbook_code"):
            try:
                ctx = LocalDomainContext(
                    actor_id=self.profile_id,
                    workspace_id=self.session.workspace_id,
                )
                result = await self.execution_launcher.launch(
                    playbook_code=item["playbook_code"],
                    inputs={
                        "task": item["description"],
                        "meeting_session_id": self.session.id,
                        "workspace_id": self.session.workspace_id,
                    },
                    ctx=ctx,
                    project_id=self.project_id,
                    trace_id=str(uuid.uuid4()),
                )
                item["execution_id"] = result.get("execution_id")
                if item["execution_id"] and item["execution_id"] not in self.session.decisions:
                    self.session.decisions.append(item["execution_id"])
                item["landing_status"] = (
                    "launched" if item.get("execution_id") else "launch_failed"
                )
            except Exception as exc:
                logger.warning(
                    "MeetingEngine failed to launch playbook '%s': %s",
                    item.get("playbook_code"),
                    exc,
                    exc_info=True,
                )
                item["landing_status"] = "launch_error"
                item["landing_error"] = str(exc)

        if not item.get("execution_id"):
            item["task_id"] = self._create_action_task(item)
            item["landing_status"] = "task_created" if item.get("task_id") else "planned"

        return item

    def _create_action_task(self, item: Dict[str, Any]) -> Optional[str]:
        if not self.tasks_store:
            return None
        try:
            task_id = str(uuid.uuid4())
            task = Task(
                id=task_id,
                workspace_id=self.session.workspace_id,
                message_id=(self._events[-1].id if self._events else str(uuid.uuid4())),
                execution_id=item.get("execution_id"),
                project_id=self.project_id,
                pack_id=item.get("playbook_code") or "meeting_action_item",
                task_type="meeting_action_item",
                status=TaskStatus.PENDING,
                params={
                    "meeting_session_id": self.session.id,
                    "title": item.get("title"),
                    "description": item.get("description"),
                    "priority": item.get("priority"),
                },
                result=None,
                execution_context={
                    "trigger_source": "meeting_engine",
                    "meeting_session_id": self.session.id,
                },
                created_at=datetime.now(timezone.utc),
            )
            self.tasks_store.create_task(task)
            return task_id
        except Exception as exc:
            logger.warning("MeetingEngine failed to create action task: %s", exc, exc_info=True)
            return None

    async def _generate_text(self, messages: List[Dict[str, str]]) -> str:
        attempts = max(0, self.max_retries)

        last_error: Optional[Exception] = None
        for attempt in range(attempts + 1):
            try:
                if self.preferred_agent:
                    return await self._generate_text_via_preferred_agent(messages)
                await self._ensure_provider()
                return await self._generate_text_via_llm(messages)
            except Exception as exc:
                last_error = exc
                if attempt >= attempts:
                    break
                self.orchestrator.record_retry()
                await asyncio.sleep(self._retry_delay_seconds(attempt))

        raise RuntimeError(f"Meeting turn generation failed: {last_error}") from last_error

    async def _generate_text_via_llm(self, messages: List[Dict[str, str]]) -> str:
        call_kwargs = {
            "messages": messages,
            "model": self.model_name,
            "temperature": 0.3,
            "max_tokens": 1200,
        }
        sig = inspect.signature(self.provider.chat_completion)
        allowed = set(sig.parameters.keys())
        kwargs = {k: v for k, v in call_kwargs.items() if k in allowed}
        if "messages" not in kwargs:
            kwargs["messages"] = messages
        content = await self.provider.chat_completion(**kwargs)
        if not content or not str(content).strip():
            raise RuntimeError("Meeting LLM returned empty content")
        return str(content).strip()

    async def _generate_text_via_preferred_agent(
        self, messages: List[Dict[str, str]]
    ) -> str:
        if not self.preferred_agent:
            raise RuntimeError("preferred_agent is not configured for meeting mode")
        if not self.workspace:
            raise RuntimeError("workspace is required for preferred_agent meeting mode")

        if not self._agent_executor:
            self._agent_executor = WorkspaceAgentExecutor(self.workspace)

        available = await self._agent_executor.check_agent_available(self.preferred_agent)
        if not available:
            raise RuntimeError(
                f"Preferred agent '{self.preferred_agent}' is unavailable in meeting mode"
            )

        system_prompt = ""
        user_prompt = ""
        for msg in messages:
            role = str(msg.get("role", "")).lower()
            if role == "system" and not system_prompt:
                system_prompt = str(msg.get("content", ""))
            if role == "user":
                user_prompt = str(msg.get("content", ""))

        task = (
            "[Meeting Agent Turn]\n"
            f"Session: {self.session.id}\n"
            "Follow the system instructions and produce a direct role response.\n\n"
            f"[System Prompt]\n{system_prompt}\n\n"
            f"[Turn Prompt]\n{user_prompt}\n"
        )

        result = await self._agent_executor.execute(
            task=task,
            agent_id=self.preferred_agent,
            context_overrides={
                "meeting_session_id": self.session.id,
                "thread_id": self.thread_id,
                "project_id": self.project_id,
                "conversation_context": system_prompt,
            },
        )
        if not result.success:
            raise RuntimeError(
                f"Preferred agent '{self.preferred_agent}' failed: "
                f"{result.error or 'unknown error'}"
            )
        if not result.output or not result.output.strip():
            raise RuntimeError(
                f"Preferred agent '{self.preferred_agent}' returned empty output"
            )
        return result.output.strip()

    async def _ensure_provider(self) -> None:
        if self.provider:
            return

        if not self.model_name:
            self.model_name = self._resolve_model_name()

        manager = get_llm_provider_manager(
            profile_id=self.profile_id,
            db_path=getattr(self.store, "db_path", None),
        )
        provider, _ = get_llm_provider(
            model_name=self.model_name,
            llm_provider_manager=manager,
            profile_id=self.profile_id,
            db_path=getattr(self.store, "db_path", None),
        )
        self.provider = provider

    def _resolve_model_name(self) -> str:
        try:
            from backend.app.services.system_settings_store import SystemSettingsStore

            setting = SystemSettingsStore().get_setting("chat_model")
            if setting and setting.value:
                return str(setting.value)
        except Exception as exc:
            logger.warning("MeetingEngine failed to resolve chat_model: %s", exc)
        raise RuntimeError(
            "Meeting mode requires model_name or system setting 'chat_model'; "
            "no fallback model is allowed"
        )

    def _retry_delay_seconds(self, attempt: int) -> float:
        if self.retry_strategy == "immediate":
            return 0.0
        if self.retry_strategy == "exponential_backoff":
            return float(min(2**attempt, 8))
        return 0.0

    def _build_turn_prompt(
        self,
        agent_id: str,
        round_num: int,
        user_message: str,
        decision: Optional[str],
        planner_proposals: List[str],
        critic_notes: List[str],
    ) -> str:
        history = self._history_snippet()
        agenda = self.session.agenda or [user_message]
        agenda_text = "\n".join([f"- {a}" for a in agenda])
        latest_proposal = planner_proposals[-1] if planner_proposals else "(none)"
        latest_critic = critic_notes[-1] if critic_notes else "(none)"

        common = (
            f"Meeting session: {self.session.id}\n"
            f"Round: {round_num}/{max(1, self.session.max_rounds)}\n"
            f"Agenda:\n{agenda_text}\n\n"
            f"User request:\n{user_message}\n\n"
            f"Current decision draft:\n{decision or '(not finalized)'}\n\n"
            f"Latest planner proposal:\n{latest_proposal}\n\n"
            f"Latest critic note:\n{latest_critic}\n\n"
            f"Recent turns:\n{history}\n\n"
        )

        if agent_id == "facilitator":
            return (
                common
                + "As facilitator, synthesize progress and decide if another round is needed. "
                "If converged, include the marker [CONVERGED]. Keep concise."
            )
        if agent_id == "planner":
            return (
                common
                + "As planner, propose a concrete, executable plan with clear steps and ownership."
            )
        if agent_id == "critic":
            return (
                common
                + "As critic, challenge assumptions, identify risks, and suggest mitigations."
            )
        return (
            common
            + "As executor, produce only JSON array with up to 3 action items. "
            'Schema: [{"title":"...","description":"...","assigned_to":"executor",'
            '"priority":"low|medium|high","playbook_code":null}]'
        )

    def _history_snippet(self) -> str:
        if not self._turn_history:
            return "(none)"
        recent = self._turn_history[-6:]
        return "\n".join(
            [f"- R{t['round']} {t['role']}: {t['content'][:220]}" for t in recent]
        )

    def _fallback_turn_text(self, agent_id: str, round_num: int, user_message: str) -> str:
        if agent_id == "facilitator":
            return (
                f"Round {round_num} facilitation summary for '{user_message[:80]}'. "
                "Planner and critic inputs consolidated."
            )
        if agent_id == "planner":
            return (
                f"Proposal R{round_num}: execute incrementally, track evidence, and verify outcomes."
            )
        if agent_id == "critic":
            return (
                f"Critique R{round_num}: verify data contract, add rollback checks, and test failure paths."
            )
        return json.dumps(
            [
                {
                    "title": "Implement finalized decision",
                    "description": "Translate final meeting decision into executable work.",
                    "assigned_to": "executor",
                    "priority": "medium",
                    "playbook_code": None,
                }
            ]
        )

    def _is_converged(self, round_num: int, max_rounds: int, facilitator_text: str) -> bool:
        if round_num >= max_rounds:
            return True
        if round_num >= 2 and "[converged]" in facilitator_text.lower():
            return True
        return False

    def _parse_action_items(self, executor_output: str, decision: str) -> List[Dict[str, Any]]:
        payload = self._extract_json_payload(executor_output)
        items: List[Dict[str, Any]] = []

        if isinstance(payload, dict) and isinstance(payload.get("action_items"), list):
            payload = payload.get("action_items")
        if isinstance(payload, list):
            for raw_item in payload[:3]:
                if not isinstance(raw_item, dict):
                    continue
                items.append(
                    {
                        "meeting_session_id": self.session.id,
                        "title": str(raw_item.get("title") or "Action Item").strip(),
                        "description": str(
                            raw_item.get("description") or decision
                        ).strip(),
                        "assigned_to": str(
                            raw_item.get("assigned_to") or "executor"
                        ).strip(),
                        "priority": str(raw_item.get("priority") or "medium").strip(),
                        "playbook_code": (
                            str(raw_item.get("playbook_code")).strip()
                            if raw_item.get("playbook_code")
                            else None
                        ),
                        "execution_id": None,
                    }
                )

        if items:
            return items

        # Fallback from plain text bullets.
        bullet_items = re.findall(r"(?:^|\n)\s*(?:[-*]|\d+\.)\s+(.+)", executor_output)
        if bullet_items:
            return [
                {
                    "meeting_session_id": self.session.id,
                    "title": bullet_items[0][:80],
                    "description": bullet_items[0],
                    "assigned_to": "executor",
                    "priority": "medium",
                    "playbook_code": None,
                    "execution_id": None,
                }
            ]

        return [
            {
                "meeting_session_id": self.session.id,
                "title": "Implement finalized decision",
                "description": decision,
                "assigned_to": "executor",
                "priority": "medium",
                "playbook_code": None,
                "execution_id": None,
            }
        ]

    def _extract_json_payload(self, text: str) -> Any:
        candidates: List[str] = []
        fenced = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
        if fenced:
            candidates.append(fenced.group(1))

        bracket = re.search(r"(\[[\s\S]*\])", text)
        if bracket:
            candidates.append(bracket.group(1))

        brace = re.search(r"(\{[\s\S]*\})", text)
        if brace:
            candidates.append(brace.group(1))

        for candidate in candidates:
            try:
                return json.loads(candidate)
            except Exception:
                continue
        return None

    def _emit_turn(self, turn: AgentTurnResult) -> None:
        self._emit_event(
            EventType.AGENT_TURN,
            payload={
                "meeting_session_id": self.session.id,
                "agent_id": turn.agent_id,
                "agent_role": turn.agent_role,
                "round_number": turn.round_number,
                "content": turn.content,
            },
        )

    def _emit_decision_proposal(self, turn: AgentTurnResult) -> None:
        self._emit_event(
            EventType.DECISION_PROPOSAL,
            payload={
                "meeting_session_id": self.session.id,
                "proposed_by": turn.agent_id,
                "round_number": turn.round_number,
                "proposal": turn.content,
                "supporting_evidence": [],
                "risks": [],
                "alternatives": [],
            },
        )

    def _emit_decision_final(self, decision: str, round_number: int) -> None:
        self._emit_event(
            EventType.DECISION_FINAL,
            payload={
                "meeting_session_id": self.session.id,
                "decided_by": "facilitator",
                "round_number": round_number,
                "decision": decision,
                "rationale": "Planner proposal accepted after critic review.",
                "dissenting_views": [],
            },
        )

    def _emit_action_item(self, item: Dict[str, Any]) -> None:
        self._emit_event(
            EventType.ACTION_ITEM,
            payload=item,
        )

    def _emit_round_event(self, round_number: int, status: str) -> None:
        self._emit_event(
            EventType.MEETING_ROUND,
            payload={
                "meeting_session_id": self.session.id,
                "round_number": round_number,
                "status": status,
                "speaker_order": ["facilitator", "planner", "critic"],
                "summary": f"Round {round_number} {status}",
            },
        )

    def _emit_minutes_message(self, minutes_md: str) -> None:
        self._emit_event(
            EventType.MESSAGE,
            payload={
                "message": minutes_md,
                "meeting_session_id": self.session.id,
                "is_meeting_minutes": True,
            },
            actor=EventActor.ASSISTANT,
            channel="meeting",
        )

    def _emit_event(
        self,
        event_type: EventType,
        payload: Dict[str, Any],
        actor: EventActor = EventActor.SYSTEM,
        channel: str = "meeting",
    ) -> None:
        event = MindEvent(
            id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc),
            actor=actor,
            channel=channel,
            profile_id=self.profile_id,
            project_id=self.project_id,
            workspace_id=self.session.workspace_id,
            thread_id=self.thread_id or self.session.thread_id,
            event_type=event_type,
            payload=payload,
            entity_ids=[],
            metadata={"meeting_session_id": self.session.id},
        )
        self.store.create_event(event)
        self._events.append(event)

    def _render_minutes(
        self,
        user_message: str,
        decision: str,
        critic_notes: List[str],
        action_items: List[Dict[str, Any]],
        converged: bool,
    ) -> str:
        status = "converged" if converged else "partial"
        action_lines = "\n".join([
            (
                f"| {idx} | {item.get('title', 'Action Item')} | "
                f"{item.get('assigned_to', 'executor')} | {item.get('priority', 'medium')} |"
            )
            for idx, item in enumerate(action_items, start=1)
        ])
        if not action_lines:
            action_lines = "| 1 | No action item generated | executor | medium |"
        risk_text = "\n".join([f"- {note}" for note in critic_notes]) or "- None"

        return (
            f"# Meeting Minutes — {self.session.id[:8]}\n"
            f"**Status**: {status}  \n"
            f"**Rounds**: {self.session.round_count}\n\n"
            f"## Agenda\n- {user_message}\n\n"
            f"## Decisions\n- {decision}\n\n"
            f"## Risks & Concerns\n{risk_text}\n\n"
            "## Action Items\n"
            "| # | Task | Assigned To | Priority |\n"
            "|---|------|-------------|----------|\n"
            f"{action_lines}\n"
        )
