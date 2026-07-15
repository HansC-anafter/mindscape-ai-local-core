"""Authorized group-memory reader and non-persistent agent-view policy."""

import hashlib
import json
from typing import Dict, Optional, Sequence, Tuple

from backend.app.services.knowledge_projection.contracts import (
    GroupKnowledgePacket,
    GroupKnowledgePacketEntry,
)
from backend.app.services.stores.postgres.memory_item_store import MemoryItemStore
from backend.app.services.workspace_groups.facade import WorkspaceGroupFacade
from backend.app.services.workspace_groups.snapshot_service import (
    WorkspaceGroupSnapshotService,
)


class GroupKnowledgeAccessError(PermissionError):
    pass


class AgentKnowledgeViewPolicy:
    """Select a role view; no agent-specific memory rows are created."""

    @staticmethod
    def allows(item, *, agent_role: str) -> bool:
        metadata = item.metadata or {}
        allowed_roles = metadata.get("allowed_agent_roles")
        denied_roles = metadata.get("denied_agent_roles") or []
        if agent_role in denied_roles:
            return False
        if allowed_roles is None:
            return True
        return agent_role in allowed_roles


class GroupKnowledgeContextReader:
    """Compile at most one packet per role/snapshot/revision on this run reader."""

    def __init__(
        self,
        *,
        snapshot_service: Optional[WorkspaceGroupSnapshotService] = None,
        group_facade: Optional[WorkspaceGroupFacade] = None,
        memory_store: Optional[MemoryItemStore] = None,
        view_policy: Optional[AgentKnowledgeViewPolicy] = None,
    ) -> None:
        self.snapshot_service = snapshot_service or WorkspaceGroupSnapshotService()
        self.group_facade = group_facade or WorkspaceGroupFacade()
        self.memory_store = memory_store or MemoryItemStore()
        self.view_policy = view_policy or AgentKnowledgeViewPolicy()
        self._cache: Dict[Tuple[str, str, str, str], GroupKnowledgePacket] = {}

    def compile_packet(
        self,
        *,
        topology_snapshot_id: str,
        requesting_workspace_id: str,
        actor_user_id: str,
        agent_role: str,
        allowed_group_ids: Sequence[str] = (),
        limit: int = 100,
    ) -> GroupKnowledgePacket:
        request_cache_key = (
            actor_user_id,
            requesting_workspace_id,
            agent_role,
            topology_snapshot_id,
        )
        cached = self._cache.get(request_cache_key)
        if cached is not None:
            return cached
        snapshot = self.snapshot_service.get(topology_snapshot_id)
        if snapshot is None:
            raise GroupKnowledgeAccessError("workspace group snapshot not found")
        if requesting_workspace_id not in snapshot.role_map:
            raise GroupKnowledgeAccessError(
                "requesting workspace is outside the admitted group snapshot"
            )
        self.group_facade.get_group(
            snapshot.group_id,
            actor_user_id=actor_user_id,
            allowed_group_ids=allowed_group_ids,
        )
        items = self.memory_store.list_for_context(
            context_type="group",
            context_id=snapshot.group_id,
            lifecycle_statuses=["active", "candidate"],
            verification_statuses=["verified", "observed", "unverified", "challenged"],
            limit=min(max(limit, 1), 200),
        )
        visible = [
            item
            for item in items
            if self.view_policy.allows(item, agent_role=agent_role)
        ]
        canonical = [
            {
                "id": item.id,
                "stable_subject_key": (
                    (item.metadata or {}).get("stable_subject_key")
                    or f"{item.subject_type}:{item.subject_id}"
                ),
                "updated_at": item.updated_at.isoformat(),
                "lifecycle_status": item.lifecycle_status,
                "verification_status": item.verification_status,
            }
            for item in visible
        ]
        canonical.sort(key=lambda item: (item["stable_subject_key"], item["id"]))
        revision_hash = hashlib.sha256(
            json.dumps(
                canonical,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        packet = GroupKnowledgePacket(
            group_id=snapshot.group_id,
            topology_snapshot_id=snapshot.id,
            topology_revision=snapshot.group_revision,
            requesting_workspace_id=requesting_workspace_id,
            agent_role=agent_role,
            memory_revision_hash=revision_hash,
            entries=[
                GroupKnowledgePacketEntry(
                    memory_item_id=item.id,
                    stable_subject_key=(
                        (item.metadata or {}).get("stable_subject_key")
                        or f"{item.subject_type}:{item.subject_id}"
                    ),
                    title=item.title,
                    claim=item.claim,
                    summary=item.summary,
                    lifecycle_status=item.lifecycle_status,
                    verification_status=item.verification_status,
                    confidence=item.confidence,
                )
                for item in visible
            ],
        )
        self._cache[request_cache_key] = packet
        return packet
