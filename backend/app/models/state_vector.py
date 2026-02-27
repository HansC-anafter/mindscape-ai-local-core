"""
L3 StateVector model — four-axis convergence state representation.

Tracks progress, evidence, risk, and drift for a meeting session,
with a computed Lyapunov stability metric and meeting mode.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class ProgressScore:
    """Score representing alignment of an extract item to a GoalClause."""

    goal_clause_id: str
    extract_item_id: str
    score: float  # 0.0 - 1.0
    method: str = "keyword"  # "keyword" | "cosine" | "llm"
    evidence_refs: List[str] = field(default_factory=list)

    @property
    def has_evidence(self) -> bool:
        return len(self.evidence_refs) > 0


@dataclass
class ViolationScore:
    """Score representing violation of a negative constraint (G_not)."""

    goal_clause_id: str
    extract_item_id: str
    score: float  # 0.0 - 1.0, higher = worse
    violation_type: str = "boundary"  # "boundary" | "budget" | "timeline"
    detail: str = ""


@dataclass
class StateVector:
    """Four-axis convergence state for a meeting session.

    Axes:
        progress: Goal alignment score (0=no progress, 1=fully aligned)
        evidence: Evidence quality score (0=no evidence, 1=fully backed)
        risk: Risk/violation score (0=no risk, 1=critical)
        drift: Persona/lens drift score (0=stable, 1=diverged)
    """

    id: str
    meeting_session_id: str
    workspace_id: str
    timestamp: datetime

    # Four convergence axes
    progress: float = 0.0
    evidence: float = 0.0
    risk: float = 0.0
    drift: float = 0.0

    # Stability metric
    lyapunov_v: float = 0.0

    # Meeting mode (explore/converge/deliver/debug)
    mode: str = "explore"

    # Optional fields (defaults after required fields)
    project_id: Optional[str] = None
    progress_scores: List[ProgressScore] = field(default_factory=list)
    violation_scores: List[ViolationScore] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @staticmethod
    def create(
        meeting_session_id: str,
        workspace_id: str,
        project_id: Optional[str] = None,
    ) -> "StateVector":
        """Factory: create a zero-state vector."""
        return StateVector(
            id=str(uuid.uuid4()),
            meeting_session_id=meeting_session_id,
            workspace_id=workspace_id,
            project_id=project_id,
            timestamp=datetime.now(timezone.utc),
        )

    def as_tuple(self) -> tuple:
        """Return the four axes as a tuple for computation."""
        return (self.progress, self.evidence, self.risk, self.drift)
