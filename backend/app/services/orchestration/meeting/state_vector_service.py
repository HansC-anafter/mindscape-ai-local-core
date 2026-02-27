"""
L3 StateVectorService — orchestrates scoring to compute s_t.

Pipeline: MeetingExtract + GoalSet + LensPatch → StateVector s_t

This service:
1. Runs GoalAlignmentScorer → progress axis
2. Runs ViolationScorer → risk axis
3. Runs DriftScorer → drift axis
4. Applies evidence gating → evidence axis
5. Computes Lyapunov V
6. Evaluates MeetingMode FSM transition
7. Persists StateVector + emits STATE_VECTOR_COMPUTED event
"""

import logging
from typing import List, Optional

from backend.app.models.goal_set import GoalSet
from backend.app.models.lens_patch import LensPatch
from backend.app.models.meeting_extract import MeetingExtract
from backend.app.models.meeting_mode import MeetingMode, evaluate_transition
from backend.app.models.state_vector import StateVector, ProgressScore, ViolationScore
from backend.app.services.orchestration.meeting.scoring.goal_alignment import (
    GoalAlignmentScorer,
)
from backend.app.services.orchestration.meeting.scoring.violation import (
    ViolationScorer,
)
from backend.app.services.orchestration.meeting.scoring.drift import DriftScorer
from backend.app.services.orchestration.meeting.scoring.lyapunov import (
    compute_lyapunov_v,
)

logger = logging.getLogger(__name__)

# Evidence gating: sessions within grace period bypass the cap
EVIDENCE_GRACE_SESSIONS = 3
EVIDENCE_CAP_FACTOR = 0.5


class StateVectorService:
    """Orchestrates L3 scoring to compute StateVector s_t.

    Usage:
        svc = StateVectorService()
        sv = svc.compute(extract, goal_set, patches, ...)
    """

    def __init__(
        self,
        goal_scorer: Optional[GoalAlignmentScorer] = None,
        violation_scorer: Optional[ViolationScorer] = None,
        drift_scorer: Optional[DriftScorer] = None,
    ):
        self.goal_scorer = goal_scorer or GoalAlignmentScorer()
        self.violation_scorer = violation_scorer or ViolationScorer()
        self.drift_scorer = drift_scorer or DriftScorer()

    def compute(
        self,
        meeting_session_id: str,
        workspace_id: str,
        extract: MeetingExtract,
        goal_set: Optional[GoalSet],
        patches: Optional[List[LensPatch]] = None,
        current_lens_hash: Optional[str] = None,
        previous_lens_hash: Optional[str] = None,
        current_mode: MeetingMode = MeetingMode.EXPLORE,
        previous_mode: Optional[MeetingMode] = None,
        session_count: int = 0,
        risk_fallback: float = 0.0,
        project_id: Optional[str] = None,
    ) -> StateVector:
        """Compute state vector s_t from meeting session artifacts.

        Args:
            meeting_session_id: Current meeting session ID.
            workspace_id: Workspace scope.
            extract: MeetingExtract with classified items.
            goal_set: GoalSet with clauses (may be None).
            patches: LensPatch list from this session.
            current_lens_hash: Current lens hash.
            previous_lens_hash: Previous lens hash.
            current_mode: Current meeting mode.
            previous_mode: Mode before DEBUG (for exit routing).
            session_count: How many sessions have run (for grace period).
            risk_fallback: Fallback risk value if no EGB data.
            project_id: Optional project scope.

        Returns:
            Computed StateVector with all axes filled.
        """
        sv = StateVector.create(
            meeting_session_id=meeting_session_id,
            workspace_id=workspace_id,
            project_id=project_id,
        )

        # --- 1. Progress axis ---
        progress_scores: List[ProgressScore] = []
        if goal_set and goal_set.clauses:
            progress_scores = self.goal_scorer.score(extract, goal_set)
        sv.progress = self._aggregate_progress(progress_scores)
        sv.progress_scores = progress_scores

        # --- 2. Evidence axis ---
        sv.evidence = self._compute_evidence(progress_scores, session_count)

        # --- 3. Risk axis (violations + fallback) ---
        violation_scores: List[ViolationScore] = []
        if goal_set and goal_set.goal_not:
            violation_scores = self.violation_scorer.score(extract, goal_set)
        sv.violation_scores = violation_scores
        violation_risk = max((v.score for v in violation_scores), default=0.0)
        sv.risk = max(violation_risk, risk_fallback)

        # --- 4. Drift axis ---
        if patches:
            sv.drift = self.drift_scorer.score_from_patches(patches)
        elif current_lens_hash and previous_lens_hash:
            sv.drift = self.drift_scorer.score(current_lens_hash, previous_lens_hash)

        # --- 5. Lyapunov V ---
        sv.lyapunov_v = compute_lyapunov_v(sv)

        # --- 6. Mode FSM ---
        new_mode = evaluate_transition(current_mode, sv, previous_mode)
        sv.mode = (new_mode or current_mode).value

        logger.info(
            "StateVector computed: session=%s axes=(%.2f, %.2f, %.2f, %.2f) V=%.3f mode=%s",
            meeting_session_id,
            sv.progress,
            sv.evidence,
            sv.risk,
            sv.drift,
            sv.lyapunov_v,
            sv.mode,
        )

        return sv

    def _aggregate_progress(self, scores: List[ProgressScore]) -> float:
        """Aggregate progress scores into single axis value.

        Strategy: weighted average of best score per clause.
        """
        if not scores:
            return 0.0

        # Best score per clause
        best_by_clause: dict = {}
        for s in scores:
            key = s.goal_clause_id
            if key not in best_by_clause or s.score > best_by_clause[key]:
                best_by_clause[key] = s.score

        if not best_by_clause:
            return 0.0

        return min(sum(best_by_clause.values()) / len(best_by_clause), 1.0)

    def _compute_evidence(
        self,
        scores: List[ProgressScore],
        session_count: int,
    ) -> float:
        """Compute evidence axis with gating.

        Evidence = fraction of progress scores backed by evidence_refs.
        During grace period (first N sessions), gating is bypassed.
        """
        if not scores:
            return 0.0

        has_evidence = sum(1 for s in scores if s.has_evidence)
        ratio = has_evidence / len(scores)

        # Grace period: bypass evidence cap
        if session_count < EVIDENCE_GRACE_SESSIONS:
            return ratio

        # After grace: cap scores without evidence
        if ratio < 1.0:
            uncapped_count = has_evidence
            capped_count = len(scores) - has_evidence
            weighted = uncapped_count * 1.0 + capped_count * EVIDENCE_CAP_FACTOR
            return min(weighted / len(scores), 1.0)

        return ratio
