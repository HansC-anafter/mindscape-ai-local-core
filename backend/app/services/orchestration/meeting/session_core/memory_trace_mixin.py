"""Selected memory packet and impact trace helpers."""

import logging
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class MeetingSessionMemoryTraceMixin:
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

    @staticmethod
    def _has_selected_source_refs(value: Any) -> bool:
        if isinstance(value, dict):
            refs = value.get("selected_object_refs") or value.get("context_attachments")
            if isinstance(refs, list) and refs:
                return True
            return any(
                MeetingSessionMemoryTraceMixin._has_selected_source_refs(item)
                for item in value.values()
            )
        if isinstance(value, list):
            return any(
                MeetingSessionMemoryTraceMixin._has_selected_source_refs(item) for item in value
            )
        return False

    def _requires_command_bounded_memory(self) -> bool:
        session = getattr(self, "session", None)
        metadata = dict(getattr(session, "metadata", None) or {})
        request_contract = metadata.get("request_contract")
        if self._has_selected_source_refs(request_contract):
            return True

        meeting_type = str(getattr(session, "meeting_type", "") or "").lower()
        if meeting_type in {"e2e_validation", "command_validation"}:
            return True

        agenda_text = " ".join(
            str(item).lower()
            for item in list(getattr(session, "agenda", None) or [])
        )
        user_message = str(getattr(self, "_last_user_message", "") or "").lower()
        combined = f"{agenda_text} {user_message}"
        return (
            "selected" in combined
            and "reference" in combined
            and ("storyboard" in combined or "reels" in combined)
        )

    def _memory_policy_context_for_session(
        self,
        *,
        read_model: Any,
        workspace: Any,
    ) -> Dict[str, Any]:
        policy_context = dict(read_model._build_policy_context(workspace))
        if self._requires_command_bounded_memory():
            policy_context["memory_scope"] = "command_bounded"
            policy_context["max_episodic_items"] = 0
            policy_context["episodic_exclusion_reason"] = (
                "explicit_source_reference_command"
            )
        return policy_context

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
                policy_context=self._memory_policy_context_for_session(
                    read_model=read_model,
                    workspace=workspace,
                ),
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
        }
        return {
            "explicit": {
                key: value
                for key, value in explicit.items()
                if value not in (None, [], {})
            },
            "inferred": None,
        }
