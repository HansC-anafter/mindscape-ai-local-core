"""
MetaMeetingSession — Extended meeting session for Personal Governance.

ADR-001 v2 Phase 3: Meta Meeting State Machine.

Extends the standard MeetingSession lifecycle with:
  - MetaScope binding (which workspaces/projects/time-window to review)
  - Digest aggregation (which session_digests feed this meeting)
  - Writeback tracking (WRITEBACK_PENDING → ARCHIVED)

State Machine:
  DRAFT → PREPARED → ACTIVE → CLOSING → CLOSED
                                           ↓
                                 WRITEBACK_PENDING → ARCHIVED
                                           ↓ (failure)
                                      WRITEBACK_FAILED
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MetaMeetingStatus(str, Enum):
    """Extended lifecycle for meta governance meetings."""

    # Standard meeting phases
    DRAFT = "draft"  # Scope selection in progress
    PREPARED = "prepared"  # Scope frozen, digests aggregated
    ACTIVE = "active"  # LLM deliberation running
    CLOSING = "closing"  # Generating minutes + action items
    CLOSED = "closed"  # Deliberation done, ready for writeback

    # Writeback phases (unique to meta meetings)
    WRITEBACK_PENDING = "writeback_pending"  # Processing outputs through routing table
    WRITEBACK_FAILED = "writeback_failed"  # One or more writebacks failed
    ARCHIVED = "archived"  # All writebacks complete, session archived


# Valid state transitions
VALID_TRANSITIONS: Dict[MetaMeetingStatus, List[MetaMeetingStatus]] = {
    MetaMeetingStatus.DRAFT: [MetaMeetingStatus.PREPARED],
    MetaMeetingStatus.PREPARED: [MetaMeetingStatus.ACTIVE],
    MetaMeetingStatus.ACTIVE: [MetaMeetingStatus.CLOSING],
    MetaMeetingStatus.CLOSING: [MetaMeetingStatus.CLOSED],
    MetaMeetingStatus.CLOSED: [MetaMeetingStatus.WRITEBACK_PENDING],
    MetaMeetingStatus.WRITEBACK_PENDING: [
        MetaMeetingStatus.ARCHIVED,
        MetaMeetingStatus.WRITEBACK_FAILED,
    ],
    MetaMeetingStatus.WRITEBACK_FAILED: [
        MetaMeetingStatus.WRITEBACK_PENDING,  # retry
        MetaMeetingStatus.ARCHIVED,  # force-close
    ],
    MetaMeetingStatus.ARCHIVED: [],  # terminal
}


@dataclass
class MetaMeetingSession:
    """A personal governance meta meeting session.

    Unlike workspace meetings which focus on a single project/workspace,
    meta meetings operate at the personal governance layer — reviewing
    signals across workspaces, updating self-model, and iterating goals.
    """

    # --- Identity ---
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    owner_profile_id: str = ""
    status: MetaMeetingStatus = MetaMeetingStatus.DRAFT

    # --- Scope (L4: MetaScope binding) ---
    meta_scope_id: Optional[str] = None  # FK → meta_scopes.id
    scope_snapshot: Dict[str, Any] = field(default_factory=dict)  # frozen at PREPARED

    # --- Digest Aggregation ---
    digest_ids: List[str] = field(default_factory=list)  # session_digest IDs fed in
    digest_count: int = 0
    digest_time_window_start: Optional[datetime] = None
    digest_time_window_end: Optional[datetime] = None

    # --- Meeting Content (mirrors MeetingSession) ---
    agenda: List[str] = field(default_factory=list)
    success_criteria: List[str] = field(default_factory=list)
    minutes_md: str = ""
    action_items: List[Dict[str, Any]] = field(default_factory=list)
    decisions: List[Dict[str, Any]] = field(default_factory=list)
    round_count: int = 0
    max_rounds: int = 5

    # --- Writeback Tracking ---
    writeback_receipts: List[str] = field(default_factory=list)  # receipt IDs
    writeback_summary: Dict[str, int] = field(default_factory=dict)
    # e.g. {"goals_created": 2, "knowledge_created": 3, "dispatched": 1, "skipped": 4}

    # --- Timestamps ---
    created_at: datetime = field(default_factory=_utc_now)
    prepared_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    archived_at: Optional[datetime] = None

    # --- Metadata ---
    metadata: Dict[str, Any] = field(default_factory=dict)

    # -----------------------------------------------------------------
    # State machine transitions
    # -----------------------------------------------------------------

    def transition_to(self, target: MetaMeetingStatus) -> None:
        """Transition to target status with validation."""
        valid = VALID_TRANSITIONS.get(self.status, [])
        if target not in valid:
            raise ValueError(
                f"Invalid transition: {self.status.value} → {target.value}. "
                f"Valid: {[s.value for s in valid]}"
            )
        self.status = target

    def prepare(self, scope_snapshot: Dict[str, Any], digest_ids: List[str]) -> None:
        """Freeze scope and aggregate digests. DRAFT → PREPARED."""
        self.transition_to(MetaMeetingStatus.PREPARED)
        self.scope_snapshot = scope_snapshot
        self.digest_ids = digest_ids
        self.digest_count = len(digest_ids)
        self.prepared_at = _utc_now()

    def start(self) -> None:
        """Begin deliberation. PREPARED → ACTIVE."""
        self.transition_to(MetaMeetingStatus.ACTIVE)
        self.started_at = _utc_now()

    def begin_closing(self) -> None:
        """Begin closing phase. ACTIVE → CLOSING."""
        self.transition_to(MetaMeetingStatus.CLOSING)

    def close(
        self, minutes_md: str, action_items: List[Dict], decisions: List[Dict]
    ) -> None:
        """Close deliberation with outputs. CLOSING → CLOSED."""
        self.transition_to(MetaMeetingStatus.CLOSED)
        self.minutes_md = minutes_md
        self.action_items = action_items
        self.decisions = decisions
        self.closed_at = _utc_now()

    def begin_writeback(self) -> None:
        """Start writeback processing. CLOSED → WRITEBACK_PENDING."""
        self.transition_to(MetaMeetingStatus.WRITEBACK_PENDING)

    def complete_writeback(
        self, summary: Dict[str, int], receipt_ids: List[str]
    ) -> None:
        """All writebacks done. WRITEBACK_PENDING → ARCHIVED."""
        self.writeback_summary = summary
        self.writeback_receipts = receipt_ids
        self.transition_to(MetaMeetingStatus.ARCHIVED)
        self.archived_at = _utc_now()

    def fail_writeback(self, error: str) -> None:
        """Writeback failed. WRITEBACK_PENDING → WRITEBACK_FAILED."""
        self.metadata["writeback_error"] = error
        self.transition_to(MetaMeetingStatus.WRITEBACK_FAILED)

    # -----------------------------------------------------------------
    # Factory
    # -----------------------------------------------------------------

    @staticmethod
    def new(
        owner_profile_id: str,
        meta_scope_id: Optional[str] = None,
        agenda: Optional[List[str]] = None,
        max_rounds: int = 5,
    ) -> "MetaMeetingSession":
        return MetaMeetingSession(
            owner_profile_id=owner_profile_id,
            meta_scope_id=meta_scope_id,
            agenda=list(agenda or []),
            max_rounds=max_rounds,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "owner_profile_id": self.owner_profile_id,
            "status": self.status.value,
            "meta_scope_id": self.meta_scope_id,
            "scope_snapshot": self.scope_snapshot,
            "digest_ids": self.digest_ids,
            "digest_count": self.digest_count,
            "agenda": self.agenda,
            "minutes_md": self.minutes_md[:500] if self.minutes_md else "",
            "action_items": self.action_items,
            "decisions": self.decisions,
            "round_count": self.round_count,
            "writeback_summary": self.writeback_summary,
            "created_at": self.created_at.isoformat(),
            "prepared_at": self.prepared_at.isoformat() if self.prepared_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
            "archived_at": self.archived_at.isoformat() if self.archived_at else None,
        }
