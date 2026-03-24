"""Compile governance memory packets into ordered prompt context."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class MemoryPacketCompiler:
    """Turn a governance-selected packet into ordered prompt sections."""

    def build_route_plan(
        self,
        governance_packet: Optional[Dict[str, Any]],
        *,
        include_semantic_hits: bool = False,
    ) -> List[str]:
        if not governance_packet:
            return []

        layers = (governance_packet.get("memory_packet") or {}).get("layers") or {}
        route: List[str] = []

        if self._has_core_layer(layers.get("core")):
            route.append("core")
        if (layers.get("knowledge") or {}).get("verified"):
            route.append("verified_knowledge")
        if (layers.get("goals") or {}).get("active"):
            route.append("active_goals")
        if self._has_project_layer(layers.get("project")):
            route.append("project_memory")
        if self._has_member_layer(layers.get("member")):
            route.append("member_memory")
        if (layers.get("knowledge") or {}).get("candidates"):
            route.append("candidate_knowledge")
        if (layers.get("goals") or {}).get("pending"):
            route.append("pending_goals")
        if layers.get("episodic"):
            route.append("episodic_evidence")
        if include_semantic_hits:
            route.append("semantic_hits")

        return route

    def compile_for_context(
        self, governance_packet: Optional[Dict[str, Any]]
    ) -> str:
        if not governance_packet:
            return ""

        memory_packet = governance_packet.get("memory_packet") or {}
        selection = memory_packet.get("selection") or {}
        layers = memory_packet.get("layers") or {}
        parts: List[str] = []

        workspace_mode = selection.get("workspace_mode")
        memory_scope = selection.get("memory_scope")
        if workspace_mode or memory_scope:
            label = " / ".join(
                [value for value in (workspace_mode, memory_scope) if value]
            )
            if label:
                parts.append(f"Routing mode: {label}")

        core = layers.get("core") or {}
        if self._has_core_layer(core):
            parts.append("Core directives:")
            if core.get("brand_identity"):
                parts.append(f"- Brand identity: {core.get('brand_identity')}")
            if core.get("voice_and_tone"):
                parts.append(f"- Voice and tone: {core.get('voice_and_tone')}")
            if core.get("style_constraints"):
                constraints = ", ".join(core.get("style_constraints")[:6])
                parts.append(f"- Style constraints: {constraints}")
            if core.get("learnings"):
                for learning in core.get("learnings")[:3]:
                    parts.append(f"- Learned standard: {learning}")

        verified_knowledge = (layers.get("knowledge") or {}).get("verified") or []
        if verified_knowledge:
            parts.append("Guiding knowledge:")
            for item in verified_knowledge[:5]:
                parts.append(
                    f"- [{item.get('knowledge_type', 'knowledge')}] {item.get('content', '')}"
                )

        active_goals = (layers.get("goals") or {}).get("active") or []
        if active_goals:
            parts.append("Active goals:")
            for item in active_goals[:4]:
                line = f"- {item.get('title', '')}"
                description = item.get("description") or ""
                if description:
                    line += f": {description}"
                parts.append(line)

        project_memory = layers.get("project") or {}
        if self._has_project_layer(project_memory):
            parts.append("Project decisions:")
            for item in (project_memory.get("decision_history") or [])[:3]:
                decision = item.get("decision") or ""
                rationale = item.get("rationale") or ""
                line = f"- {decision}"
                if rationale:
                    line += f": {rationale}"
                parts.append(line)
            for conversation in (project_memory.get("key_conversations") or [])[:2]:
                parts.append(f"- Project thread: {conversation}")

        member_memory = layers.get("member") or {}
        if self._has_member_layer(member_memory):
            parts.append("Member strengths:")
            skills = member_memory.get("skills") or []
            if skills:
                parts.append(f"- Skills: {', '.join(skills[:6])}")
            preferences = member_memory.get("preferences") or {}
            for key, value in list(preferences.items())[:2]:
                parts.append(f"- Preference {key}: {value}")
            for learning in (member_memory.get("learnings") or [])[:2]:
                parts.append(f"- Repeated learning: {learning}")

        candidate_knowledge = (layers.get("knowledge") or {}).get("candidates") or []
        if candidate_knowledge:
            parts.append("Emerging candidates:")
            for item in candidate_knowledge[:3]:
                parts.append(
                    f"- [{item.get('knowledge_type', 'candidate')}] {item.get('content', '')}"
                )

        pending_goals = (layers.get("goals") or {}).get("pending") or []
        if pending_goals:
            parts.append("Pending goals:")
            for item in pending_goals[:2]:
                parts.append(f"- {item.get('title', '')}")

        episodic_items = layers.get("episodic") or []
        if episodic_items:
            parts.append("Recent episodes:")
            episodic_limit = selection.get("episodic_limit", 3)
            for item in episodic_items[:episodic_limit]:
                text = item.get("summary") or item.get("claim") or item.get("title") or ""
                if text:
                    parts.append(f"- {text}")

        return "\n".join(parts)

    @staticmethod
    def _has_core_layer(core: Optional[Dict[str, Any]]) -> bool:
        if not core:
            return False
        return any(
            core.get(key)
            for key in (
                "brand_identity",
                "voice_and_tone",
                "style_constraints",
                "learnings",
            )
        )

    @staticmethod
    def _has_project_layer(project: Optional[Dict[str, Any]]) -> bool:
        if not project:
            return False
        return bool(
            project.get("decision_history")
            or project.get("key_conversations")
            or project.get("artifact_index")
        )

    @staticmethod
    def _has_member_layer(member: Optional[Dict[str, Any]]) -> bool:
        if not member:
            return False
        return bool(
            member.get("skills")
            or member.get("preferences")
            or member.get("learnings")
        )
