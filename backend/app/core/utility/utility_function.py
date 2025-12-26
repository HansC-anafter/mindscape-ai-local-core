"""
Utility Function Framework

Explicit utility function u(a,s) for systematic model switching strategy.
"""

import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum

from .scoring_dimensions import ScoringContext, ScoringDimensions

logger = logging.getLogger(__name__)


class UtilityWeight(str, Enum):
    """Utility weight preset"""
    COST_OPTIMIZED = "cost_optimized"  # Prioritize cost
    RISK_AVERSE = "risk_averse"  # Prioritize safety
    SUCCESS_OPTIMIZED = "success_optimized"  # Prioritize success rate
    FRICTION_MINIMIZED = "friction_minimized"  # Minimize human friction
    BALANCED = "balanced"  # Balanced weights


@dataclass
class UtilityScore:
    """Utility score result"""
    total_score: float
    cost_score: float
    risk_score: float
    success_rate_score: float
    human_friction_score: float
    weights: Dict[str, float]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "total_score": self.total_score,
            "cost_score": self.cost_score,
            "risk_score": self.risk_score,
            "success_rate_score": self.success_rate_score,
            "human_friction_score": self.human_friction_score,
            "weights": self.weights,
        }


class UtilityFunction:
    """
    Utility function u(a,s)

    Computes utility score for action a in state s.
    Utility = weighted sum of scoring dimensions.
    """

    def __init__(
        self,
        weights: Optional[Dict[str, float]] = None,
        weight_preset: Optional[UtilityWeight] = None
    ):
        """
        Initialize UtilityFunction

        Args:
            weights: Custom weights dictionary (cost, risk, success_rate, human_friction)
            weight_preset: Weight preset (overrides custom weights if provided)
        """
        self.scoring_dimensions = ScoringDimensions()

        # Set weights
        if weight_preset:
            self.weights = self._get_preset_weights(weight_preset)
        elif weights:
            self.weights = weights
        else:
            self.weights = self._get_preset_weights(UtilityWeight.BALANCED)

        # Normalize weights
        total_weight = sum(self.weights.values())
        if total_weight > 0:
            self.weights = {k: v / total_weight for k, v in self.weights.items()}

    def _get_preset_weights(self, preset: UtilityWeight) -> Dict[str, float]:
        """Get preset weights"""
        presets = {
            UtilityWeight.COST_OPTIMIZED: {
                "cost": 0.5,
                "risk": 0.2,
                "success_rate": 0.2,
                "human_friction": 0.1,
            },
            UtilityWeight.RISK_AVERSE: {
                "cost": 0.1,
                "risk": 0.5,
                "success_rate": 0.3,
                "human_friction": 0.1,
            },
            UtilityWeight.SUCCESS_OPTIMIZED: {
                "cost": 0.2,
                "risk": 0.2,
                "success_rate": 0.5,
                "human_friction": 0.1,
            },
            UtilityWeight.FRICTION_MINIMIZED: {
                "cost": 0.2,
                "risk": 0.2,
                "success_rate": 0.2,
                "human_friction": 0.4,
            },
            UtilityWeight.BALANCED: {
                "cost": 0.25,
                "risk": 0.25,
                "success_rate": 0.25,
                "human_friction": 0.25,
            },
        }
        return presets.get(preset, presets[UtilityWeight.BALANCED])

    def evaluate(
        self,
        context: ScoringContext,
        estimated_tokens: int = 1000
    ) -> UtilityScore:
        """
        Evaluate utility function u(a,s)

        Args:
            context: Scoring context (action a, state s)
            estimated_tokens: Estimated token count (for cost scoring)

        Returns:
            UtilityScore instance
        """
        # Score all dimensions
        dimension_scores = self.scoring_dimensions.score_all(context, estimated_tokens)

        # Compute weighted utility score
        # Note: For cost, risk, and human_friction, lower is better (invert)
        # For success_rate, higher is better
        cost_contribution = (1.0 - dimension_scores["cost"]) * self.weights["cost"]
        risk_contribution = (1.0 - dimension_scores["risk"]) * self.weights["risk"]
        success_contribution = dimension_scores["success_rate"] * self.weights["success_rate"]
        friction_contribution = (1.0 - dimension_scores["human_friction"]) * self.weights["human_friction"]

        total_score = (
            cost_contribution +
            risk_contribution +
            success_contribution +
            friction_contribution
        )

        return UtilityScore(
            total_score=total_score,
            cost_score=dimension_scores["cost"],
            risk_score=dimension_scores["risk"],
            success_rate_score=dimension_scores["success_rate"],
            human_friction_score=dimension_scores["human_friction"],
            weights=self.weights.copy()
        )

    def compare_actions(
        self,
        contexts: list[ScoringContext],
        estimated_tokens: int = 1000
    ) -> Dict[str, UtilityScore]:
        """
        Compare multiple actions

        Args:
            contexts: List of scoring contexts (different actions)
            estimated_tokens: Estimated token count

        Returns:
            Dictionary mapping action identifier to UtilityScore
        """
        results = {}
        for i, context in enumerate(contexts):
            action_id = context.metadata.get("action_id") if context.metadata else f"action_{i}"
            score = self.evaluate(context, estimated_tokens)
            results[action_id] = score

        return results

    def select_best_action(
        self,
        contexts: list[ScoringContext],
        estimated_tokens: int = 1000
    ) -> tuple[ScoringContext, UtilityScore]:
        """
        Select best action based on utility

        Args:
            contexts: List of scoring contexts (different actions)
            estimated_tokens: Estimated token count

        Returns:
            Tuple of (best context, best utility score)
        """
        if not contexts:
            raise ValueError("No contexts provided")

        best_context = None
        best_score = None
        best_utility = float('-inf')

        for context in contexts:
            utility = self.evaluate(context, estimated_tokens)
            if utility.total_score > best_utility:
                best_utility = utility.total_score
                best_context = context
                best_score = utility

        return best_context, best_score









