"""
L3 DriftScorer — Drift(P_t, P_{t-1}) computation.

Measures persona/lens drift by analyzing the LensPatch chain.
Higher drift indicates the meeting is shifting persona significantly.

Implements DriftScorerProtocol.
"""

import logging
from typing import List, Optional

from backend.app.models.lens_patch import LensPatch

logger = logging.getLogger(__name__)

# Maximum number of delta dimensions considered "normal"
_MAX_EXPECTED_DIMS = 10


class DriftScorer:
    """Score persona drift from LensPatch chain.

    Implements DriftScorerProtocol.
    L2 strategy: normalized delta_magnitude count.
    L3 upgrade: embedding-space distance between lens versions.
    """

    def __init__(self, max_dims: int = _MAX_EXPECTED_DIMS):
        self.max_dims = max_dims

    def score(
        self,
        current_lens_hash: str,
        previous_lens_hash: str,
    ) -> float:
        """Score drift from lens hash comparison.

        Simple binary: 0.0 if same, 0.5 if different (no patch data).
        Use score_from_patch for richer scoring.
        """
        if current_lens_hash == previous_lens_hash:
            return 0.0
        return 0.5  # Changed but magnitude unknown

    def score_from_patch(self, patch: Optional[LensPatch]) -> float:
        """Score drift from a LensPatch (richer signal).

        Normalized: delta_magnitude / max_dims, clamped to [0, 1].
        """
        if not patch:
            return 0.0
        magnitude = patch.delta_magnitude
        if magnitude == 0:
            return 0.0
        return min(magnitude / max(1, self.max_dims), 1.0)

    def score_from_patches(self, patches: List[LensPatch]) -> float:
        """Score drift from multiple patches (e.g. accumulated session drift)."""
        if not patches:
            return 0.0
        total_magnitude = sum(p.delta_magnitude for p in patches)
        return min(total_magnitude / max(1, self.max_dims), 1.0)
