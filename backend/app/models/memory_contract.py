"""
Canonical memory contract models.

These dataclasses back the first governed-memory rollout slice:
`memory_items`, `memory_versions`, `memory_evidence_links`,
and `memory_writeback_runs`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

from backend.app.models.personal_governance.session_digest import SessionDigest


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MemoryLayer(str, Enum):
    PROCESS = "process"
    EPISODIC = "episodic"
    INTERFACE = "interface"
    CORE = "core"
    PROCEDURAL = "procedural"


class MemoryKind(str, Enum):
    SESSION_EPISODE = "session_episode"
    DECISION_EPISODE = "decision_episode"
    PATTERN_CANDIDATE = "pattern_candidate"
    CONTEXT_SIGNATURE = "context_signature"
    PREFERENCE = "preference"
    PRINCIPLE = "principle"
    PROCEDURAL_RULE = "procedural_rule"


class MemoryVerificationStatus(str, Enum):
    UNVERIFIED = "unverified"
    OBSERVED = "observed"
    VERIFIED = "verified"
    CHALLENGED = "challenged"
    REJECTED = "rejected"


class MemoryLifecycleStatus(str, Enum):
    CANDIDATE = "candidate"
    ACTIVE = "active"
    STALE = "stale"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"


class MemoryUpdateMode(str, Enum):
    APPEND = "append"
    REVISE = "revise"
    SUPERSEDE = "supersede"
    INVALIDATE = "invalidate"
    MERGE = "merge"


class MemoryEdgeType(str, Enum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    DERIVED_FROM = "derived_from"
    CONTINUES = "continues"
    SUPERSEDES = "supersedes"


class MemoryWritebackRunStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


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


@dataclass
class MemoryEvidenceLink:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    memory_item_id: str = ""
    evidence_type: str = ""
    evidence_id: str = ""
    link_role: str = "supports"
    excerpt: Optional[str] = None
    confidence: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utc_now)

    @staticmethod
    def from_session_digest(
        memory_item_id: str,
        digest: SessionDigest,
    ) -> "MemoryEvidenceLink":
        return MemoryEvidenceLink(
            memory_item_id=memory_item_id,
            evidence_type="session_digest",
            evidence_id=digest.id,
            link_role="derived_from",
            excerpt=_shorten(digest.summary_md.strip(), 280),
            confidence=0.9,
            metadata={
                "source_type": digest.source_type,
                "source_id": digest.source_id,
            },
        )


@dataclass
class MemoryEdge:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    from_memory_id: str = ""
    to_memory_id: str = ""
    edge_type: str = MemoryEdgeType.SUPPORTS.value
    weight: Optional[float] = None
    valid_from: datetime = field(default_factory=_utc_now)
    valid_to: Optional[datetime] = None
    evidence_strength: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utc_now)

    @staticmethod
    def supersedes(
        from_memory_id: str,
        to_memory_id: str,
        *,
        reason: str = "",
        run_id: Optional[str] = None,
    ) -> "MemoryEdge":
        metadata: Dict[str, Any] = {}
        if reason:
            metadata["reason"] = reason
        if run_id:
            metadata["source_writeback_run_id"] = run_id
        return MemoryEdge(
            from_memory_id=from_memory_id,
            to_memory_id=to_memory_id,
            edge_type=MemoryEdgeType.SUPERSEDES.value,
            evidence_strength=1.0,
            metadata=metadata,
        )


@dataclass
class MemoryWritebackRun:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    run_type: str = ""
    source_scope: str = ""
    source_id: str = ""
    status: str = MemoryWritebackRunStatus.RUNNING.value
    idempotency_key: str = ""
    update_mode_summary: Dict[str, Any] = field(default_factory=dict)
    started_at: datetime = field(default_factory=_utc_now)
    completed_at: Optional[datetime] = None
    summary: Dict[str, Any] = field(default_factory=dict)
    error_detail: Optional[str] = None
    last_stage: str = "created"
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)

    @staticmethod
    def new(
        *,
        run_type: str,
        source_scope: str,
        source_id: str,
        idempotency_key: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "MemoryWritebackRun":
        now = _utc_now()
        return MemoryWritebackRun(
            run_type=run_type,
            source_scope=source_scope,
            source_id=source_id,
            status=MemoryWritebackRunStatus.RUNNING.value,
            idempotency_key=idempotency_key,
            metadata=dict(metadata or {}),
            created_at=now,
            started_at=now,
            updated_at=now,
        )


def _shorten(value: str, limit: int) -> str:
    if not value:
        return ""
    value = " ".join(value.split())
    return value[:limit]


def _build_meeting_fallback_summary(digest: SessionDigest) -> str:
    action_count = len(digest.actions or [])
    decision_count = len(digest.decisions or [])
    return (
        f"Closed meeting {digest.source_id} with "
        f"{action_count} action items and {decision_count} decisions."
    )
