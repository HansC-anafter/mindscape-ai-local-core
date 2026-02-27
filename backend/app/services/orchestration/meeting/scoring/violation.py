"""
L3 ViolationScorer — Violation(X_t, G_not) computation.

Scores whether MeetingExtract items violate GoalSet NOT clauses
(prohibitions, anti-patterns, taboos).

Implements ViolationScorerProtocol.
"""

import logging
from typing import List

from backend.app.models.goal_set import GoalSet
from backend.app.models.meeting_extract import MeetingExtract
from backend.app.models.state_vector import ViolationScore
from backend.app.services.orchestration.meeting.scoring.goal_alignment import (
    _keyword_similarity,
    _cosine_similarity,
)

logger = logging.getLogger(__name__)


class ViolationScorer:
    """Score extract items against NOT goal clauses.

    Implements ViolationScorerProtocol.
    High similarity to a NOT clause = violation detected.
    """

    def __init__(self, threshold: float = 0.15):
        """Args:
        threshold: Minimum similarity to count as violation.
        """
        self.threshold = threshold

    def score(
        self,
        extract: MeetingExtract,
        goal_set: GoalSet,
    ) -> List[ViolationScore]:
        """Return ViolationScores for each detected violation."""
        if not goal_set or not goal_set.goal_not:
            return []

        violations: List[ViolationScore] = []
        for item in extract.items:
            for clause in goal_set.goal_not:
                # L3: cosine if embeddings available
                item_embedding = getattr(item, "embedding", None)
                if clause.embedding and item_embedding:
                    sim = _cosine_similarity(item_embedding, clause.embedding)
                else:
                    sim = _keyword_similarity(item.content, clause.text)

                if sim >= self.threshold:
                    violations.append(
                        ViolationScore(
                            goal_clause_id=clause.id,
                            extract_item_id=item.id,
                            score=min(sim * clause.weight, 1.0),
                            violation_type="boundary",
                            detail=f"Item matches NOT clause: {clause.text[:80]}",
                        )
                    )

        if violations:
            logger.warning(
                "ViolationScorer: %d violations detected from %d items",
                len(violations),
                len(extract.items),
            )
        return violations
