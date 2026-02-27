"""
Lens Patch — versioned persona/lens update proposal.

Each patch represents a proposed change to a MindLensInstance,
produced by a meeting session. Patches form a version chain:

    LensInstance v1 -> Patch_A (proposed) -> v2 (approved) -> Patch_B -> v3

L3 uses the patch chain to compute Drift(P_t, P_{t-1}):
- delta magnitude = persona shift per meeting
- rollback_to = automatic recovery when V(s) rises
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class PatchStatus(str, Enum):
    """Lifecycle status of a lens patch."""

    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    ROLLED_BACK = "rolled_back"


@dataclass
class LensPatch:
    """
    A proposed change to a MindLensInstance.

    Produced at meeting close. Contains:
    - delta: which dimension values changed and how
    - evidence_refs: supporting evidence for the change
    - confidence: how confident the system is about the change
    - rollback_to: previous snapshot for recovery
    """

    id: str
    lens_id: str
    meeting_session_id: str
    delta: Dict[str, Any]  # {dimension_key: {before: ..., after: ...}}
    evidence_refs: List[str] = field(default_factory=list)
    confidence: float = 0.0  # 0.0 - 1.0
    status: PatchStatus = PatchStatus.PROPOSED
    rollback_to: Optional[str] = None  # Previous lens snapshot ID
    lens_version_before: int = 0
    lens_version_after: Optional[int] = None
    approved_by: Optional[str] = None  # "system" | "user" | agent_id
    rejection_reason: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: Optional[datetime] = None

    @staticmethod
    def new(
        lens_id: str,
        meeting_session_id: str,
        delta: Dict[str, Any],
        evidence_refs: Optional[List[str]] = None,
        confidence: float = 0.0,
        lens_version_before: int = 0,
        rollback_to: Optional[str] = None,
    ) -> "LensPatch":
        return LensPatch(
            id=str(uuid.uuid4()),
            lens_id=lens_id,
            meeting_session_id=meeting_session_id,
            delta=delta,
            evidence_refs=evidence_refs or [],
            confidence=confidence,
            lens_version_before=lens_version_before,
            rollback_to=rollback_to,
        )

    def approve(
        self, approved_by: str = "system", version_after: Optional[int] = None
    ) -> None:
        """Approve this patch (apply to lens)."""
        self.status = PatchStatus.APPROVED
        self.approved_by = approved_by
        self.lens_version_after = version_after or (self.lens_version_before + 1)
        self.resolved_at = datetime.now(timezone.utc)

    def reject(self, reason: Optional[str] = None) -> None:
        """Reject this patch (do not apply)."""
        self.status = PatchStatus.REJECTED
        self.rejection_reason = reason
        self.resolved_at = datetime.now(timezone.utc)

    def rollback(self) -> None:
        """Mark this patch as rolled back."""
        self.status = PatchStatus.ROLLED_BACK
        self.resolved_at = datetime.now(timezone.utc)

    @property
    def is_pending(self) -> bool:
        return self.status == PatchStatus.PROPOSED

    @property
    def delta_magnitude(self) -> int:
        """Number of dimensions changed — simple drift proxy for L2."""
        return len(self.delta)

    @property
    def has_evidence(self) -> bool:
        return len(self.evidence_refs) > 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "lens_id": self.lens_id,
            "meeting_session_id": self.meeting_session_id,
            "delta": self.delta,
            "evidence_refs": self.evidence_refs,
            "confidence": self.confidence,
            "status": (
                self.status.value
                if isinstance(self.status, PatchStatus)
                else self.status
            ),
            "rollback_to": self.rollback_to,
            "lens_version_before": self.lens_version_before,
            "lens_version_after": self.lens_version_after,
            "approved_by": self.approved_by,
            "rejection_reason": self.rejection_reason,
            "delta_magnitude": self.delta_magnitude,
            "has_evidence": self.has_evidence,
            "is_pending": self.is_pending,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LensPatch":
        status = data.get("status", "proposed")
        if isinstance(status, str):
            status = PatchStatus(status)
        created = data.get("created_at")
        if isinstance(created, str):
            created = datetime.fromisoformat(created)
        resolved = data.get("resolved_at")
        if isinstance(resolved, str):
            resolved = datetime.fromisoformat(resolved)
        return cls(
            id=data["id"],
            lens_id=data["lens_id"],
            meeting_session_id=data["meeting_session_id"],
            delta=data.get("delta", {}),
            evidence_refs=data.get("evidence_refs", []),
            confidence=data.get("confidence", 0.0),
            status=status,
            rollback_to=data.get("rollback_to"),
            lens_version_before=data.get("lens_version_before", 0),
            lens_version_after=data.get("lens_version_after"),
            approved_by=data.get("approved_by"),
            rejection_reason=data.get("rejection_reason"),
            metadata=data.get("metadata", {}),
            created_at=created or datetime.now(timezone.utc),
            resolved_at=resolved,
        )
