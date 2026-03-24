"""Projection adapter from canonical memory rows to legacy metadata memory surfaces."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from backend.app.models.personal_governance.session_digest import SessionDigest
from backend.app.services.memory.member_profile_memory import (
    MemberProfileMemoryService,
)
from backend.app.services.memory.project_memory import ProjectMemoryService
from backend.app.services.memory.workspace_core_memory import (
    WorkspaceCoreMemoryService,
)
from backend.app.services.mindscape_store import MindscapeStore


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class LegacyMetadataMemoryProjectionAdapter:
    """Materialize canonical meeting memory into legacy metadata-memory surfaces."""

    def __init__(
        self,
        *,
        workspace_core_memory_service: Optional[WorkspaceCoreMemoryService] = None,
        project_memory_service: Optional[ProjectMemoryService] = None,
        member_profile_memory_service: Optional[MemberProfileMemoryService] = None,
        store: Optional[MindscapeStore] = None,
    ) -> None:
        resolved_store = store
        if (
            resolved_store is None
            and (
                workspace_core_memory_service is None
                or project_memory_service is None
                or member_profile_memory_service is None
            )
        ):
            resolved_store = MindscapeStore()
        self.workspace_core_memory_service = (
            workspace_core_memory_service
            or WorkspaceCoreMemoryService(resolved_store)
        )
        self.project_memory_service = (
            project_memory_service or ProjectMemoryService(resolved_store)
        )
        self.member_profile_memory_service = (
            member_profile_memory_service
            or MemberProfileMemoryService(resolved_store)
        )

    def dispatch_digest_projection(
        self,
        digest: SessionDigest,
        *,
        source_memory_item_id: str,
        source_writeback_run_id: str,
        projection_stage: str = "legacy_metadata_memory_v1",
    ) -> None:
        coroutine = self._project_digest(
            digest,
            source_memory_item_id=source_memory_item_id,
            source_writeback_run_id=source_writeback_run_id,
            projection_stage=projection_stage,
        )

        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(coroutine)
            return
        asyncio.run(coroutine)

    async def _project_digest(
        self,
        digest: SessionDigest,
        *,
        source_memory_item_id: str,
        source_writeback_run_id: str,
        projection_stage: str,
    ) -> None:
        episode = self._build_projection_episode(
            digest,
            source_memory_item_id=source_memory_item_id,
            source_writeback_run_id=source_writeback_run_id,
            projection_stage=projection_stage,
        )

        workspace_id = (digest.workspace_refs or [""])[0]
        if workspace_id:
            await self.workspace_core_memory_service.add_projected_episode(
                workspace_id,
                episode,
            )

        project_id = (digest.project_refs or [None])[0]
        if workspace_id and project_id:
            await self.project_memory_service.add_projected_episode(
                project_id,
                workspace_id,
                episode,
            )

        if workspace_id and digest.owner_profile_id:
            await self.member_profile_memory_service.add_projected_episode(
                digest.owner_profile_id,
                workspace_id,
                episode,
            )

    def _build_projection_episode(
        self,
        digest: SessionDigest,
        *,
        source_memory_item_id: str,
        source_writeback_run_id: str,
        projection_stage: str,
    ) -> Dict[str, Any]:
        summary = (digest.summary_md or "").strip().replace("\n", " ")
        summary = summary[:280]
        return {
            "title": f"Meeting episode {digest.source_id}",
            "summary": summary,
            "source_type": digest.source_type,
            "source_id": digest.source_id,
            "workspace_refs": list(digest.workspace_refs or []),
            "project_refs": list(digest.project_refs or []),
            "action_count": len(digest.actions or []),
            "decision_count": len(digest.decisions or []),
            "observed_at": (
                (digest.source_time_end or digest.created_at or _utc_now()).isoformat()
            ),
            "canonical_projection": {
                "source_memory_item_id": source_memory_item_id,
                "source_writeback_run_id": source_writeback_run_id,
                "source_digest_id": digest.id,
                "projection_stage": projection_stage,
                "projected_at": _utc_now().isoformat(),
            },
        }
