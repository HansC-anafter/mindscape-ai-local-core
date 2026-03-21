"""
RemediationPolicy — Deterministic follow-up gating for failed evaluations.

Decides whether a follow-up task should be created based on eval_result,
current remediation round, and quality thresholds.

Does NOT create the task itself — returns a RemediationDecision
for the caller (GovernanceEngine) to act on.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class RemediationDecision:
    """Result of remediation policy evaluation."""

    should_follow_up: bool
    reason: str
    remediation_round: int
    follow_up_context: Optional[Dict[str, Any]] = field(default=None)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "should_follow_up": self.should_follow_up,
            "reason": self.reason,
            "remediation_round": self.remediation_round,
            "follow_up_context": self.follow_up_context,
        }


class RemediationPolicy:
    """Deterministic gate for follow-up task creation.

    Policy rules (evaluated in order):
    1. eval passed → no follow-up
    2. current_round >= MAX_ROUNDS → stop (max reached)
    3. quality_score >= MIN_QUALITY_SCORE → skip (close enough)
    4. Otherwise → build follow-up context
    """

    MAX_ROUNDS = 2
    MIN_QUALITY_SCORE = 0.5

    def __init__(
        self,
        *,
        max_rounds: int = MAX_ROUNDS,
        min_quality_score: float = MIN_QUALITY_SCORE,
    ):
        self.max_rounds = max_rounds
        self.min_quality_score = min_quality_score

    def decide(
        self,
        *,
        eval_result: Dict[str, Any],
        current_round: int = 0,
        execution_id: str,
        artifact_id: Optional[str] = None,
        playbook_code: Optional[str] = None,
        acceptance_tests: Optional[List[str]] = None,
    ) -> RemediationDecision:
        """Evaluate whether a follow-up is warranted.

        Parameters:
            eval_result: Dict from AcceptanceEvaluator (passed, quality_score, reasons, checks).
            current_round: Current remediation round (0 = first attempt).
            execution_id: Original execution ID.
            artifact_id: Artifact from the failed attempt.
            playbook_code: Playbook that produced the result.
            acceptance_tests: Original acceptance criteria.

        Returns:
            RemediationDecision with follow_up_context if warranted.
        """
        next_round = current_round + 1
        passed = eval_result.get("passed", True)
        quality_score = eval_result.get("quality_score", 1.0)
        reasons = eval_result.get("reasons", [])

        # Rule 1: Eval passed → no follow-up
        if passed:
            return RemediationDecision(
                should_follow_up=False,
                reason="eval passed",
                remediation_round=current_round,
            )

        # Rule 2: Max rounds exceeded
        if current_round >= self.max_rounds:
            logger.warning(
                "RemediationPolicy: max rounds (%d) reached for exec=%s — no follow-up",
                self.max_rounds,
                execution_id,
            )
            return RemediationDecision(
                should_follow_up=False,
                reason=f"max remediation rounds ({self.max_rounds}) reached",
                remediation_round=current_round,
            )

        # Rule 3: Quality score above threshold
        if quality_score >= self.min_quality_score:
            return RemediationDecision(
                should_follow_up=False,
                reason=f"quality_score {quality_score:.2f} >= threshold {self.min_quality_score}",
                remediation_round=current_round,
            )

        # Rule 4: Follow-up warranted
        follow_up_context = {
            "remediation_round": next_round,
            "original_execution_id": execution_id,
            "original_artifact_id": artifact_id,
            "playbook_code": playbook_code,
            "eval_reasons": reasons,
            "eval_quality_score": quality_score,
            "acceptance_tests": acceptance_tests,
            "idempotency_key": f"followup:{execution_id}:{next_round}",
        }

        logger.info(
            "RemediationPolicy: follow-up warranted for exec=%s round=%d score=%.2f",
            execution_id,
            next_round,
            quality_score,
        )

        return RemediationDecision(
            should_follow_up=True,
            reason=f"quality_score {quality_score:.2f} below threshold, {len(reasons)} failing checks",
            remediation_round=next_round,
            follow_up_context=follow_up_context,
        )
