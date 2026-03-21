"""
L3 Dispatch Gate — orchestration-level dispatch decisions.

Runs AFTER the Policy Gate (L4 allowlist checks) and BEFORE TaskIR
compilation. Produces per-intent decisions:

  dispatch_now  → compile to TaskIR and dispatch
  clarify       → loop back to L1 (ask user for more info)
  split         → decompose compound intent into sub-intents
  defer         → postpone dispatch (risk/concurrency budget)

Invariant: Policy Gate runs first. Items already policy_blocked
are never re-evaluated by DispatchGate.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from backend.app.models.action_intent import ActionIntent, IntentConfidence
from backend.app.models.supervision_signals import SupervisionSignals

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Decision types
# ------------------------------------------------------------------


class GateDecision(str, Enum):
    """Per-intent dispatch decision from the L3 gate."""

    DISPATCH_NOW = "dispatch_now"
    CLARIFY = "clarify"
    SPLIT = "split"
    DEFER = "defer"
    SHRINK_SCOPE = "shrink_scope"  # OP-3: budget-aware scope reduction


class IntentDecision(BaseModel):
    """Decision for a single ActionIntent."""

    intent_id: str
    decision: GateDecision
    reason: str = ""
    sub_intents: List[ActionIntent] = Field(
        default_factory=list,
        description="Decomposed sub-intents (only for SPLIT decisions)",
    )


class GateResult(BaseModel):
    """Aggregate result from the L3 dispatch gate."""

    decisions: List[IntentDecision] = Field(default_factory=list)

    @property
    def dispatch_intents(self) -> List[str]:
        """Intent IDs approved for dispatch."""
        return [
            d.intent_id
            for d in self.decisions
            if d.decision == GateDecision.DISPATCH_NOW
        ]

    @property
    def clarify_intents(self) -> List[IntentDecision]:
        """Intents that need clarification."""
        return [d for d in self.decisions if d.decision == GateDecision.CLARIFY]

    @property
    def deferred_intents(self) -> List[IntentDecision]:
        """Intents that were deferred."""
        return [d for d in self.decisions if d.decision == GateDecision.DEFER]

    @property
    def split_intents(self) -> List[IntentDecision]:
        """Intents that were split."""
        return [d for d in self.decisions if d.decision == GateDecision.SPLIT]

    @property
    def shrunk_intents(self) -> List[IntentDecision]:
        """Intents deferred via scope shrinking (OP-3)."""
        return [d for d in self.decisions if d.decision == GateDecision.SHRINK_SCOPE]


# ------------------------------------------------------------------
# Gate implementation
# ------------------------------------------------------------------


class DispatchGate:
    """L3 online dispatch gate.

    Evaluates each ActionIntent against supervision signals and
    confidence thresholds, producing a GateResult with per-intent
    decisions.

    Args:
        signals: L5 supervision signals (defaults to safe empty signals).
        confidence_threshold: Minimum confidence to auto-dispatch
            (LOW intents below this → CLARIFY).
        compound_word_limit: Intents with descriptions exceeding this
            word count are candidates for SPLIT.
    """

    def __init__(
        self,
        signals: Optional[SupervisionSignals] = None,
        confidence_threshold: IntentConfidence = IntentConfidence.MEDIUM,
        compound_word_limit: int = 100,
    ):
        self.signals = signals or SupervisionSignals()
        self.confidence_threshold = confidence_threshold
        self.compound_word_limit = compound_word_limit
        self.correctness_shrink_threshold = 0.75
        self.correctness_defer_threshold = 0.4
        self.correctness_defer_acceptance_threshold = 0.5

    def evaluate(
        self,
        intents: List[ActionIntent],
    ) -> GateResult:
        """Evaluate all intents and return gate decisions.

        Evaluation order per intent:
        1. Risk budget check → DEFER if exhausted
        2. Concurrency limit check → DEFER if at limit
        3. Confidence check → CLARIFY if below threshold
        4. Compound intent check → SPLIT if oversized
        5. Default → DISPATCH_NOW
        """
        result = GateResult()

        for intent in intents:
            decision = self._evaluate_single(intent)
            result.decisions.append(decision)

        return result

    def _evaluate_single(self, intent: ActionIntent) -> IntentDecision:
        """Evaluate a single intent against gate rules."""

        # Rule 1: Risk budget exhausted → DEFER
        if self.signals.risk_budget_exhausted:
            return IntentDecision(
                intent_id=intent.intent_id,
                decision=GateDecision.DEFER,
                reason="risk_budget_exhausted",
            )

        # Rule 2: Concurrency limit reached → DEFER
        if self.signals.concurrency_at_limit:
            return IntentDecision(
                intent_id=intent.intent_id,
                decision=GateDecision.DEFER,
                reason="concurrency_limit_reached",
            )

        # Rule 3: Low confidence → CLARIFY
        if self._below_confidence_threshold(intent.confidence):
            return IntentDecision(
                intent_id=intent.intent_id,
                decision=GateDecision.CLARIFY,
                reason=f"confidence_too_low:{intent.confidence.value}",
            )

        # Rule 4: Compound intent → SPLIT
        desc = intent.description or ""
        if len(desc.split()) > self.compound_word_limit:
            return IntentDecision(
                intent_id=intent.intent_id,
                decision=GateDecision.SPLIT,
                reason=f"compound_intent:{len(desc.split())}_words",
            )

        # Rule 5: High failure rate + low retry budget → DEFER
        if (
            self.signals.historical_failure_rate > 0.5
            and self.signals.retry_budget_remaining <= 0
        ):
            return IntentDecision(
                intent_id=intent.intent_id,
                decision=GateDecision.DEFER,
                reason="high_failure_rate_no_retries",
            )

        # Rule 6 (P5): correctness recovery loop → trim/defer new low-priority work
        correctness_decision = self._evaluate_correctness_feedback(intent)
        if correctness_decision is not None:
            return correctness_decision

        # Rule 7 (OP-3): Budget pressure + low priority → SHRINK_SCOPE
        if self.signals.budget_pressure_high:
            priority = getattr(intent, "priority", None) or "medium"
            if priority == "low":
                return IntentDecision(
                    intent_id=intent.intent_id,
                    decision=GateDecision.SHRINK_SCOPE,
                    reason="budget_pressure_low_priority",
                )

        # Default: DISPATCH_NOW
        return IntentDecision(
            intent_id=intent.intent_id,
            decision=GateDecision.DISPATCH_NOW,
            reason="approved",
        )

    def _below_confidence_threshold(self, confidence: IntentConfidence) -> bool:
        """Check if confidence is below the gate threshold."""
        order = {
            IntentConfidence.LOW: 0,
            IntentConfidence.MEDIUM: 1,
            IntentConfidence.HIGH: 2,
        }
        return order.get(confidence, 0) < order.get(self.confidence_threshold, 1)

    def _evaluate_correctness_feedback(
        self,
        intent: ActionIntent,
    ) -> Optional[IntentDecision]:
        """Apply conservative correctness-loop feedback to new dispatches.

        The goal is not to hard-stop the session after a failed eval. Instead:
        - first remediation round: shrink low-priority expansion work
        - repeated remediation with poor quality: defer non-high-priority work
        """
        if self.signals.remediation_round <= 0:
            return None

        priority = self._normalize_priority(getattr(intent, "priority", None))
        quality_score = self.signals.quality_score
        acceptance_pass_rate = self.signals.acceptance_pass_rate

        if (
            priority == "low"
            and (
                quality_score < self.correctness_shrink_threshold
                or acceptance_pass_rate < self.correctness_shrink_threshold
            )
        ):
            return IntentDecision(
                intent_id=intent.intent_id,
                decision=GateDecision.SHRINK_SCOPE,
                reason=(
                    "correctness_feedback_low_priority:"
                    f"quality={quality_score:.2f}:"
                    f"acceptance={acceptance_pass_rate:.2f}:"
                    f"round={self.signals.remediation_round}"
                ),
            )

        if (
            priority != "high"
            and self.signals.remediation_round >= 2
            and (
                quality_score < self.correctness_defer_threshold
                or acceptance_pass_rate < self.correctness_defer_acceptance_threshold
            )
        ):
            return IntentDecision(
                intent_id=intent.intent_id,
                decision=GateDecision.DEFER,
                reason=(
                    "correctness_recovery_in_progress:"
                    f"quality={quality_score:.2f}:"
                    f"acceptance={acceptance_pass_rate:.2f}:"
                    f"round={self.signals.remediation_round}"
                ),
            )

        return None

    @staticmethod
    def _normalize_priority(priority: Optional[str]) -> str:
        """Normalize free-form intent priorities into gate buckets."""
        if not isinstance(priority, str):
            return "medium"
        normalized = priority.strip().lower()
        if normalized in {"high", "medium", "low"}:
            return normalized
        return "medium"
