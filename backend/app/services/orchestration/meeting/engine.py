"""
Meeting Engine — slim orchestrator.

Composes mixin modules for event emission, governance, prompts,
action items, and text generation into a single MeetingEngine class.

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
    MEETING_AGENT_ROSTER,
    MEETING_TOPOLOGY,
    build_meeting_roster,
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
    dispatch_result: Optional[Dict[str, Any]] = None


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
        uploaded_files: Optional[List[Dict[str, Any]]] = None,
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

    @staticmethod
    def _resolve_locale(workspace) -> str:
        """Resolve locale with fallback chain.

        Aligned with workspace_dependencies.py:100-112 get_orchestrator():
        1. workspace.default_locale
        2. system_settings "default_language"
        3. "zh-TW" hardcoded fallback
        """
        # 1. Workspace direct field
        ws_locale = getattr(workspace, "default_locale", None)
        if ws_locale:
            return ws_locale

        # 2. System settings (key = "default_language", per workspace_dependencies.py:107)
        try:
            from backend.app.services.system_settings_store import SystemSettingsStore

            store = SystemSettingsStore()
            setting = store.get_setting("default_language")
            if setting and setting.value:
                return str(setting.value)
        except Exception:
            pass

        # 3. Hardcoded fallback (per blueprint_loader.py:196 + workspace_dependencies.py:111)
        return "zh-TW"

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
        # Cache user_message for _build_tool_query_from_context()
        # MUST be set before _rag_tool_cache pre-fetch below.
        self._last_user_message = user_message

        # Pre-fetch RAG tool results once per session (non-fatal, non-blocking for
        # prompt construction — _build_tool_inventory_block() reads cache synchronously).
        self._rag_tool_cache: list = []
        try:
            from backend.app.services.tool_rag import retrieve_relevant_tools

            self._rag_tool_cache = await retrieve_relevant_tools(
                self._build_tool_query_from_context(),
                top_k=20,
                workspace_id=self.session.workspace_id,
            )
            logger.debug(
                "Meeting RAG pre-fetch: %d tools cached for session %s",
                len(self._rag_tool_cache),
                self.session.id if hasattr(self, "session") and self.session else "?",
            )
        except Exception as exc:
            logger.warning(
                "Meeting RAG pre-fetch failed (manifest fallback active): %s", exc
            )

        # 5A-1: Preload workspace-installed playbooks for prompt injection

        self._available_playbooks_cache = await self._async_load_installed_playbooks()

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
            self.session.end()  # Set ended_at so session is not stale

            # Generate partial minutes from completed rounds so content
            # is not silently discarded when later rounds fail.
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

        action_items = await self._build_action_items(
            decision=decision,
            user_message=user_message,
            critic_notes=critic_notes,
            planner_proposals=planner_proposals,
        )
        # ------------------------------------------------------------------ #
        # Pre-dispatch null-tool gate (Fix: emit AFTER gate to keep events    #
        # consistent with session.action_items)                               #
        # Gate fires when the workspace has EXPLICIT TOOL bindings OR the     #
        # RAG cache returned relevant tools — either signal means the LLM    #
        # was given a tool list and should have used it.                      #
        # ------------------------------------------------------------------ #
        all_null = action_items and not any(
            item.get("tool_name") or item.get("playbook_code") for item in action_items
        )
        has_tool_context = self._has_workspace_tool_bindings() or bool(
            getattr(self, "_rag_tool_cache", [])
        )
        if all_null and has_tool_context:
            pb_cache = getattr(self, "_available_playbooks_cache", "")
            logger.info(
                "Pre-dispatch null-tool gate triggered for session %s: "
                "workspace has explicit TOOL bindings but all action_items "
                "have tool_name=null and playbook_code=null.  Retrying executor turn.",
                self.session.id,
            )
            try:
                retry_items = await self._build_action_items(
                    decision=decision,
                    user_message=user_message,
                    critic_notes=critic_notes,
                    planner_proposals=planner_proposals,
                )
                has_actuator_retry = any(
                    item.get("tool_name") or item.get("playbook_code")
                    for item in retry_items
                )
                if has_actuator_retry:
                    action_items = retry_items
                    logger.info(
                        "Null-tool gate retry produced %d actuator-linked items",
                        sum(
                            1
                            for i in action_items
                            if i.get("tool_name") or i.get("playbook_code")
                        ),
                    )
                    self._emit_event(
                        "tool_name_self_heal",
                        payload={
                            "session_id": self.session.id,
                            "trigger": "null_tool_gate_retry",
                            "actuator_count": sum(
                                1
                                for i in action_items
                                if i.get("tool_name") or i.get("playbook_code")
                            ),
                        },
                    )
                else:
                    logger.warning(
                        "Null-tool gate retry did not produce actuator items; "
                        "keeping original action_items."
                    )
            except Exception as exc:
                logger.warning("Null-tool gate retry failed (non-fatal): %s", exc)

        # Emit final action_items AFTER gate (so SSE events match session.action_items)
        for item in action_items:
            self._emit_action_item(item)

        # Dispatch action items to target workspaces (fan-out + fan-in)
        dispatch_result = await self._dispatch_phases_to_workspaces(action_items)

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

        return MeetingResult(
            session_id=self.session.id,
            minutes_md=minutes_md,
            decision=decision,
            action_items=action_items,
            event_ids=[e.id for e in self._events],
            task_ir=compiled_ir,
            dispatch_result=dispatch_result,
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

    async def _async_load_installed_playbooks(self) -> str:
        """Load workspace-installed playbooks for prompt injection.

        Primary: query workspace_resource_bindings for PLAYBOOK type.
        Fallback: PlaybookService.list_playbooks() when no bindings exist.

        Returns:
            Formatted string listing available playbooks.
        """
        # TODO: binding_store is sync I/O; consider run_in_executor or async store
        try:
            from backend.app.services.stores.workspace_resource_binding_store import (
                WorkspaceResourceBindingStore,
            )
            from backend.app.models.workspace_resource_binding import ResourceType
            from backend.app.services.playbook_service import PlaybookService

            binding_store = WorkspaceResourceBindingStore()
            bindings = binding_store.list_bindings_by_workspace(
                self.session.workspace_id, resource_type=ResourceType.PLAYBOOK
            )

            if not bindings:
                # Fallback: PlaybookService merges capability/system/user sources
                svc = PlaybookService(store=self.store)
                playbooks = await svc.list_playbooks(
                    workspace_id=self.session.workspace_id
                )
                # list_playbooks returns List[PlaybookMetadata] — .name is direct
                lines = [f"- {p.playbook_code}: {p.name}" for p in playbooks]
                return "\n".join(lines) if lines else "(no playbooks installed)"

            svc = PlaybookService(store=self.store)
            lines = []
            for b in bindings:
                pb = await svc.get_playbook(
                    b.resource_id, workspace_id=self.session.workspace_id
                )
                # get_playbook returns Playbook — name via .metadata.name
                name = pb.metadata.name if pb else b.resource_id
                lines.append(f"- {b.resource_id}: {name}")
            return "\n".join(lines)
        except Exception as exc:
            logger.warning("Failed to load installed playbooks: %s", exc, exc_info=True)
            return "(playbook discovery unavailable)"

    def _resolve_blocked_by_order(
        self, action_items: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Validate blocked_by references and return topologically sorted list.

        Rules:
        1. blocked_by refs are 0-based indices within the same dispatch batch.
        2. Cycles → all items in the cycle marked dispatch_error.
        3. Missing refs (non-existent index) → referencing item marked dispatch_error.

        Returns:
            Topologically sorted list of action items (dependencies first).
        """
        n = len(action_items)
        # Quick exit: no blocked_by at all
        has_blocked_by = False
        for idx, item in enumerate(action_items):
            deps = item.get("blocked_by")
            if not deps or not isinstance(deps, list):
                continue
            has_blocked_by = True
            for ref in deps:
                if not isinstance(ref, int) or ref < 0 or ref >= n or ref == idx:
                    item["landing_status"] = "dispatch_error"
                    item["landing_error"] = f"missing dependency: {ref}"
                    break

        if not has_blocked_by:
            return list(action_items)

        # Kahn's algorithm: topological sort + cycle detection
        from collections import deque

        in_degree = [0] * n
        adj: Dict[int, List[int]] = {i: [] for i in range(n)}
        for idx, item in enumerate(action_items):
            if item.get("landing_status"):
                continue
            deps = item.get("blocked_by")
            if not deps or not isinstance(deps, list):
                continue
            for ref in deps:
                if isinstance(ref, int) and 0 <= ref < n and ref != idx:
                    adj[ref].append(idx)
                    in_degree[idx] += 1

        queue = deque()
        for i in range(n):
            if not action_items[i].get("landing_status") and in_degree[i] == 0:
                queue.append(i)

        sorted_indices: List[int] = []
        while queue:
            node = queue.popleft()
            sorted_indices.append(node)
            for neighbor in adj.get(node, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # Items not in sorted output and not already marked → cycle
        visited = set(sorted_indices)
        for idx, item in enumerate(action_items):
            if item.get("landing_status"):
                continue
            deps = item.get("blocked_by")
            if deps and isinstance(deps, list) and idx not in visited:
                item["landing_status"] = "dispatch_error"
                item["landing_error"] = "dependency cycle detected"

        # Build final ordered list: topo-sorted items first, then items
        # without blocked_by (preserving original order), then errored items
        in_sorted = set(sorted_indices)
        result: List[Dict[str, Any]] = []
        # Add items without blocked_by in original order (interleaved with
        # topo-sorted items at their natural positions)
        topo_order = {idx: pos for pos, idx in enumerate(sorted_indices)}

        # Assign a sort key: topo-sorted items by their topo position,
        # items without deps by original index, errored items last
        def sort_key(pair):
            idx, item = pair
            if item.get("landing_status") in ("dispatch_error", "policy_blocked"):
                return (2, idx)  # Errored items last
            if idx in topo_order:
                return (0, topo_order[idx])  # Topo-sorted position
            return (0, idx)  # No deps: original order

        for idx, item in sorted(enumerate(action_items), key=sort_key):
            result.append(item)

        return result

    async def _attempt_tool_name_self_heal(
        self,
        action_items: List[Dict[str, Any]],
        binding_store: Any,
    ) -> int:
        """Attempt one bounded LLM repair pass for TOOL_NOT_ALLOWED items.

        Repair path is only used after deterministic normalization in
        dispatch_policy_gate has already run. This method only clears
        policy blocks for items that can be mapped to an allowlisted tool.
        """
        try:
            from backend.app.services.orchestration.meeting.dispatch_policy_gate import (
                _canonicalize_tool_name,
                _load_tool_allowlist,
            )

            blocked_rows: List[Dict[str, Any]] = []
            for idx, item in enumerate(action_items):
                if item.get("landing_status") != "policy_blocked":
                    continue
                if item.get("policy_reason_code") != "TOOL_NOT_ALLOWED":
                    continue
                current_tool = item.get("tool_name")
                if not isinstance(current_tool, str) or not current_tool.strip():
                    continue
                target_ws = item.get("target_workspace_id") or self.session.workspace_id
                allowlist = _load_tool_allowlist(target_ws, binding_store)
                if not allowlist:
                    continue
                blocked_rows.append(
                    {
                        "index": idx,
                        "item": item,
                        "target_workspace_id": target_ws,
                        "allowed_tools": set(allowlist),
                    }
                )

            if not blocked_rows:
                return 0

            prompt_rows = [
                {
                    "index": row["index"],
                    "title": row["item"].get("title"),
                    "tool_name": row["item"].get("tool_name"),
                    "target_workspace_id": row["target_workspace_id"],
                    "allowed_tools": sorted(list(row["allowed_tools"]))[:80],
                }
                for row in blocked_rows
            ]
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You repair tool_name fields for action items. "
                        "Only use tool names from each item's allowed_tools."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "Return JSON array only. Schema: "
                        '[{"index":<int>,"tool_name":"<allowed_tool_or_null>"}]. '
                        "Use null when no valid repair exists.\n\n"
                        f"Items:\n{json.dumps(prompt_rows, ensure_ascii=False)}"
                    ),
                },
            ]

            try:
                raw = (await self._generate_text(messages)).strip()
            except Exception as exc:
                logger.warning("Tool self-heal generation failed: %s", exc)
                return 0

            payload = None
            extract_fn = getattr(self, "_extract_json_payload", None)
            if callable(extract_fn):
                try:
                    payload = extract_fn(raw)
                except Exception:
                    payload = None
            if payload is None:
                try:
                    payload = json.loads(raw)
                except Exception:
                    payload = None
            if not isinstance(payload, list):
                logger.warning("Tool self-heal returned non-list payload")
                return 0

            row_by_index = {row["index"]: row for row in blocked_rows}
            repaired = 0
            for rec in payload:
                if not isinstance(rec, dict):
                    continue
                idx_raw = rec.get("index")
                try:
                    idx = int(idx_raw)
                except (TypeError, ValueError):
                    continue
                if idx not in row_by_index:
                    continue

                candidate_tool = rec.get("tool_name")
                if not isinstance(candidate_tool, str) or not candidate_tool.strip():
                    continue
                row = row_by_index[idx]
                canonical, _ = _canonicalize_tool_name(
                    candidate_tool, row["allowed_tools"]
                )
                if canonical is None:
                    continue

                item = row["item"]
                original = item.get("tool_name")
                item["tool_name"] = canonical
                item.setdefault("tool_name_original", original)
                item["tool_name_self_healed"] = True
                item.pop("landing_status", None)
                item.pop("landing_error", None)
                item.pop("policy_reason_code", None)
                repaired += 1

            return repaired
        except Exception as exc:
            logger.warning("Tool self-heal pipeline failed (non-fatal): %s", exc)
            return 0

    async def _dispatch_phases_to_workspaces(
        self, action_items: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Dispatch action items grouped by workspace with fan-in aggregation.

        Groups action items by their target_workspace_id, dispatches each
        group concurrently, and aggregates results per workspace.

        Returns dict with per-workspace results and aggregate status.
        """
        import asyncio
        from collections import defaultdict

        # 5E: Run policy gate before any dispatch
        try:
            from backend.app.services.orchestration.meeting.dispatch_policy_gate import (
                check_dispatch_policy,
            )
            from backend.app.services.stores.workspace_resource_binding_store import (
                WorkspaceResourceBindingStore,
            )

            _binding_store = WorkspaceResourceBindingStore()
            check_dispatch_policy(
                action_items,
                workspace_id=self.session.workspace_id,
                available_playbooks_cache=getattr(
                    self, "_available_playbooks_cache", ""
                ),
                binding_store=_binding_store,
            )

            # Self-heal priority: one bounded LLM repair for TOOL_NOT_ALLOWED.
            repaired_count = 0
            repair_fn = getattr(self, "_attempt_tool_name_self_heal", None)
            if callable(repair_fn):
                repaired_count = await repair_fn(
                    action_items=action_items,
                    binding_store=_binding_store,
                )
            if repaired_count > 0:
                # Re-run policy gate after repair with same allowlist policy.
                check_dispatch_policy(
                    action_items,
                    workspace_id=self.session.workspace_id,
                    available_playbooks_cache=getattr(
                        self, "_available_playbooks_cache", ""
                    ),
                    binding_store=_binding_store,
                )
                self._emit_event(
                    EventType.DECISION_FINAL,
                    payload={
                        "tool_name_self_heal": True,
                        "meeting_session_id": self.session.id,
                        "repaired_count": repaired_count,
                    },
                )

            # Emit audit event for any policy-blocked items
            blocked_items = [
                item
                for item in action_items
                if item.get("landing_status") == "policy_blocked"
            ]
            if blocked_items:
                self._emit_event(
                    EventType.DECISION_FINAL,
                    payload={
                        "policy_gate_blocked": True,
                        "meeting_session_id": self.session.id,
                        "blocked_count": len(blocked_items),
                        "reasons": [
                            {
                                "title": item.get("title"),
                                "policy_reason_code": item.get("policy_reason_code"),
                            }
                            for item in blocked_items
                        ],
                    },
                )
        except Exception as exc:
            logger.warning("Policy gate check failed (non-fatal): %s", exc)

        # 5B-4: Validate + topologically sort blocked_by references
        action_items = self._resolve_blocked_by_order(action_items)

        # Group action items by target workspace
        ws_groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        default_ws = self.session.workspace_id
        for item in action_items:
            target = item.get("target_workspace_id") or default_ws
            item["target_workspace_id"] = target
            ws_groups[target].append(item)

        if len(ws_groups) <= 1:
            # Single workspace — use existing serial path
            # Determine actual target workspace (may differ from session ws)
            actual_ws = next(iter(ws_groups)) if ws_groups else default_ws
            results = []
            for item in action_items:
                if item.get("landing_status") in ("policy_blocked", "dispatch_error"):
                    results.append(item)
                    continue
                landed = await self._land_action_item(item)
                results.append(landed)
            succeeded = sum(
                1
                for r in results
                if r.get("landing_status") in ("launched", "task_created")
            )
            failed = sum(
                1
                for r in results
                if r.get("landing_status")
                in (
                    "launch_failed",
                    "launch_error",
                    "policy_blocked",
                    "dispatch_error",
                )
            )
            if failed == 0:
                agg_status = "ok"
            elif succeeded == 0:
                agg_status = "all_failed"
            else:
                agg_status = "partial_failure"

            return {
                "dispatch_mode": "single",
                "workspace_results": {actual_ws: results},
                "aggregate_status": agg_status,
                "total": len(results),
                "succeeded": succeeded,
                "failed": failed,
            }

        # Multi-workspace: run DataLocality boundary check before dispatch
        boundary_violations = []
        try:
            from backend.app.services.data_locality_service import (
                get_data_locality_service,
            )
            from backend.app.services.stores.workspace_resource_binding_store import (
                WorkspaceResourceBindingStore,
            )
            from backend.app.models.workspace_resource_binding import ResourceType

            binding_store = WorkspaceResourceBindingStore()
            ws_asset_map: Dict[str, List[str]] = {}
            for ws_id in ws_groups:
                bindings = binding_store.list_bindings_by_workspace(
                    ws_id, resource_type=ResourceType.ASSET
                )
                ws_asset_map[ws_id] = [b.resource_id for b in bindings]

            locality_svc = get_data_locality_service()
            boundary_result = locality_svc.check_dispatch_boundary(
                action_items, ws_asset_map
            )

            if not boundary_result["valid"]:
                boundary_violations = boundary_result["violations"]
                logger.warning(
                    "DataLocality boundary violations: %s",
                    boundary_result["message"],
                )
                # Mark violating items so they are skipped during dispatch
                violation_indices = {v["item_index"] for v in boundary_violations}
                for idx in violation_indices:
                    if idx < len(action_items):
                        action_items[idx]["landing_status"] = "boundary_violation"
                        action_items[idx]["landing_error"] = boundary_result["message"]

                self._emit_event(
                    EventType.DECISION_FINAL,
                    payload={
                        "dispatch_boundary_violation": True,
                        "meeting_session_id": self.session.id,
                        "violations": boundary_violations,
                    },
                )
        except Exception as exc:
            logger.warning("DataLocality boundary check failed: %s", exc)

        # Rebuild groups excluding violated items
        ws_groups_clean: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for item in action_items:
            if item.get("landing_status") in (
                "boundary_violation",
                "policy_blocked",
                "dispatch_error",
            ):
                continue
            ws_groups_clean[item["target_workspace_id"]].append(item)

        # Multi-workspace fan-out: dispatch each workspace group concurrently
        async def _dispatch_ws_group(
            ws_id: str, items: List[Dict[str, Any]]
        ) -> Dict[str, Any]:
            ws_results = []
            for item in items:
                try:
                    landed = await self._land_action_item(item)
                    ws_results.append(landed)
                except Exception as exc:
                    logger.warning(
                        "Dispatch failed for item '%s' → ws '%s': %s",
                        item.get("title"),
                        ws_id,
                        exc,
                    )
                    item["landing_status"] = "dispatch_error"
                    item["landing_error"] = str(exc)
                    ws_results.append(item)
            return {"workspace_id": ws_id, "items": ws_results}

        tasks = [
            _dispatch_ws_group(ws_id, items) for ws_id, items in ws_groups_clean.items()
        ]
        ws_outcomes = await asyncio.gather(*tasks, return_exceptions=True)

        # Fan-in: aggregate results (include all pre-blocked items)
        workspace_results: Dict[str, List[Dict[str, Any]]] = {}
        all_items: List[Dict[str, Any]] = []
        # Include all pre-blocked items (boundary_violation, policy_blocked, dispatch_error)
        pre_blocked_items = [
            item
            for item in action_items
            if item.get("landing_status")
            in ("boundary_violation", "policy_blocked", "dispatch_error")
        ]
        all_items.extend(pre_blocked_items)
        for outcome in ws_outcomes:
            if isinstance(outcome, Exception):
                logger.error("Workspace dispatch group failed: %s", outcome)
                continue
            ws_id = outcome["workspace_id"]
            workspace_results[ws_id] = outcome["items"]
            all_items.extend(outcome["items"])

        succeeded = sum(
            1
            for r in all_items
            if r.get("landing_status") in ("launched", "task_created")
        )
        failed = sum(
            1
            for r in all_items
            if r.get("landing_status")
            in (
                "launch_failed",
                "launch_error",
                "dispatch_error",
                "boundary_violation",
                "policy_blocked",
            )
        )

        if failed == 0:
            agg_status = "ok"
        elif succeeded == 0:
            agg_status = "all_failed"
        else:
            agg_status = "partial_failure"

        # Emit audit event for cross-workspace dispatch
        self._emit_event(
            EventType.DECISION_FINAL,
            payload={
                "cross_workspace_dispatch": True,
                "meeting_session_id": self.session.id,
                "workspace_count": len(ws_groups),
                "total_items": len(all_items),
                "succeeded": succeeded,
                "failed": failed,
                "aggregate_status": agg_status,
                "workspace_ids": list(ws_groups.keys()),
            },
        )

        return {
            "dispatch_mode": "multi",
            "workspace_results": workspace_results,
            "aggregate_status": agg_status,
            "total": len(all_items),
            "succeeded": succeeded,
            "failed": failed,
        }

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

            # Step 5: L3 StateVector computation (non-fatal)
            try:
                from backend.app.services.orchestration.meeting.state_vector_service import (
                    StateVectorService,
                )
                from backend.app.services.stores.state_vector_store import (
                    StateVectorStore,
                )
                from backend.app.models.meeting_mode import MeetingMode

                sv_svc = StateVectorService()
                goal_set = active_goals[0] if active_goals else None

                # Risk fallback: prefer EGB drift score, fall back to session metadata
                risk_fallback = float(self.session.metadata.get("risk_score", 0.0))
                intent_ids = self._get_active_intent_ids()
                if intent_ids:
                    try:
                        from backend.app.database import get_db_postgres
                        from sqlalchemy import text

                        db_gen = get_db_postgres()
                        db = next(db_gen)
                        try:
                            row = db.execute(
                                text(
                                    "SELECT overall_drift_score "
                                    "FROM egb_drift_report "
                                    "WHERE intent_id = :iid "
                                    "ORDER BY created_at DESC LIMIT 1"
                                ),
                                {"iid": intent_ids[0]},
                            ).fetchone()
                            if row and row[0] and float(row[0]) > 0:
                                risk_fallback = max(risk_fallback, float(row[0]))
                        finally:
                            next(db_gen, None)
                    except Exception:
                        pass  # EGB 不可用時回退到 session metadata

                # Session count for evidence grace period
                session_count = 0
                if self.session_store and self.project_id:
                    try:
                        previous = self.session_store.list_by_workspace(
                            workspace_id=self.session.workspace_id,
                            project_id=self.project_id,
                            limit=100,
                        )
                        session_count = len(previous)
                    except Exception:
                        pass

                sv = sv_svc.compute(
                    meeting_session_id=self.session.id,
                    workspace_id=self.session.workspace_id,
                    extract=extract,
                    goal_set=goal_set,
                    patches=[patch] if patch else [],
                    current_lens_hash=getattr(self, "_lens_hash", None) or "",
                    previous_lens_hash="",
                    current_mode=MeetingMode(
                        self.session.metadata.get("meeting_mode", "explore")
                    ),
                    session_count=session_count,
                    risk_fallback=risk_fallback,
                    project_id=self.project_id,
                )

                # Persist state vector
                sv_store = StateVectorStore()
                sv_store.create(sv)

                # Emit STATE_VECTOR_COMPUTED event
                self._emit_event(
                    EventType.STATE_VECTOR_COMPUTED,
                    payload={
                        "meeting_session_id": self.session.id,
                        "state_vector_id": sv.id,
                        "axes": {
                            "progress": sv.progress,
                            "evidence": sv.evidence,
                            "risk": sv.risk,
                            "drift": sv.drift,
                        },
                        "lyapunov_v": sv.lyapunov_v,
                        "mode": sv.mode,
                    },
                )

                # Emit MODE_TRANSITION if mode changed
                prev_mode = self.session.metadata.get("meeting_mode", "explore")
                if sv.mode != prev_mode:
                    self._emit_event(
                        EventType.MODE_TRANSITION,
                        payload={
                            "meeting_session_id": self.session.id,
                            "from_mode": prev_mode,
                            "to_mode": sv.mode,
                            "reason": f"StateVector triggered: V={sv.lyapunov_v:.3f}",
                        },
                    )

                logger.info(
                    "L3: StateVector %s computed for session %s (V=%.3f, mode=%s)",
                    sv.id,
                    self.session.id,
                    sv.lyapunov_v,
                    sv.mode,
                )
            except Exception as exc:
                logger.warning(
                    "L3 StateVector computation failed (non-fatal) for session %s: %s",
                    self.session.id,
                    exc,
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
        role_def = self._roster[agent_id]
        role = role_def.agent_name

        prompt = self._build_turn_prompt(
            agent_id=agent_id,
            round_num=round_num,
            user_message=user_message,
            decision=decision,
            planner_proposals=planner_proposals or [],
            critic_notes=critic_notes or [],
        )
        system_content = role_def.system_prompt
        messages = [
            {"role": "system", "content": system_content},
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
