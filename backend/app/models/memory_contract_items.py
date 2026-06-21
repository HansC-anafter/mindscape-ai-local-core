"""Memory item and version contract models."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional

from .memory_contract_excerpts import _shorten
from .memory_contract_types import (
    MemoryKind,
    MemoryLayer,
    MemoryLifecycleStatus,
    MemoryUpdateMode,
    MemoryVerificationStatus,
    _utc_now,
)
from .personal_governance.session_digest import SessionDigest


@dataclass
class MemoryItem:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    kind: str = MemoryKind.SESSION_EPISODE.value
    layer: str = MemoryLayer.EPISODIC.value
    scope: str = "global"
    subject_type: str = ""
    subject_id: str = ""
    context_type: str = ""
    context_id: str = ""
    title: str = ""
    claim: str = ""
    summary: str = ""
    salience: float = 0.5
    confidence: float = 0.5
    verification_status: str = MemoryVerificationStatus.OBSERVED.value
    lifecycle_status: str = MemoryLifecycleStatus.CANDIDATE.value
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    observed_at: datetime = field(default_factory=_utc_now)
    last_confirmed_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    update_mode: Optional[str] = MemoryUpdateMode.APPEND.value
    supersedes_memory_id: Optional[str] = None
    created_by_pipeline: str = ""
    created_from_run_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)

    @staticmethod
    def from_session_digest(
        digest: SessionDigest,
        *,
        run_id: str,
        pipeline_name: str = "meeting_close_writeback_v1",
    ) -> "MemoryItem":
        summary = _shorten(digest.summary_md.strip(), 600)
        if not summary:
            summary = _build_meeting_fallback_summary(digest)

        title = f"Meeting episode {digest.source_id}".strip()
        claim = _shorten(digest.summary_md.strip(), 2000) or summary

        action_count = len(digest.actions or [])
        decision_count = len(digest.decisions or [])
        signal_weight = min(1.0, 0.35 + (action_count * 0.05) + (decision_count * 0.08))

        return MemoryItem(
            kind=MemoryKind.SESSION_EPISODE.value,
            layer=MemoryLayer.EPISODIC.value,
            scope="meeting",
            subject_type="meeting_session",
            subject_id=digest.source_id,
            context_type="workspace",
            context_id=(digest.workspace_refs[0] if digest.workspace_refs else ""),
            title=title,
            claim=claim,
            summary=summary,
            salience=signal_weight,
            confidence=0.85,
            verification_status=MemoryVerificationStatus.OBSERVED.value,
            lifecycle_status=MemoryLifecycleStatus.CANDIDATE.value,
            valid_from=digest.source_time_end or digest.created_at,
            observed_at=digest.source_time_end or digest.created_at,
            update_mode=MemoryUpdateMode.APPEND.value,
            created_by_pipeline=pipeline_name,
            created_from_run_id=run_id,
            metadata={
                "source_type": digest.source_type,
                "source_id": digest.source_id,
                "workspace_refs": list(digest.workspace_refs or []),
                "project_refs": list(digest.project_refs or []),
                "participant_count": len(digest.participants or []),
                "action_count": action_count,
                "decision_count": decision_count,
                "digest_id": digest.id,
            },
        )


def _build_meeting_fallback_summary(digest: SessionDigest) -> str:
    action_count = len(digest.actions or [])
    decision_count = len(digest.decisions or [])
    return (
        f"Closed meeting {digest.source_id} with "
        f"{action_count} action items and {decision_count} decisions."
    )


@dataclass
class MemoryVersion:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    memory_item_id: str = ""
    version_no: int = 1
    update_mode: str = MemoryUpdateMode.APPEND.value
    claim_snapshot: str = ""
    summary_snapshot: Optional[str] = None
    metadata_snapshot: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utc_now)
    created_from_run_id: Optional[str] = None

    @staticmethod
    def initial_from_item(item: MemoryItem) -> "MemoryVersion":
        return MemoryVersion(
            memory_item_id=item.id,
            version_no=1,
            update_mode=item.update_mode or MemoryUpdateMode.APPEND.value,
            claim_snapshot=item.claim,
            summary_snapshot=item.summary,
            metadata_snapshot=dict(item.metadata or {}),
            created_from_run_id=item.created_from_run_id,
        )
