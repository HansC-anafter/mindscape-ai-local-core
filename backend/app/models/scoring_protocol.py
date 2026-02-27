"""
L3 ScoringProtocol — abstract interface for convergence scoring.

Defines the Protocol that both L2 rule-based and L3 semantic scorers
must implement, enabling swap without changing callers.
"""

from typing import List, Protocol, runtime_checkable

from backend.app.models.state_vector import ProgressScore, ViolationScore
from backend.app.models.meeting_extract import MeetingExtract
from backend.app.models.goal_set import GoalSet


@runtime_checkable
class GoalAlignmentScorerProtocol(Protocol):
    """Score how well extract items align with goal clauses."""

    def score(
        self,
        extract: MeetingExtract,
        goal_set: GoalSet,
    ) -> List[ProgressScore]:
        """Return ProgressScores for each (item, clause) pair."""
        ...


@runtime_checkable
class ViolationScorerProtocol(Protocol):
    """Score whether extract items violate negative constraints."""

    def score(
        self,
        extract: MeetingExtract,
        goal_set: GoalSet,
    ) -> List[ViolationScore]:
        """Return ViolationScores for each detected violation."""
        ...


@runtime_checkable
class DriftScorerProtocol(Protocol):
    """Score persona/lens drift between consecutive sessions."""

    def score(
        self,
        current_lens_hash: str,
        previous_lens_hash: str,
    ) -> float:
        """Return drift score 0.0 (stable) to 1.0 (diverged)."""
        ...
