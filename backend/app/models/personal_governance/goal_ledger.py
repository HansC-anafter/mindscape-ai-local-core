"""
GoalLedgerEntry — L3 goal tracking with transaction-log semantics.

Lives in mindscape_core DB (not vectors) — it's a governance record,
not a retrieval index. Supports the writeback policy's cooldown rules.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class GoalStatus(str, Enum):
    """Goal lifecycle — cannot skip stages (enforced by transition rules)."""

    CANDIDATE = "candidate"  # just extracted, unconfirmed
    PENDING_CONFIRMATION = "pending_confirmation"  # awaiting user confirm
    ACTIVE = "active"  # user-confirmed, actively tracked
    ACHIEVED = "achieved"  # goal reached
    DEPRECATED = "deprecated"  # explicitly retired
    STALE = "stale"  # no mention in 90+ days

    # --- Transition rules ---
    # candidate → pending_confirmation → active → achieved | deprecated
    # any → stale (auto, after 90 days no mention)
    # stale → active (if re-mentioned and user confirms)


VALID_TRANSITIONS = {
    GoalStatus.CANDIDATE: {GoalStatus.PENDING_CONFIRMATION, GoalStatus.DEPRECATED},
    GoalStatus.PENDING_CONFIRMATION: {GoalStatus.ACTIVE, GoalStatus.DEPRECATED},
    GoalStatus.ACTIVE: {GoalStatus.ACHIEVED, GoalStatus.DEPRECATED, GoalStatus.STALE},
    GoalStatus.STALE: {GoalStatus.ACTIVE, GoalStatus.DEPRECATED},
    GoalStatus.ACHIEVED: {GoalStatus.DEPRECATED},  # achieved goals can only be archived
    GoalStatus.DEPRECATED: set(),  # terminal
}


@dataclass
class GoalLedgerEntry:
    """A single goal entry in the personal governance ledger."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    owner_profile_id: str = ""
    title: str = ""
    description: str = ""
    status: str = GoalStatus.CANDIDATE.value
    horizon: str = "open-ended"  # "week" | "quarter" | "year" | "open-ended"

    # --- Provenance ---
    source_digest_ids: List[str] = field(default_factory=list)
    source_session_ids: List[str] = field(default_factory=list)
    related_knowledge_ids: List[str] = field(default_factory=list)

    # --- Cooldown ---
    last_updated_at: datetime = field(default_factory=_utc_now)
    MIN_UPDATE_INTERVAL_DAYS: int = 7  # writeback policy: same goal ≥ 7 days apart
    update_count: int = 0

    # --- Temporal ---
    created_at: datetime = field(default_factory=_utc_now)
    last_mentioned_at: Optional[datetime] = None  # for stale detection
    confirmed_at: Optional[datetime] = None

    # --- Metadata ---
    metadata: Dict[str, Any] = field(default_factory=dict)

    def can_transition_to(self, target: GoalStatus) -> bool:
        """Check if transition is valid per state machine rules."""
        current = GoalStatus(self.status)
        return target in VALID_TRANSITIONS.get(current, set())

    def transition_to(self, target: GoalStatus, reason: str = "") -> None:
        """Perform a validated state transition."""
        if not self.can_transition_to(target):
            raise ValueError(
                f"Invalid transition: {self.status} → {target.value}. "
                f"Valid targets: {[t.value for t in VALID_TRANSITIONS.get(GoalStatus(self.status), set())]}"
            )
        self.metadata.setdefault("transition_log", []).append(
            {
                "from": self.status,
                "to": target.value,
                "reason": reason,
                "at": _utc_now().isoformat(),
            }
        )
        self.status = target.value
        self.last_updated_at = _utc_now()
        self.update_count += 1
        if target == GoalStatus.ACTIVE:
            self.confirmed_at = _utc_now()

    def is_cooldown_active(self) -> bool:
        """Check if the 7-day cooldown is still active."""
        elapsed = (_utc_now() - self.last_updated_at).days
        return elapsed < self.MIN_UPDATE_INTERVAL_DAYS

    def record_mention(self) -> None:
        """Record that this goal was mentioned in a session."""
        self.last_mentioned_at = _utc_now()
