"""
PersonalKnowledge — L3 self-model: curated personal mental assets.

Only stores items that have been through semantic extraction and represent
something about the user (goals, preferences, principles, patterns).
NOT a vector dump. Main table lives in mindscape_core DB;
embedding index lives in mindscape_vectors DB (dual-write).
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class KnowledgeType(str, Enum):
    """Taxonomy of personal knowledge entries."""

    GOAL = "goal"
    PREFERENCE = "preference"
    PRINCIPLE = "principle"
    PATTERN = "pattern"  # recurring behavior / theme
    CONSTRAINT = "constraint"  # recurring limitation
    ANTI_GOAL = "anti_goal"
    PROJECT_IDENTITY = "project_identity"  # long-term project commitment


class KnowledgeStatus(str, Enum):
    """Lifecycle status of a personal knowledge entry."""

    CANDIDATE = "candidate"  # LLM-extracted, unverified
    MIGRATED_UNVERIFIED = "migrated_unverified"  # from old mindscape_personal seeds
    PENDING_CONFIRMATION = "pending_confirmation"  # awaiting user review
    VERIFIED = "verified"  # user-confirmed
    STALE = "stale"  # 30+ days without re-verification
    DEPRECATED = "deprecated"  # explicitly retired (never hard-deleted)


@dataclass
class PersonalKnowledge:
    """A single curated personal knowledge entry (L3 self-model)."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    owner_profile_id: str = ""
    knowledge_type: str = KnowledgeType.PREFERENCE.value
    content: str = ""
    status: str = KnowledgeStatus.CANDIDATE.value

    # --- Provenance ---
    confidence: float = 0.5
    source_evidence: List[str] = field(default_factory=list)  # digest IDs, event IDs
    source_workspace_ids: List[str] = field(default_factory=list)

    # --- Temporal ---
    created_at: datetime = field(default_factory=_utc_now)
    last_verified_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None  # for auto-stale after 30d

    # --- Scope ---
    valid_scope: str = "global"  # "global" | workspace_id | project_id

    # --- Metadata ---
    metadata: Dict[str, Any] = field(default_factory=dict)

    def mark_verified(self) -> None:
        """User confirmed this knowledge entry."""
        self.status = KnowledgeStatus.VERIFIED.value
        self.last_verified_at = _utc_now()

    def mark_stale(self) -> None:
        """Auto-stale after 30 days without verification."""
        self.status = KnowledgeStatus.STALE.value

    def deprecate(self, reason: str = "") -> None:
        """Retire this entry (never hard-delete)."""
        self.status = KnowledgeStatus.DEPRECATED.value
        self.metadata["deprecated_reason"] = reason
        self.metadata["deprecated_at"] = _utc_now().isoformat()
