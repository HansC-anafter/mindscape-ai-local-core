"""Lens/policy-aware selection for governance memory packets."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from backend.app.models.memory_contract import MemoryLifecycleStatus
from backend.app.models.personal_governance.goal_ledger import GoalStatus
from backend.app.models.personal_governance.personal_knowledge import KnowledgeStatus


class LensPolicyMemorySelector:
    """Compile a compact memory packet from mixed governance surfaces."""
    _CANDIDATE_KNOWLEDGE_STATUSES = {
        KnowledgeStatus.CANDIDATE.value,
        KnowledgeStatus.PENDING_CONFIRMATION.value,
        KnowledgeStatus.MIGRATED_UNVERIFIED.value,
    }
    _PENDING_GOAL_STATUSES = {
        GoalStatus.CANDIDATE.value,
        GoalStatus.PENDING_CONFIRMATION.value,
    }
    _VISIBLE_EPISODIC_LIFECYCLE_STATUSES = {
        MemoryLifecycleStatus.CANDIDATE.value,
        MemoryLifecycleStatus.ACTIVE.value,
    }

    _MODE_DEFAULTS: Dict[str, Dict[str, Any]] = {
        "research": {
            "episodic_limit": 5,
            "verified_knowledge_limit": 8,
            "candidate_knowledge_limit": 3,
            "goal_limit": 6,
            "include_project_memory": True,
            "include_member_memory": True,
        },
        "planning": {
            "episodic_limit": 4,
            "verified_knowledge_limit": 6,
            "candidate_knowledge_limit": 3,
            "goal_limit": 6,
            "include_project_memory": True,
            "include_member_memory": True,
        },
        "publishing": {
            "episodic_limit": 2,
            "verified_knowledge_limit": 6,
            "candidate_knowledge_limit": 2,
            "goal_limit": 4,
            "include_project_memory": True,
            "include_member_memory": False,
        },
        "default": {
            "episodic_limit": 3,
            "verified_knowledge_limit": 5,
            "candidate_knowledge_limit": 2,
            "goal_limit": 4,
            "include_project_memory": True,
            "include_member_memory": True,
        },
    }

    def select_packet(
        self,
        *,
        canonical_items: List[Any],
        personal_knowledge_entries: List[Any],
        goal_entries: List[Any],
        workspace_core_memory: Optional[Any],
        project_memory: Optional[Any],
        member_memory: Optional[Any],
        lens_context: Optional[Dict[str, Any]] = None,
        policy_context: Optional[Dict[str, Any]] = None,
        workspace_mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        lens_context = dict(lens_context or {})
        policy_context = dict(policy_context or {})

        mode = (workspace_mode or lens_context.get("workspace_mode") or "default").lower()
        config = dict(self._MODE_DEFAULTS.get(mode, self._MODE_DEFAULTS["default"]))

        memory_scope = str(policy_context.get("memory_scope") or "standard").lower()
        if memory_scope == "core_only":
            config["episodic_limit"] = 0
            config["include_project_memory"] = False
            config["include_member_memory"] = False
            config["candidate_knowledge_limit"] = 0
        elif memory_scope == "extended":
            config["episodic_limit"] += 2
            config["verified_knowledge_limit"] += 2
            config["goal_limit"] += 1

        max_episodic = policy_context.get("max_episodic_items")
        if isinstance(max_episodic, int) and max_episodic >= 0:
            config["episodic_limit"] = max_episodic

        for flag in ("include_project_memory", "include_member_memory"):
            override = policy_context.get(flag)
            if isinstance(override, bool):
                config[flag] = override

        verified_knowledge = [
            item
            for item in personal_knowledge_entries
            if getattr(item, "status", "") == KnowledgeStatus.VERIFIED.value
        ][: config["verified_knowledge_limit"]]
        candidate_knowledge = [
            item
            for item in personal_knowledge_entries
            if getattr(item, "status", "") in self._CANDIDATE_KNOWLEDGE_STATUSES
        ][: config["candidate_knowledge_limit"]]

        active_goals = [
            item
            for item in goal_entries
            if getattr(item, "status", "") == GoalStatus.ACTIVE.value
        ][: config["goal_limit"]]
        pending_goals = [
            item
            for item in goal_entries
            if getattr(item, "status", "") in self._PENDING_GOAL_STATUSES
        ][:2]

        episodic_items = sorted(
            [
                item
                for item in canonical_items
                if getattr(item, "lifecycle_status", "")
                in self._VISIBLE_EPISODIC_LIFECYCLE_STATUSES
            ],
            key=lambda item: (
                float(getattr(item, "salience", 0.0) or 0.0),
                self._to_ts(getattr(item, "observed_at", None)),
                self._to_ts(getattr(item, "created_at", None)),
            ),
            reverse=True,
        )[: config["episodic_limit"]]

        return {
            "selection": {
                "workspace_mode": workspace_mode or lens_context.get("workspace_mode"),
                "memory_scope": memory_scope,
                "episodic_limit": config["episodic_limit"],
                "include_project_memory": config["include_project_memory"],
                "include_member_memory": config["include_member_memory"],
                "lens_context": lens_context,
                "policy_context": policy_context,
            },
            "layers": {
                "core": self._serialize_core_memory(workspace_core_memory),
                "knowledge": {
                    "verified": [
                        self._serialize_knowledge(item) for item in verified_knowledge
                    ],
                    "candidates": [
                        self._serialize_knowledge(item) for item in candidate_knowledge
                    ],
                },
                "goals": {
                    "active": [self._serialize_goal(item) for item in active_goals],
                    "pending": [self._serialize_goal(item) for item in pending_goals],
                },
                "episodic": [
                    self._serialize_memory_item(item) for item in episodic_items
                ],
                "project": (
                    self._serialize_project_memory(project_memory)
                    if config["include_project_memory"]
                    else None
                ),
                "member": (
                    self._serialize_member_memory(member_memory)
                    if config["include_member_memory"]
                    else None
                ),
            },
        }

    @staticmethod
    def _to_ts(value: Optional[datetime]) -> float:
        if value is None:
            return 0.0
        return value.timestamp()

    @staticmethod
    def _serialize_core_memory(memory: Optional[Any]) -> Optional[Dict[str, Any]]:
        if memory is None:
            return None
        return {
            "brand_identity": getattr(memory, "brand_identity", None),
            "voice_and_tone": getattr(memory, "voice_and_tone", None),
            "style_constraints": getattr(memory, "style_constraints", None),
            "important_milestones": getattr(memory, "important_milestones", None),
            "learnings": getattr(memory, "learnings", None),
        }

    @staticmethod
    def _serialize_project_memory(memory: Optional[Any]) -> Optional[Dict[str, Any]]:
        if memory is None:
            return None
        return {
            "project_id": getattr(memory, "project_id", ""),
            "decision_history": [
                {
                    "decision": getattr(item, "decision", ""),
                    "rationale": getattr(item, "rationale", ""),
                }
                for item in list(getattr(memory, "decision_history", []) or [])[:5]
            ],
            "key_conversations": list(getattr(memory, "key_conversations", []) or [])[:5],
            "artifact_index": list(getattr(memory, "artifact_index", []) or [])[:5],
        }

    @staticmethod
    def _serialize_member_memory(memory: Optional[Any]) -> Optional[Dict[str, Any]]:
        if memory is None:
            return None
        return {
            "user_id": getattr(memory, "user_id", ""),
            "skills": list(getattr(memory, "skills", []) or [])[:8],
            "preferences": getattr(memory, "preferences", None),
            "learnings": list(getattr(memory, "learnings", []) or [])[:5],
        }

    @staticmethod
    def _serialize_knowledge(item: Any) -> Dict[str, Any]:
        return {
            "id": getattr(item, "id", ""),
            "knowledge_type": getattr(item, "knowledge_type", ""),
            "content": getattr(item, "content", ""),
            "status": getattr(item, "status", ""),
            "confidence": getattr(item, "confidence", None),
            "valid_scope": getattr(item, "valid_scope", "global"),
        }

    @staticmethod
    def _serialize_goal(item: Any) -> Dict[str, Any]:
        return {
            "id": getattr(item, "id", ""),
            "title": getattr(item, "title", ""),
            "description": getattr(item, "description", ""),
            "status": getattr(item, "status", ""),
            "horizon": getattr(item, "horizon", ""),
        }

    @staticmethod
    def _serialize_memory_item(item: Any) -> Dict[str, Any]:
        return {
            "id": getattr(item, "id", ""),
            "kind": getattr(item, "kind", ""),
            "layer": getattr(item, "layer", ""),
            "title": getattr(item, "title", ""),
            "summary": getattr(item, "summary", ""),
            "claim": getattr(item, "claim", ""),
            "salience": getattr(item, "salience", None),
            "confidence": getattr(item, "confidence", None),
            "lifecycle_status": getattr(item, "lifecycle_status", ""),
            "verification_status": getattr(item, "verification_status", ""),
            "observed_at": (
                getattr(item, "observed_at", None).isoformat()
                if getattr(item, "observed_at", None)
                else None
            ),
        }
