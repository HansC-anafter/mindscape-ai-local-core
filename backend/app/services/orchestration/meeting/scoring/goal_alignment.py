"""
L3 GoalAlignmentScorer — Progress(X_t, G) computation.

Scores how well MeetingExtract items align with GoalSet WHAT/HOW clauses.

L2 strategy: keyword overlap (Jaccard similarity)
L3 upgrade: cosine similarity on GoalClause.embedding (when available)

Implements GoalAlignmentScorerProtocol.
"""

import logging
import math
import re
from typing import List, Optional

from backend.app.models.goal_set import GoalCategory, GoalClause, GoalSet
from backend.app.models.meeting_extract import MeetingExtract, MeetingExtractItem
from backend.app.models.state_vector import ProgressScore

logger = logging.getLogger(__name__)

# Reuse the same stop words as GoalLinkingService
_STOP_WORDS = frozenset(
    {
        "the",
        "is",
        "at",
        "in",
        "on",
        "to",
        "of",
        "and",
        "or",
        "for",
        "this",
        "that",
        "with",
        "from",
        "are",
        "was",
        "were",
        "been",
        "have",
        "has",
        "had",
        "will",
        "would",
        "could",
        "should",
    }
)


def _tokenize(text: str) -> List[str]:
    """Simple word tokenization (shared with GoalLinkingService)."""
    words = re.findall(r"[a-z0-9\u4e00-\u9fff]{2,}", text.lower())
    return [w for w in words if w not in _STOP_WORDS]


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Cosine similarity between two vectors."""
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _keyword_similarity(text_a: str, text_b: str) -> float:
    """Jaccard-like keyword overlap score."""
    words_a = set(_tokenize(text_a))
    words_b = set(_tokenize(text_b))
    if not words_a or not words_b:
        return 0.0
    overlap = len(words_a & words_b)
    union = len(words_a | words_b)
    return overlap / union if union > 0 else 0.0


class GoalAlignmentScorer:
    """Score extract items against WHAT/HOW goal clauses.

    Implements GoalAlignmentScorerProtocol.
    Uses cosine similarity when embeddings are available,
    falls back to keyword overlap otherwise.
    """

    def score(
        self,
        extract: MeetingExtract,
        goal_set: GoalSet,
    ) -> List[ProgressScore]:
        """Return ProgressScores for each (item, clause) pair with nonzero alignment."""
        if not goal_set or not goal_set.clauses:
            return []

        # Score against WHAT + HOW clauses (positive goals)
        positive_clauses = goal_set.goal_what + goal_set.goal_how
        if not positive_clauses:
            return []

        scores: List[ProgressScore] = []
        for item in extract.items:
            for clause in positive_clauses:
                sim, method = self._compute_similarity(item, clause)
                if sim > 0.0:
                    evidence = getattr(item, "evidence_refs", []) or []
                    scores.append(
                        ProgressScore(
                            goal_clause_id=clause.id,
                            extract_item_id=item.id,
                            score=min(sim * clause.weight, 1.0),
                            method=method,
                            evidence_refs=evidence,
                        )
                    )

        logger.debug(
            "GoalAlignmentScorer: %d scores from %d items x %d clauses",
            len(scores),
            len(extract.items),
            len(positive_clauses),
        )
        return scores

    def _compute_similarity(
        self,
        item: MeetingExtractItem,
        clause: GoalClause,
    ) -> tuple:
        """Compute similarity between item and clause.

        Returns (score, method) tuple.
        """
        # L3 path: use embeddings when both are available
        item_embedding = getattr(item, "embedding", None)
        if clause.embedding and item_embedding:
            return _cosine_similarity(item_embedding, clause.embedding), "cosine"

        # L2 fallback: keyword overlap
        return _keyword_similarity(item.content, clause.text), "keyword"
