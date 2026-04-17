"""Governance-context read model for memory packet compilation."""

from __future__ import annotations

import logging
from datetime import datetime
from types import SimpleNamespace
from typing import Any, Dict, Optional

from backend.app.models.memory_contract import (
    MemoryLayer,
    MemoryLifecycleStatus,
    MemoryVerificationStatus,
)
from backend.app.services.governance.lens_policy_memory_selector import (
    LensPolicyMemorySelector,
)
from backend.app.services.governance.memory_packet_compiler import (
    MemoryPacketCompiler,
)
from backend.app.services.memory.member_profile_memory import (
    MemberProfileMemoryService,
)
from backend.app.services.memory.project_memory import ProjectMemoryService
from backend.app.services.memory.workspace_core_memory import (
    WorkspaceCoreMemoryService,
)
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.orchestration.meeting.spatial_scheduling_compiler import (
    merge_spatial_schedule_context,
    normalize_spatial_schedule_context,
)
from backend.app.services.stores.postgres.goal_ledger_store import GoalLedgerStore
from backend.app.services.stores.postgres.memory_item_store import MemoryItemStore
from backend.app.services.stores.postgres.personal_knowledge_store import (
    PersonalKnowledgeStore,
)
logger = logging.getLogger(__name__)


class GovernanceContextReadModel:
    """Compile governance context and selected memory into a single packet."""

    def __init__(
        self,
        *,
        store: Optional[MindscapeStore] = None,
        workspace_core_memory_service: Optional[WorkspaceCoreMemoryService] = None,
        project_memory_service: Optional[ProjectMemoryService] = None,
        member_profile_memory_service: Optional[MemberProfileMemoryService] = None,
        personal_knowledge_store: Optional[PersonalKnowledgeStore] = None,
        goal_ledger_store: Optional[GoalLedgerStore] = None,
        memory_item_store: Optional[MemoryItemStore] = None,
        selector: Optional[LensPolicyMemorySelector] = None,
        packet_compiler: Optional[MemoryPacketCompiler] = None,
        meeting_session_store: Optional[Any] = None,
    ):
        self.store = store or MindscapeStore()
        self.workspace_core_memory_service = (
            workspace_core_memory_service or WorkspaceCoreMemoryService(self.store)
        )
        self.project_memory_service = (
            project_memory_service or ProjectMemoryService(self.store)
        )
        self.member_profile_memory_service = (
            member_profile_memory_service or MemberProfileMemoryService(self.store)
        )
        self.personal_knowledge_store = personal_knowledge_store or PersonalKnowledgeStore()
        self.goal_ledger_store = goal_ledger_store or GoalLedgerStore()
        self.memory_item_store = memory_item_store or MemoryItemStore()
        self.selector = selector or LensPolicyMemorySelector()
        self.packet_compiler = packet_compiler or MemoryPacketCompiler()
        self.meeting_session_store = meeting_session_store

    async def build_for_workspace(
        self,
        workspace: Optional[Any] = None,
        *,
        workspace_id: Optional[str] = None,
        profile_id: Optional[str] = None,
        project_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        workspace_ref = workspace
        if workspace_ref is None and workspace_id:
            workspace_ref = await self.store.get_workspace(workspace_id)
        if workspace_ref is None:
            return None

        resolved_workspace_id = getattr(workspace_ref, "id", None) or workspace_id
        if not resolved_workspace_id:
            return None

        resolved_profile_id = (
            profile_id
            or getattr(workspace_ref, "owner_user_id", None)
            or ""
        )
        resolved_project_id = project_id or getattr(workspace_ref, "primary_project_id", None)

        core_memory = await self._safe_get_workspace_core_memory(resolved_workspace_id)
        project_memory = await self._safe_get_project_memory(
            resolved_project_id, resolved_workspace_id
        )
        member_memory = await self._safe_get_member_memory(
            resolved_profile_id, resolved_workspace_id
        )
        canonical_items = self._safe_get_recent_canonical_items(resolved_workspace_id)
        personal_knowledge = self._safe_list_personal_knowledge(resolved_profile_id)
        goal_entries = self._safe_list_goal_entries(resolved_profile_id)

        lens_context = self._build_lens_context(
            workspace_ref,
            workspace_mode=getattr(workspace_ref, "mode", None),
            session_id=session_id,
        )
        policy_context = self._build_policy_context(workspace_ref)
        spatial_schedule_context = self._build_spatial_schedule_context(
            workspace_ref,
            workspace_id=resolved_workspace_id,
            session_id=session_id,
        )

        memory_packet = self.selector.select_packet(
            canonical_items=canonical_items,
            personal_knowledge_entries=personal_knowledge,
            goal_entries=goal_entries,
            workspace_core_memory=core_memory,
            project_memory=project_memory,
            member_memory=member_memory,
            lens_context=lens_context,
            policy_context=policy_context,
            workspace_mode=getattr(workspace_ref, "mode", None),
        )

        return {
            "governance_context": {
                "workspace_id": resolved_workspace_id,
                "profile_id": resolved_profile_id,
                "project_id": resolved_project_id,
                "mode": getattr(workspace_ref, "mode", None),
                "execution_mode": getattr(workspace_ref, "execution_mode", None),
                "lens": lens_context,
                "policy": policy_context,
                "sources": {
                    "canonical_item_count": len(canonical_items),
                    "personal_knowledge_count": len(personal_knowledge),
                    "goal_count": len(goal_entries),
                    "has_project_memory": project_memory is not None,
                    "has_member_memory": member_memory is not None,
                    "has_spatial_schedule": spatial_schedule_context is not None,
                },
                "spatial_schedule_context": spatial_schedule_context,
            },
            "memory_packet": memory_packet,
        }

    def format_memory_packet_for_context(
        self, governance_packet: Optional[Dict[str, Any]]
    ) -> str:
        return self.packet_compiler.compile_for_context(governance_packet)

    async def _safe_get_workspace_core_memory(self, workspace_id: str) -> Optional[Any]:
        try:
            return await self.workspace_core_memory_service.get_core_memory(workspace_id)
        except Exception as exc:
            logger.debug("Failed to load workspace core memory for %s: %s", workspace_id, exc)
            return None

    async def _safe_get_project_memory(
        self, project_id: Optional[str], workspace_id: str
    ) -> Optional[Any]:
        if not project_id:
            return None
        try:
            return await self.project_memory_service.get_project_memory(
                project_id, workspace_id
            )
        except Exception as exc:
            logger.debug("Failed to load project memory for %s: %s", project_id, exc)
            return None

    async def _safe_get_member_memory(
        self, profile_id: str, workspace_id: str
    ) -> Optional[Any]:
        if not profile_id:
            return None
        try:
            return await self.member_profile_memory_service.get_member_memory(
                profile_id, workspace_id
            )
        except Exception as exc:
            logger.debug("Failed to load member memory for %s: %s", profile_id, exc)
            return None

    def _safe_get_recent_canonical_items(self, workspace_id: str) -> list[Any]:
        try:
            return self.memory_item_store.list_for_context(
                context_type="workspace",
                context_id=workspace_id,
                layer=MemoryLayer.EPISODIC.value,
                lifecycle_statuses=[
                    MemoryLifecycleStatus.CANDIDATE.value,
                    MemoryLifecycleStatus.ACTIVE.value,
                    MemoryLifecycleStatus.STALE.value,
                ],
                verification_statuses=[
                    MemoryVerificationStatus.OBSERVED.value,
                    MemoryVerificationStatus.VERIFIED.value,
                    MemoryVerificationStatus.CHALLENGED.value,
                ],
                limit=12,
            )
        except Exception as exc:
            logger.debug(
                "Failed to load canonical memory items for workspace %s: %s",
                workspace_id,
                exc,
            )
            return []

    def _safe_list_personal_knowledge(self, profile_id: str) -> list[Any]:
        if not profile_id:
            return []
        try:
            return self.personal_knowledge_store.list_by_owner(profile_id, limit=20)
        except Exception as exc:
            logger.debug(
                "Failed to load personal knowledge for profile %s: %s",
                profile_id,
                exc,
            )
            return []

    def _safe_list_goal_entries(self, profile_id: str) -> list[Any]:
        if not profile_id:
            return []
        try:
            return self.goal_ledger_store.list_by_owner(profile_id, limit=12)
        except Exception as exc:
            logger.debug("Failed to load goals for profile %s: %s", profile_id, exc)
            return []

    def _build_lens_context(
        self,
        workspace: Any,
        *,
        workspace_mode: Optional[str],
        session_id: Optional[str],
    ) -> Dict[str, Any]:
        metadata = dict(getattr(workspace, "metadata", {}) or {})
        lens_metadata = dict(metadata.get("mind_lens", {}) or {})
        lens_id = lens_metadata.get("lens_id") or metadata.get("lens_id")
        return {
            "workspace_mode": workspace_mode,
            "session_id": session_id,
            "lens_id": lens_id,
            "lens_label": lens_metadata.get("label"),
            "style_rules": lens_metadata.get("style_rules", []),
            "emphasized_values": lens_metadata.get("emphasized_values", []),
        }

    def _build_policy_context(self, workspace: Any) -> Dict[str, Any]:
        runtime_profile = getattr(workspace, "runtime_profile", None)
        runtime_metadata = dict(getattr(runtime_profile, "metadata", {}) or {})
        workspace_metadata = dict(getattr(workspace, "metadata", {}) or {})
        governance_memory = dict(workspace_metadata.get("governance_memory", {}) or {})
        sandbox_config = dict(getattr(workspace, "sandbox_config", {}) or {})

        memory_scope = (
            governance_memory.get("memory_scope")
            or runtime_metadata.get("memory_scope")
            or "standard"
        )

        policy_context = {
            "memory_scope": memory_scope,
            "include_project_memory": governance_memory.get("include_project_memory"),
            "include_member_memory": governance_memory.get("include_member_memory"),
            "max_episodic_items": governance_memory.get("max_episodic_items"),
            "tool_policy": {
                "allowlist": getattr(
                    getattr(runtime_profile, "tool_policy", None), "allowlist", None
                ),
                "denylist": getattr(
                    getattr(runtime_profile, "tool_policy", None), "denylist", None
                ),
            },
            "loop_budget": {
                "max_iterations": getattr(
                    getattr(runtime_profile, "loop_budget", None),
                    "max_iterations",
                    None,
                ),
                "timeout_seconds": getattr(
                    getattr(runtime_profile, "loop_budget", None),
                    "timeout_seconds",
                    None,
                ),
            },
            "sandbox": {
                "filesystem_scope": sandbox_config.get("filesystem_scope"),
                "network_allowlist": sandbox_config.get("network_allowlist"),
                "tool_policies": sandbox_config.get("tool_policies"),
            },
        }

        return {
            key: value
            for key, value in policy_context.items()
            if value not in (None, {}, [])
        }

    def _build_spatial_schedule_context(
        self,
        workspace: Any,
        *,
        workspace_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        workspace_metadata = dict(getattr(workspace, "metadata", {}) or {})
        workspace_context = normalize_spatial_schedule_context(
            workspace_metadata.get("spatial_schedule_context")
        )
        session_context = self._safe_get_session_spatial_schedule_context(
            workspace_id=workspace_id or getattr(workspace, "id", None),
            session_id=session_id,
        )
        if session_context is None:
            return workspace_context
        if workspace_context is None:
            return session_context
        if not self._should_prefer_session_schedule(
            existing=workspace_context,
            incoming=session_context,
        ):
            return workspace_context
        return merge_spatial_schedule_context(
            existing=workspace_context,
            incoming=session_context,
        )

    def _safe_get_session_spatial_schedule_context(
        self,
        *,
        workspace_id: Optional[str],
        session_id: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        if not session_id:
            return None

        session_store = self.meeting_session_store
        if session_store is None:
            try:
                from backend.app.services.stores.meeting_session_store import (
                    MeetingSessionStore,
                )
            except Exception as exc:
                logger.debug(
                    "MeetingSessionStore import failed for spatial schedule context: %s",
                    exc,
                )
                return None
            session_store = MeetingSessionStore()
            self.meeting_session_store = session_store

        get_by_id = getattr(session_store, "get_by_id", None)
        if not callable(get_by_id):
            return None

        try:
            session = get_by_id(session_id)
        except Exception as exc:
            logger.debug(
                "Failed to load meeting session %s for spatial schedule context: %s",
                session_id,
                exc,
            )
            return None

        if session is None:
            return None
        if workspace_id and getattr(session, "workspace_id", None) not in (None, workspace_id):
            return None
        return normalize_spatial_schedule_context(
            dict(getattr(session, "metadata", {}) or {}).get("spatial_schedule_context")
        )

    @staticmethod
    def _should_prefer_session_schedule(
        *,
        existing: Optional[Dict[str, Any]],
        incoming: Optional[Dict[str, Any]],
    ) -> bool:
        if not isinstance(incoming, dict) or not incoming.get("schedule_id"):
            return False
        if not isinstance(existing, dict) or not existing.get("schedule_id"):
            return True

        incoming_updated_at = GovernanceContextReadModel._parse_schedule_updated_at(
            incoming.get("updated_at")
        )
        existing_updated_at = GovernanceContextReadModel._parse_schedule_updated_at(
            existing.get("updated_at")
        )
        if incoming_updated_at and existing_updated_at:
            return incoming_updated_at >= existing_updated_at
        if incoming_updated_at and not existing_updated_at:
            return True
        if not incoming_updated_at and existing_updated_at:
            return False
        return incoming.get("schedule_id") != existing.get("schedule_id") or incoming == existing

    @staticmethod
    def _parse_schedule_updated_at(value: Any) -> Optional[datetime]:
        if not isinstance(value, str) or not value.strip():
            return None
        normalized = value.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            return None

    @staticmethod
    def _derive_schedule_artifact_ref(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        source_artifact_id = raw.get("source_artifact_id")
        if source_artifact_id:
            return {
                "artifact_id": source_artifact_id,
                "type": raw.get("artifact_type")
                or "application/vnd.mindscape.spatial-scheduling+json",
            }

        artifact_refs = list(raw.get("artifact_refs") or [])
        for artifact_ref in artifact_refs:
            if isinstance(artifact_ref, dict) and artifact_ref.get("artifact_id"):
                return {
                    "artifact_id": artifact_ref.get("artifact_id"),
                    "type": artifact_ref.get("type")
                    or "application/vnd.mindscape.spatial-scheduling+json",
                }
        return None

    @staticmethod
    def _derive_active_segments(raw: Dict[str, Any]) -> list[Dict[str, Any]]:
        segment_ids = list(raw.get("active_segment_ids") or [])
        segments = []
        for segment_id in segment_ids:
            segments.append(
                {
                    "segment_id": segment_id,
                    "title": segment_id,
                    "entity_refs": [],
                    "anchor_ids": [],
                }
            )
        return segments

    @staticmethod
    def _derive_consumer_receipts(raw: Dict[str, Any]) -> Dict[str, Any]:
        receipts: Dict[str, Any] = {}
        for consumer_ref in list(raw.get("consumer_refs") or []):
            if not isinstance(consumer_ref, dict):
                continue
            consumer_code = consumer_ref.get("consumer_code")
            if not consumer_code:
                continue
            receipts[str(consumer_code)] = {
                "status": consumer_ref.get("status"),
                "receipt_ref": {
                    "artifact_id": consumer_ref.get("receipt_artifact_id"),
                },
            }
        return receipts

    async def build_for_workspace_id(
        self,
        workspace_id: str,
        *,
        profile_id: Optional[str] = None,
        project_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        workspace = await self.store.get_workspace(workspace_id)
        if workspace is None:
            workspace = SimpleNamespace(
                id=workspace_id,
                owner_user_id=profile_id or "",
                primary_project_id=project_id,
                mode=None,
                execution_mode=None,
                runtime_profile=None,
                sandbox_config={},
                metadata={},
            )
        return await self.build_for_workspace(
            workspace,
            workspace_id=workspace_id,
            profile_id=profile_id,
            project_id=project_id,
            session_id=session_id,
        )
