"""Meeting close writeback orchestration for canonical memory rollout."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from backend.app.models.memory_contract import (
    MemoryEvidenceLink,
    MemoryItem,
    MemoryKind,
    MemoryUpdateMode,
    MemoryVersion,
)
from backend.app.models.personal_governance.session_digest import SessionDigest
from backend.app.services.memory.writeback.legacy_governance_projection_adapter import (
    LegacyGovernanceProjectionAdapter,
)
from backend.app.services.memory.writeback.legacy_metadata_memory_projection_adapter import (
    LegacyMetadataMemoryProjectionAdapter,
)
from backend.app.services.stores.postgres.memory_evidence_link_store import (
    MemoryEvidenceLinkStore,
)
from backend.app.services.stores.postgres.memory_item_store import MemoryItemStore
from backend.app.services.stores.postgres.memory_version_store import MemoryVersionStore
from backend.app.services.stores.postgres.memory_writeback_run_store import (
    MemoryWritebackRunStore,
)
from backend.app.services.stores.postgres.session_digest_store import SessionDigestStore

logger = logging.getLogger(__name__)


class MeetingMemoryWritebackOrchestrator:
    """Drive meeting-close canonical writeback while preserving legacy extraction."""

    def __init__(
        self,
        *,
        run_store: Optional[MemoryWritebackRunStore] = None,
        digest_store: Optional[SessionDigestStore] = None,
        memory_item_store: Optional[MemoryItemStore] = None,
        memory_version_store: Optional[MemoryVersionStore] = None,
        evidence_link_store: Optional[MemoryEvidenceLinkStore] = None,
        legacy_projection_adapter: Optional[LegacyGovernanceProjectionAdapter] = None,
        metadata_projection_adapter: Optional[
            LegacyMetadataMemoryProjectionAdapter
        ] = None,
    ) -> None:
        self.run_store = run_store or MemoryWritebackRunStore()
        self.digest_store = digest_store or SessionDigestStore()
        self.memory_item_store = memory_item_store or MemoryItemStore()
        self.memory_version_store = memory_version_store or MemoryVersionStore()
        self.evidence_link_store = evidence_link_store or MemoryEvidenceLinkStore()
        self.legacy_projection_adapter = (
            legacy_projection_adapter or LegacyGovernanceProjectionAdapter()
        )
        self.metadata_projection_adapter = (
            metadata_projection_adapter or LegacyMetadataMemoryProjectionAdapter()
        )

    def run_for_closed_session(
        self,
        *,
        session: Any,
        workspace: Any,
        profile_id: str,
    ) -> Dict[str, Any]:
        session_id = getattr(session, "id", "")
        idempotency_key = f"meeting_close:{session_id}"
        run, created = self.run_store.get_or_create(
            run_type="meeting_close",
            source_scope="meeting",
            source_id=session_id,
            idempotency_key=idempotency_key,
            metadata={
                "workspace_id": getattr(session, "workspace_id", ""),
                "project_id": getattr(session, "project_id", ""),
                "profile_id": profile_id,
            },
        )

        if not created and run.status == "completed":
            digest = self.digest_store.get_by_source("meeting", session_id)
            item = self.memory_item_store.find_by_subject(
                kind=MemoryKind.SESSION_EPISODE.value,
                subject_type="meeting_session",
                subject_id=session_id,
                context_type="workspace",
                context_id=getattr(session, "workspace_id", ""),
            )
            return {
                "run": run,
                "created": False,
                "digest": digest,
                "memory_item": item,
                "legacy_extraction_triggered": bool(
                    (run.summary or {}).get("legacy_extraction_triggered")
                ),
            }

        try:
            self.run_store.mark_stage(
                run.id,
                last_stage="digest",
                summary_update={"meeting_session_id": session_id},
            )
            digest = self.digest_store.get_by_source("meeting", session_id)
            digest_created = False
            if not digest:
                digest = SessionDigest.from_meeting_session(
                    session=session,
                    workspace=workspace,
                    profile_id=profile_id,
                )
                self.digest_store.create(digest)
                digest_created = True

            self.run_store.mark_stage(
                run.id,
                last_stage="canonical_item",
                summary_update={
                    "digest_id": digest.id,
                    "digest_created": digest_created,
                },
            )

            item = self.memory_item_store.find_by_subject(
                kind=MemoryKind.SESSION_EPISODE.value,
                subject_type="meeting_session",
                subject_id=session_id,
                context_type="workspace",
                context_id=getattr(session, "workspace_id", ""),
            )
            item_created = False
            if not item:
                item = MemoryItem.from_session_digest(digest, run_id=run.id)
                self.memory_item_store.create(item)
                self.memory_version_store.create(MemoryVersion.initial_from_item(item))
                item_created = True

            evidence_created = False
            if not self.evidence_link_store.exists(
                memory_item_id=item.id,
                evidence_type="session_digest",
                evidence_id=digest.id,
                link_role="derived_from",
            ):
                link = MemoryEvidenceLink.from_session_digest(item.id, digest)
                self.evidence_link_store.create(link)
                evidence_created = True

            self.run_store.mark_stage(
                run.id,
                last_stage="legacy_projection",
                summary_update={
                    "memory_item_id": item.id,
                    "memory_item_created": item_created,
                    "evidence_link_created": evidence_created,
                },
            )

            legacy_triggered, legacy_error = self._safe_dispatch_legacy_projection(
                digest,
                session_id,
                source_memory_item_id=item.id,
                source_writeback_run_id=run.id,
            )
            metadata_triggered, metadata_error = (
                self._safe_dispatch_metadata_projection(
                    digest,
                    session_id,
                    source_memory_item_id=item.id,
                    source_writeback_run_id=run.id,
                )
            )

            completed_run = self.run_store.mark_completed(
                run.id,
                summary={
                    "digest_id": digest.id,
                    "memory_item_id": item.id,
                    "legacy_extraction_triggered": legacy_triggered,
                    "legacy_extraction_error": legacy_error,
                    "legacy_metadata_projection_triggered": metadata_triggered,
                    "legacy_metadata_projection_error": metadata_error,
                },
                update_mode_summary={MemoryUpdateMode.APPEND.value: 1},
                last_stage="completed",
            )

            logger.info(
                "Meeting memory writeback completed for session %s (run=%s item=%s)",
                session_id,
                run.id,
                item.id,
            )
            return {
                "run": completed_run or run,
                "created": created,
                "digest": digest,
                "memory_item": item,
                "legacy_extraction_triggered": legacy_triggered,
                "legacy_metadata_projection_triggered": metadata_triggered,
            }
        except Exception as exc:
            self.run_store.mark_failed(
                run.id,
                error_detail=str(exc),
                summary={"meeting_session_id": session_id},
                last_stage="failed",
            )
            raise

    def _safe_dispatch_legacy_projection(
        self,
        digest: SessionDigest,
        session_id: str,
        *,
        source_memory_item_id: str,
        source_writeback_run_id: str,
    ) -> tuple[bool, Optional[str]]:
        try:
            self.legacy_projection_adapter.dispatch_digest_projection(
                digest,
                session_id,
                source_memory_item_id=source_memory_item_id,
                source_writeback_run_id=source_writeback_run_id,
            )
            return True, None
        except Exception as exc:
            logger.warning(
                "Legacy extraction dispatch failed for %s: %s",
                session_id,
                exc,
            )
            return False, str(exc)

    def _safe_dispatch_metadata_projection(
        self,
        digest: SessionDigest,
        session_id: str,
        *,
        source_memory_item_id: str,
        source_writeback_run_id: str,
    ) -> tuple[bool, Optional[str]]:
        try:
            self.metadata_projection_adapter.dispatch_digest_projection(
                digest,
                source_memory_item_id=source_memory_item_id,
                source_writeback_run_id=source_writeback_run_id,
            )
            return True, None
        except Exception as exc:
            logger.warning(
                "Legacy metadata projection failed for %s: %s",
                session_id,
                exc,
            )
            return False, str(exc)
