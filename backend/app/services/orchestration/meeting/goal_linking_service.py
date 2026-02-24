"""
Goal linking service — MeetingExtract items to GoalSet clause association.

Links MeetingExtractItems to GoalClauses via text similarity or
keyword matching, populating the goal_clause_ids field for
L3 Progress(X, G) = sum(sim(x_i, g_j)) computation.

Matches model contracts:
  - GoalClause.category (GoalCategory enum: what/how/not/metric)
  - MeetingExtractItem.goal_clause_ids (List[str])

Pipeline: MeetingExtract -> GoalLinking -> enriched extract items
"""

import logging
import re
from typing import List, Optional

from backend.app.models.goal_set import GoalSet, GoalClause
from backend.app.models.meeting_extract import MeetingExtract, MeetingExtractItem

logger = logging.getLogger(__name__)

# Common stop words for keyword matching
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


class GoalLinkingService:
    """Link extract items to goal clauses.

    L2 uses keyword-based matching. L3 replaces with embedding similarity
    without changing the interface (per invariant #5: L2 Scorer = Protocol).

    Usage:
        service = GoalLinkingService()
        enriched = service.link_extract_to_goals(extract, goal_set)
        # enriched items now have goal_clause_ids populated
    """

    def link_extract_to_goals(
        self,
        extract: MeetingExtract,
        goal_set: Optional[GoalSet],
    ) -> MeetingExtract:
        """Link extract items to goal clauses via keyword matching.

        Args:
            extract: MeetingExtract with items to link.
            goal_set: GoalSet with clauses to match against.

        Returns:
            Same MeetingExtract with goal_clause_ids populated on items.
        """
        if not goal_set or not goal_set.clauses:
            logger.debug("No goal set or clauses to link against")
            return extract

        linked_count = 0
        for item in extract.items:
            matched_ids = self._find_matching_clauses(item, goal_set.clauses)
            if matched_ids:
                item.goal_clause_ids = matched_ids
                linked_count += 1

        logger.info(
            "Linked %d/%d extract items to goal clauses (goal_set=%s)",
            linked_count,
            len(extract.items),
            goal_set.id,
        )

        return extract

    def _find_matching_clauses(
        self,
        item: MeetingExtractItem,
        clauses: List[GoalClause],
    ) -> List[str]:
        """Find goal clauses matching an extract item.

        L2 strategy: keyword overlap scoring (Jaccard-like).
        L3 upgrade path: replace with embedding cosine similarity.
        """
        item_words = set(self._tokenize(item.content))
        if not item_words:
            return []

        matches = []
        for clause in clauses:
            clause_words = set(self._tokenize(clause.text))
            if not clause_words:
                continue

            overlap = len(item_words & clause_words)
            union_size = len(item_words | clause_words)
            if union_size > 0 and overlap / union_size >= 0.15:
                matches.append(clause.id)

        return matches

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """Simple word tokenization for keyword matching."""
        # Lowercase, split on non-alphanumeric, filter short tokens + CJK
        words = re.findall(r"[a-z0-9\u4e00-\u9fff]{2,}", text.lower())
        return [w for w in words if w not in _STOP_WORDS]
