"""
Meeting engine session lifecycle mixin.

Handles session start/close transitions, locale resolution,
and workspace playbook discovery.
"""

import logging
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

from backend.app.models.meeting_session import MeetingStatus
from backend.app.models.mindscape import EventType

logger = logging.getLogger(__name__)


class MeetingSessionMixin:
    """Mixin providing session lifecycle methods for MeetingEngine."""

    async def _prefetch_governed_context_packet(self) -> None:
        """Prefetch governed content/world context for meeting prompt injection."""
        try:
            from backend.app.services.governance.governance_context_read_model import (
                GovernanceContextReadModel,
            )
            from backend.app.services.mindscape_store import MindscapeStore

            read_model = GovernanceContextReadModel(store=MindscapeStore())
            governance_packet = await read_model.build_for_workspace(
                getattr(self, "workspace", None),
                profile_id=getattr(self, "profile_id", None),
                project_id=getattr(self, "project_id", None)
                or getattr(getattr(self, "session", None), "project_id", None),
                session_id=getattr(getattr(self, "session", None), "id", None),
            )
            memory_context_summary = read_model.format_memory_packet_for_context(
                governance_packet
            )
            self._governance_packet = governance_packet or None
            self._memory_context_summary = memory_context_summary or ""
            self._world_memory_packet = (
                governance_packet.get("world_memory_packet")
                if isinstance(governance_packet, dict)
                else None
            )
            self._world_card_projection = (
                governance_packet.get("world_card_projection")
                if isinstance(governance_packet, dict)
                else None
            )
            self._world_card_text = (
                governance_packet.get("world_card_text", "")
                if isinstance(governance_packet, dict)
                else ""
            )
        except Exception as exc:
            logger.warning(
                "Failed to prefetch governed meeting context for session %s: %s",
                getattr(getattr(self, "session", None), "id", "unknown"),
                exc,
            )
            self._governance_packet = None
            self._memory_context_summary = ""
            self._world_memory_packet = None
            self._world_card_projection = None
            self._world_card_text = ""

    def _persist_prefetched_governed_context(self) -> None:
        """Persist prefetched governed content/world context into session metadata."""
        if self.session.metadata is None:
            self.session.metadata = {}

        governance_packet = getattr(self, "_governance_packet", None)
        if isinstance(governance_packet, dict):
            if governance_packet.get("governance_context"):
                self.session.metadata["governance_context"] = governance_packet.get(
                    "governance_context"
                )
            if governance_packet.get("memory_packet"):
                self.session.metadata["memory_packet"] = governance_packet.get(
                    "memory_packet"
                )
            if governance_packet.get("world_memory_packet"):
                self.session.metadata["world_memory_packet"] = governance_packet.get(
                    "world_memory_packet"
                )
            if governance_packet.get("world_card_projection"):
                self.session.metadata["world_card_projection"] = governance_packet.get(
                    "world_card_projection"
                )
            if governance_packet.get("world_card_text"):
                self.session.metadata["world_card_text"] = governance_packet.get(
                    "world_card_text"
                )
            if governance_packet.get("geo_context"):
                self.session.metadata["geo_context"] = governance_packet.get(
                    "geo_context"
                )
            if governance_packet.get("motion_context"):
                self.session.metadata["motion_context"] = governance_packet.get(
                    "motion_context"
                )
            if governance_packet.get("spatial_schedule_context"):
                self.session.metadata["spatial_schedule_context"] = governance_packet.get(
                    "spatial_schedule_context"
                )

        memory_context_summary = getattr(self, "_memory_context_summary", "")
        if memory_context_summary:
            self.session.metadata["memory_context_summary"] = memory_context_summary

    @staticmethod
    def _packet_has_core_layer(core: Optional[Dict[str, Any]]) -> bool:
        if not core:
            return False
        return any(
            core.get(key)
            for key in (
                "brand_identity",
                "voice_and_tone",
                "style_constraints",
                "important_milestones",
                "learnings",
            )
        )

    @staticmethod
    def _packet_has_project_layer(project: Optional[Dict[str, Any]]) -> bool:
        if not project:
            return False
        return bool(
            project.get("decision_history")
            or project.get("key_conversations")
            or project.get("artifact_index")
        )

    @staticmethod
    def _packet_has_member_layer(member: Optional[Dict[str, Any]]) -> bool:
        if not member:
            return False
        return bool(
            member.get("skills")
            or member.get("preferences")
            or member.get("learnings")
        )

    def _build_workspace_core_memory_snapshot(
        self, workspace: Any
    ) -> Optional[SimpleNamespace]:
        metadata = dict(getattr(workspace, "metadata", {}) or {})
        core_memory = dict(metadata.get("core_memory", {}) or {})
        if not core_memory:
            return None
        return SimpleNamespace(
            brand_identity=core_memory.get("brand_identity"),
            voice_and_tone=core_memory.get("voice_and_tone"),
            style_constraints=core_memory.get("style_constraints"),
            important_milestones=core_memory.get("important_milestones"),
            learnings=core_memory.get("learnings"),
        )

    def _build_project_memory_snapshot(
        self, project_id: Optional[str]
    ) -> Optional[SimpleNamespace]:
        if not project_id:
            return None
        try:
            from backend.app.services.stores.postgres.projects_store import (
                PostgresProjectsStore,
            )
        except Exception as exc:
            logger.debug("Project store import failed for selected packet trace: %s", exc)
            return None

        try:
            project = PostgresProjectsStore().get_project(project_id)
        except Exception as exc:
            logger.debug(
                "Project memory lookup failed for selected packet trace (%s): %s",
                project_id,
                exc,
            )
            return None
        if project is None:
            return None

        memory = dict(getattr(project, "metadata", {}) or {}).get("project_memory", {}) or {}
        if not memory:
            return None

        decision_history = []
        for item in list(memory.get("decision_history", []) or [])[:5]:
            if isinstance(item, dict):
                decision_history.append(
                    SimpleNamespace(
                        decision=item.get("decision", ""),
                        rationale=item.get("rationale", ""),
                    )
                )

        return SimpleNamespace(
            project_id=project_id,
            decision_history=decision_history,
            key_conversations=list(memory.get("key_conversations", []) or [])[:5],
            artifact_index=list(memory.get("artifact_index", []) or [])[:5],
        )

    def _build_member_memory_snapshot(
        self,
        *,
        profile_id: str,
        workspace_id: str,
    ) -> Optional[SimpleNamespace]:
        if not profile_id:
            return None
        try:
            from backend.app.services.mindscape_store import MindscapeStore

            profile = MindscapeStore().get_profile(profile_id)
        except Exception as exc:
            logger.debug(
                "Member memory lookup failed for selected packet trace (%s): %s",
                profile_id,
                exc,
            )
            return None
        if profile is None:
            return None

        workspace_memory = (
            dict(getattr(profile, "metadata", {}) or {})
            .get("workspace_memories", {})
            .get(workspace_id, {})
        )
        if not workspace_memory:
            return None

        return SimpleNamespace(
            user_id=profile_id,
            skills=list(workspace_memory.get("skills", []) or [])[:8],
            preferences=workspace_memory.get("preferences"),
            learnings=list(workspace_memory.get("learnings", []) or [])[:5],
        )

    def _extract_selected_memory_packet_node_ids(
        self,
        *,
        memory_packet: Dict[str, Any],
        workspace_id: str,
    ) -> List[str]:
        layers = dict(memory_packet.get("layers") or {})
        node_ids: List[str] = []

        def add(node_id: Optional[str]) -> None:
            if node_id and node_id not in node_ids:
                node_ids.append(node_id)

        if self._packet_has_core_layer(layers.get("core")):
            add(f"workspace_core:{workspace_id}")

        knowledge_layers = dict(layers.get("knowledge") or {})
        for bucket in ("verified", "candidates"):
            for item in list(knowledge_layers.get(bucket, []) or []):
                if isinstance(item, dict):
                    add(f"knowledge:{item.get('id')}")

        goal_layers = dict(layers.get("goals") or {})
        for bucket in ("active", "pending"):
            for item in list(goal_layers.get(bucket, []) or []):
                if isinstance(item, dict):
                    add(f"goal:{item.get('id')}")

        project_layer = layers.get("project")
        if self._packet_has_project_layer(project_layer):
            add(f"project_memory:{(project_layer or {}).get('project_id')}")

        member_layer = layers.get("member")
        if self._packet_has_member_layer(member_layer):
            user_id = (member_layer or {}).get("user_id")
            add(f"member_memory:{workspace_id}:{user_id}")

        for item in list(layers.get("episodic", []) or []):
            if isinstance(item, dict):
                add(f"memory_item:{item.get('id')}")

        return node_ids

    def _capture_selected_memory_packet_trace(self) -> Optional[Dict[str, Any]]:
        workspace = getattr(self, "workspace", None)
        session = getattr(self, "session", None)
        if workspace is None or session is None:
            return None

        workspace_id = getattr(session, "workspace_id", None) or getattr(workspace, "id", None)
        if not workspace_id:
            return None

        try:
            from backend.app.services.governance.governance_context_read_model import (
                GovernanceContextReadModel,
            )
            from backend.app.services.mindscape_store import MindscapeStore

            profile_id = (
                getattr(self, "profile_id", None)
                or getattr(workspace, "owner_user_id", None)
                or ""
            )
            project_id = getattr(session, "project_id", None) or getattr(
                workspace, "primary_project_id", None
            )

            read_model = GovernanceContextReadModel(store=MindscapeStore())
            memory_packet = read_model.selector.select_packet(
                canonical_items=read_model._safe_get_recent_canonical_items(workspace_id),
                personal_knowledge_entries=read_model._safe_list_personal_knowledge(
                    profile_id
                ),
                goal_entries=read_model._safe_list_goal_entries(profile_id),
                workspace_core_memory=self._build_workspace_core_memory_snapshot(workspace),
                project_memory=self._build_project_memory_snapshot(project_id),
                member_memory=self._build_member_memory_snapshot(
                    profile_id=profile_id,
                    workspace_id=workspace_id,
                ),
                lens_context=read_model._build_lens_context(
                    workspace,
                    workspace_mode=getattr(workspace, "mode", None),
                    session_id=getattr(session, "id", None),
                ),
                policy_context=read_model._build_policy_context(workspace),
                workspace_mode=getattr(workspace, "mode", None),
            )
            route_plan = read_model.packet_compiler.build_route_plan(
                {"memory_packet": memory_packet}
            )
            node_ids = self._extract_selected_memory_packet_node_ids(
                memory_packet=memory_packet,
                workspace_id=workspace_id,
            )
            return {
                "selected_memory_packet": {
                    **memory_packet,
                    "route_plan": route_plan,
                },
                "selected_memory_packet_node_ids": node_ids,
            }
        except Exception as exc:
            logger.warning(
                "Failed to capture selected memory packet for session %s: %s",
                getattr(session, "id", "unknown"),
                exc,
            )
            return None

    def _build_memory_impact_trace(
        self,
        *,
        selected_packet_node_ids: List[str],
        canonical_memory: Optional[Dict[str, Any]],
        world_memory_writeback: Optional[Dict[str, Any]],
        meeting_decision_ids: List[str],
        action_items: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        session_id = getattr(getattr(self, "session", None), "id", "") or ""
        action_item_node_ids = [
            f"action_item:{session_id}:{index}"
            for index, _item in enumerate(action_items)
        ]
        explicit: Dict[str, Any] = {
            "session_node_id": f"meeting_session:{session_id}" if session_id else None,
            "selected_packet_node_ids": list(selected_packet_node_ids),
            "meeting_decision_node_ids": [
                f"meeting_decision:{decision_id}"
                for decision_id in meeting_decision_ids
                if decision_id
            ],
            "action_item_node_ids": action_item_node_ids,
            "canonical_writeback_node_id": (
                f"memory_item:{canonical_memory.get('memory_item_id')}"
                if canonical_memory and canonical_memory.get("memory_item_id")
                else None
            ),
            "digest_node_id": (
                f"session_digest:{canonical_memory.get('digest_id')}"
                if canonical_memory and canonical_memory.get("digest_id")
                else None
            ),
            "writeback_run_id": (
                canonical_memory.get("writeback_run_id") if canonical_memory else None
            ),
            "world_snapshot_node_id": (
                f"world_snapshot:{world_memory_writeback.get('snapshot_id')}"
                if world_memory_writeback
                and world_memory_writeback.get("snapshot_id")
                else None
            ),
        }
        return {
            "explicit": {
                key: value
                for key, value in explicit.items()
                if value not in (None, [], {})
            },
            "inferred": None,
        }

    @staticmethod
    def _normalize_lineage_value(value: Any) -> Optional[str]:
        normalized = str(value or "").strip()
        return normalized or None

    @classmethod
    def _resolve_action_item_for_phase_id(
        cls,
        *,
        action_items: List[Dict[str, Any]],
        items_by_intent_id: Dict[str, Dict[str, Any]],
        phase_id: Any,
        source_intent_id: Any = None,
    ) -> Optional[Dict[str, Any]]:
        normalized_source_intent_id = cls._normalize_lineage_value(source_intent_id)
        if normalized_source_intent_id:
            item = items_by_intent_id.get(normalized_source_intent_id)
            if item is not None:
                return item

        normalized_phase_id = cls._normalize_lineage_value(phase_id)
        if not normalized_phase_id:
            return None

        item = items_by_intent_id.get(normalized_phase_id)
        if item is not None:
            return item

        if normalized_phase_id.startswith("phase_"):
            index_str = normalized_phase_id[len("phase_") :]
            if index_str.isdigit():
                index = int(index_str)
                if 0 <= index < len(action_items):
                    candidate = action_items[index]
                    if isinstance(candidate, dict):
                        return candidate

        return None

    @classmethod
    def _append_action_item_lineage(
        cls,
        *,
        item: Dict[str, Any],
        phase_id: Any,
        source_intent_id: Any,
        execution_id: Any,
        task_id: Any,
    ) -> None:
        normalized_phase_id = cls._normalize_lineage_value(phase_id)
        normalized_source_intent_id = cls._normalize_lineage_value(source_intent_id)
        normalized_execution_id = cls._normalize_lineage_value(execution_id)
        normalized_task_id = cls._normalize_lineage_value(task_id)

        if normalized_source_intent_id and not cls._normalize_lineage_value(
            item.get("source_intent_id")
        ):
            item["source_intent_id"] = normalized_source_intent_id
        if normalized_phase_id and not cls._normalize_lineage_value(
            item.get("source_phase_id")
        ):
            item["source_phase_id"] = normalized_phase_id
        if normalized_execution_id and not cls._normalize_lineage_value(
            item.get("execution_id")
        ):
            item["execution_id"] = normalized_execution_id
        if normalized_task_id and not cls._normalize_lineage_value(item.get("task_id")):
            item["task_id"] = normalized_task_id

        if normalized_execution_id:
            execution_ids = item.setdefault("execution_ids", [])
            if isinstance(execution_ids, list) and normalized_execution_id not in execution_ids:
                execution_ids.append(normalized_execution_id)
        if normalized_task_id:
            task_ids = item.setdefault("task_ids", [])
            if isinstance(task_ids, list) and normalized_task_id not in task_ids:
                task_ids.append(normalized_task_id)

    @classmethod
    def _stitch_action_item_execution_lineage(
        cls,
        *,
        action_items: List[Dict[str, Any]],
        dispatch_result: Optional[Dict[str, Any]],
    ) -> None:
        if not action_items or not isinstance(dispatch_result, dict):
            return

        attempts = dispatch_result.get("attempts")
        if not isinstance(attempts, dict) or not attempts:
            return

        items_by_intent_id: Dict[str, Dict[str, Any]] = {}
        for item in action_items:
            if not isinstance(item, dict):
                continue
            intent_id = cls._normalize_lineage_value(item.get("intent_id"))
            if intent_id and not cls._normalize_lineage_value(item.get("source_intent_id")):
                item["source_intent_id"] = intent_id
            if intent_id and intent_id not in items_by_intent_id:
                items_by_intent_id[intent_id] = item

        for phase_id, attempt in attempts.items():
            if not isinstance(attempt, dict):
                continue

            adapter_meta = attempt.get("adapter_meta")
            result = attempt.get("result")
            if not isinstance(adapter_meta, dict):
                adapter_meta = {}
            if not isinstance(result, dict):
                result = {}

            item = cls._resolve_action_item_for_phase_id(
                action_items=action_items,
                items_by_intent_id=items_by_intent_id,
                phase_id=phase_id,
                source_intent_id=adapter_meta.get("source_intent_id")
                or result.get("source_intent_id"),
            )
            if item is None:
                continue

            execution_id = (
                cls._normalize_lineage_value(adapter_meta.get("execution_id"))
                or cls._normalize_lineage_value(result.get("execution_id"))
                or cls._normalize_lineage_value(result.get("task_id"))
            )
            task_id = cls._normalize_lineage_value(result.get("task_id"))
            cls._append_action_item_lineage(
                item=item,
                phase_id=phase_id,
                source_intent_id=adapter_meta.get("source_intent_id")
                or result.get("source_intent_id"),
                execution_id=execution_id,
                task_id=task_id,
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

    def _start_session(self) -> None:
        """Transition session to ACTIVE and capture initial state snapshot."""
        self.session.start()
        self.session.status = MeetingStatus.ACTIVE
        self.session.state_before = self._capture_state_snapshot()
        self._persist_prefetched_governed_context()

        # Feature 4: Snapshot MeetingExecutionContext into session metadata
        ctx = getattr(self, "ctx", None)
        if ctx and hasattr(ctx, "model_dump"):
            self.session.metadata["execution_context_snapshot"] = {
                "executor_runtime_id": ctx.executor_runtime_id,
                "auth_type": ctx.auth_type,
                "auth_status": ctx.auth_status,
                "fallback_model": ctx.fallback_model,
                "max_iterations": ctx.max_iterations,
                "route_kind": ctx.route_kind,
                "execution_profile": ctx.execution_profile,
            }

        workflow_evidence_diagnostics = getattr(
            self,
            "_workflow_evidence_diagnostics",
            None,
        )
        if isinstance(workflow_evidence_diagnostics, dict):
            self.session.metadata["workflow_evidence_diagnostics"] = (
                workflow_evidence_diagnostics
            )

        selected_memory_packet_trace = self._capture_selected_memory_packet_trace()
        if isinstance(selected_memory_packet_trace, dict):
            self.session.metadata["selected_memory_packet"] = (
                selected_memory_packet_trace.get("selected_memory_packet") or {}
            )
            self.session.metadata["selected_memory_packet_node_ids"] = list(
                selected_memory_packet_trace.get("selected_memory_packet_node_ids") or []
            )

        self.session_store.update(self.session)
        self._emit_event(
            EventType.MEETING_START,
            payload={
                "meeting_session_id": self.session.id,
                "meeting_type": self.session.meeting_type,
                "agenda": self.session.agenda,
                "lens_id": self.session.lens_id,
                "workflow_evidence_profile": (
                    workflow_evidence_diagnostics.get("profile")
                    if isinstance(workflow_evidence_diagnostics, dict)
                    else None
                ),
                "workflow_evidence_scope": (
                    workflow_evidence_diagnostics.get("scope")
                    if isinstance(workflow_evidence_diagnostics, dict)
                    else None
                ),
                "workflow_evidence_selected_line_count": (
                    workflow_evidence_diagnostics.get("selected_line_count")
                    if isinstance(workflow_evidence_diagnostics, dict)
                    else None
                ),
                "workflow_evidence_total_line_budget": (
                    workflow_evidence_diagnostics.get("total_line_budget")
                    if isinstance(workflow_evidence_diagnostics, dict)
                    else None
                ),
                "workflow_evidence_total_candidate_count": (
                    workflow_evidence_diagnostics.get("total_candidate_count")
                    if isinstance(workflow_evidence_diagnostics, dict)
                    else None
                ),
                "workflow_evidence_total_dropped_count": (
                    workflow_evidence_diagnostics.get("total_dropped_count")
                    if isinstance(workflow_evidence_diagnostics, dict)
                    else None
                ),
                "workflow_evidence_rendered_section_count": (
                    workflow_evidence_diagnostics.get("rendered_section_count")
                    if isinstance(workflow_evidence_diagnostics, dict)
                    else None
                ),
                "workflow_evidence_budget_utilization_ratio": (
                    workflow_evidence_diagnostics.get("budget_utilization_ratio")
                    if isinstance(workflow_evidence_diagnostics, dict)
                    else None
                ),
            },
        )

    def _close_session(
        self,
        minutes_md: str,
        action_items: List[Dict[str, Any]],
        dispatch_result: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Close the session with final state snapshot and minutes."""
        self._stitch_action_item_execution_lineage(
            action_items=action_items,
            dispatch_result=dispatch_result,
        )
        self.session.begin_closing()
        self.session.minutes_md = minutes_md
        self.session.action_items = action_items
        self.session.state_after = self._capture_state_snapshot()
        self.session.status = MeetingStatus.CLOSED
        self.session.close()
        self.session_store.update(self.session)

        # Feature 3: Extract structured decisions from action_items
        decisions = []
        try:
            from backend.app.models.meeting_decision import MeetingDecision

            decisions = MeetingDecision.extract_from_session(self.session)
            if decisions:
                self.session_store.save_decisions(decisions)
                logger.info(
                    "Persisted %d decisions for session %s",
                    len(decisions),
                    self.session.id,
                )
        except Exception as exc:
            logger.warning(
                "Failed to persist meeting decisions for %s: %s",
                self.session.id,
                exc,
            )

        selected_packet_node_ids = list(
            self.session.metadata.get("selected_memory_packet_node_ids") or []
        )
        if not selected_packet_node_ids:
            selected_memory_packet_trace = self._capture_selected_memory_packet_trace()
            if isinstance(selected_memory_packet_trace, dict):
                self.session.metadata["selected_memory_packet"] = (
                    selected_memory_packet_trace.get("selected_memory_packet") or {}
                )
                selected_packet_node_ids = list(
                    selected_memory_packet_trace.get("selected_memory_packet_node_ids")
                    or []
                )
                self.session.metadata["selected_memory_packet_node_ids"] = (
                    selected_packet_node_ids
                )

        # ADR-001 v2 Phase 1: Emit session_digest (L1→L2 bridge)
        canonical_memory = None
        world_memory_writeback = None
        try:
            from backend.app.services.memory.writeback.meeting_memory_writeback_orchestrator import (
                MeetingMemoryWritebackOrchestrator,
            )

            orchestrator = MeetingMemoryWritebackOrchestrator()
            writeback_result = orchestrator.run_for_closed_session(
                session=self.session,
                workspace=getattr(self, "workspace", None),
                profile_id=getattr(self, "profile_id", ""),
            )

            digest = writeback_result.get("digest")
            memory_item = writeback_result.get("memory_item")
            run = writeback_result.get("run")
            if digest and memory_item and run:
                canonical_memory = {
                    "memory_item_id": getattr(memory_item, "id", ""),
                    "digest_id": getattr(digest, "id", ""),
                    "writeback_run_id": getattr(run, "id", ""),
                    "lifecycle_status": getattr(memory_item, "lifecycle_status", ""),
                    "verification_status": getattr(
                        memory_item,
                        "verification_status",
                        "",
                    ),
                }
                self.session.metadata["canonical_memory_item_id"] = memory_item.id
                self.session.metadata["canonical_memory"] = canonical_memory
                self.session_store.update(self.session)
                self._emit_event(
                    EventType.MEMORY_WRITEBACK,
                    payload={
                        "meeting_session_id": self.session.id,
                        "project_id": self.session.project_id,
                        **canonical_memory,
                    },
                    entity_ids=[memory_item.id],
                    metadata={
                        "project_id": self.session.project_id,
                        "memory_item_id": memory_item.id,
                        "digest_id": digest.id,
                        "writeback_run_id": run.id,
                    },
                )
            logger.info(
                "Meeting writeback run %s emitted digest %s and memory item %s for session %s",
                getattr(run, "id", "unknown"),
                getattr(digest, "id", "unknown"),
                getattr(memory_item, "id", "unknown"),
                self.session.id,
            )
        except Exception as exc:
            logger.warning(
                "Failed to execute meeting memory writeback for %s: %s",
                self.session.id,
                exc,
            )

        try:
            from backend.app.system_capabilities.world_memory_core.services.world_memory_writeback_orchestrator import (
                WorldMemoryWritebackOrchestrator,
            )

            world_orchestrator = WorldMemoryWritebackOrchestrator()
            world_memory_writeback = world_orchestrator.run_for_closed_session(
                session=self.session,
                workspace=getattr(self, "workspace", None),
                profile_id=getattr(self, "profile_id", ""),
            )
            if world_memory_writeback.get("updated"):
                self.session.metadata["world_memory_writeback"] = world_memory_writeback
                self.session_store.update(self.session)
        except Exception as exc:
            logger.warning(
                "Failed to execute world-memory writeback for %s: %s",
                self.session.id,
                exc,
            )

        self.session.metadata["memory_impact_trace"] = self._build_memory_impact_trace(
            selected_packet_node_ids=selected_packet_node_ids,
            canonical_memory=canonical_memory,
            world_memory_writeback=world_memory_writeback,
            meeting_decision_ids=[
                getattr(decision, "id", "")
                for decision in decisions
                if getattr(decision, "id", "")
            ],
            action_items=action_items,
        )
        self.session_store.update(self.session)

        self._emit_event(
            EventType.MEETING_END,
            payload={
                "meeting_session_id": self.session.id,
                "round_count": self.session.round_count,
                "action_item_count": len(action_items),
                "state_diff": self.session.state_diff,
                "dispatch_result": dispatch_result,
                "canonical_memory": canonical_memory,
                "world_memory_writeback": world_memory_writeback,
            },
        )

    async def _async_load_installed_playbooks(self) -> str:
        """Load available playbooks for prompt injection.

        Uses iterative discovery with escalation rounds instead of
        single-shot retrieval.  Each round adds candidates to a deduped
        set; search stops when confidence gate passes.

        Rounds:
          1. Scoped semantic RAG (search_rrf, category=playbook)
          2. Structural match via workspace data_sources produces/consumes
          3. Eligible subset scan (installed packs with data_sources only)
        """
        seen: set = set()
        candidates: list = []  # list of (tool_id, display_text)
        ws_id = getattr(self.session, "workspace_id", None)

        def _add(tool_id: str, text: str) -> bool:
            if tool_id in seen:
                return False
            seen.add(tool_id)
            candidates.append((tool_id, text))
            return True

        def _confidence_ok() -> bool:
            """Confidence gate: enough candidates to support LLM decision."""
            return len(candidates) >= 3

        try:
            # ── Round 1: Scoped semantic RAG ──────────────────────────
            try:
                from app.services.tool_embedding_service import (
                    ToolEmbeddingService,
                )

                rag_svc = ToolEmbeddingService()
                agenda = getattr(self.session, "agenda", []) or []
                user_msg = getattr(self, "_last_user_message", "")
                parts = list(agenda) + ([user_msg] if user_msg else [])
                query = "; ".join(parts) if parts else "available playbooks"

                matches, _status = await rag_svc.search_rrf(
                    query=query, top_k=15, min_score=0.15
                )
                pb_matches = [m for m in matches if m.category == "playbook"]
                for m in pb_matches:
                    _add(m.tool_id, f"- {m.tool_id}: {m.display_name}")

                logger.info(
                    "Playbook discovery round=1 semantic candidates=%d "
                    "top=%s action=%s session=%s",
                    len(pb_matches),
                    pb_matches[0].tool_id if pb_matches else "none",
                    "accept" if _confidence_ok() else "escalate",
                    getattr(self.session, "id", "?"),
                )
            except Exception as rag_exc:
                logger.warning("Playbook discovery round=1 failed: %s", rag_exc)

            # ── Round 2: Structural match (produces/consumes) ─────────
            if not _confidence_ok():
                try:
                    from app.services.stores.postgres.workspaces_store import (
                        PostgresWorkspacesStore,
                    )
                    from app.services.manifest_utils import (
                        resolve_playbook_produces,
                    )
                    from pathlib import Path
                    import os
                    import yaml as _yaml

                    # Get workspace data_sources → extract available asset types
                    ws_store = PostgresWorkspacesStore()
                    ws = ws_store.get_workspace_sync(ws_id) if ws_id else None
                    ds = getattr(ws, "data_sources", None) or {}
                    available_types: set = set()
                    for _pack_id, pack_data in ds.items():
                        if isinstance(pack_data, dict):
                            for prod in pack_data.get("produces", []):
                                if isinstance(prod, dict) and prod.get("type"):
                                    available_types.add(prod["type"])

                    if available_types:
                        # Scan manifests for playbooks whose consumes match
                        app_dir = os.getenv("APP_DIR", "/app")
                        cap_dirs = [
                            Path(app_dir) / "backend" / "app" / "capabilities",
                            Path(os.getenv("DATA_DIR", "data")) / "capabilities",
                        ]
                        from app.services.stores.installed_packs_store import (
                            InstalledPacksStore,
                        )

                        packs_store = InstalledPacksStore()
                        pack_ids = packs_store.list_enabled_pack_ids()
                        r2_count = 0
                        for pack_id in pack_ids:
                            for cap_base in cap_dirs:
                                mpath = cap_base / pack_id / "manifest.yaml"
                                if not mpath.exists():
                                    continue
                                try:
                                    with mpath.open("r", encoding="utf-8") as mf:
                                        manifest = _yaml.safe_load(mf) or {}
                                    for pb in manifest.get("playbooks", []):
                                        if not isinstance(pb, dict):
                                            continue
                                        code = pb.get("code", "")
                                        if not code or code in seen:
                                            continue
                                        # Check consumes match (supports both
                                        # bare string and dict {type: ...} forms)
                                        consumes = pb.get("consumes") or []
                                        consumes_types = {
                                            (c.get("type", "") if isinstance(c, dict) else c)
                                            for c in consumes
                                            if c
                                        }
                                        if consumes_types & available_types:
                                            desc = (pb.get("description") or code)[:60]
                                            if _add(code, f"- {code}: {desc}"):
                                                r2_count += 1
                                except Exception as exc:
                                    logger.warning(
                                        f"R2 Error parsing manifest for pack {pack_id}: {exc}"
                                    )
                                break

                        logger.info(
                            "Playbook discovery round=2 structural +%d "
                            "candidates=%d action=%s",
                            r2_count,
                            len(candidates),
                            "accept" if _confidence_ok() else "escalate",
                        )
                except Exception as r2_exc:
                    logger.warning("Playbook discovery round=2 failed: %s", r2_exc)

            # ── Round 3: Eligible subset scan ─────────────────────────
            if not _confidence_ok():
                try:
                    from app.services.stores.postgres.workspaces_store import (
                        PostgresWorkspacesStore,
                    )
                    from app.services.stores.installed_packs_store import (
                        InstalledPacksStore,
                    )
                    from pathlib import Path
                    import os
                    import yaml as _yaml

                    # Scope: all globally installed packs as a fallback
                    packs_store = InstalledPacksStore()
                    eligible_packs = set(packs_store.list_enabled_pack_ids())

                    app_dir = os.getenv("APP_DIR", "/app")
                    cap_dirs = [
                        Path(app_dir) / "backend" / "app" / "capabilities",
                        Path(os.getenv("DATA_DIR", "data")) / "capabilities",
                    ]
                    r3_count = 0
                    for pack_id in eligible_packs:
                        for cap_base in cap_dirs:
                            mpath = cap_base / pack_id / "manifest.yaml"
                            if not mpath.exists():
                                continue
                            try:
                                with mpath.open("r", encoding="utf-8") as mf:
                                    manifest = _yaml.safe_load(mf) or {}
                                for pb in manifest.get("playbooks", []):
                                    if isinstance(pb, dict):
                                        code = pb.get("code", "")
                                        desc = (pb.get("description") or code)[:60]
                                        logger.info(
                                            f"R3 parsing pb={code} from pack={pack_id}"
                                        )
                                        if code and _add(code, f"- {code}: {desc}"):
                                            r3_count += 1
                                            logger.info(f"R3 added {code}")
                            except Exception as exc:
                                logger.warning(
                                    f"R3 Error parsing manifest for pack {pack_id}: {exc}"
                                )
                            break
                        else:
                            logger.info(f"R3 manifest NOT FOUND for pack {pack_id}")

                    logger.info(
                        "Playbook discovery round=3 eligible_scan +%d "
                        "candidates=%d packs=%d",
                        r3_count,
                        len(candidates),
                        len(eligible_packs),
                    )
                except Exception as r3_exc:
                    logger.warning("Playbook discovery round=3 failed: %s", r3_exc)

            if candidates:
                return "\n".join(text for _, text in candidates)
            return "(no playbooks discovered)"
        except Exception as exc:
            logger.warning("Failed to load installed playbooks: %s", exc, exc_info=True)
            return "(playbook discovery unavailable)"
