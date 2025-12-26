"""
Utility Evaluator

Evaluates utility for decision points (intent filtering, plan generation, graph variant selection).
"""

import logging
from typing import Dict, Any, Optional

from .utility_function import UtilityFunction, UtilityWeight, UtilityScore
from .scoring_dimensions import ScoringContext, RiskLevel

logger = logging.getLogger(__name__)


class UtilityEvaluator:
    """
    Utility evaluator

    Evaluates utility for various decision points in the system.
    """

    def __init__(
        self,
        utility_function: Optional[UtilityFunction] = None,
        weight_preset: Optional[UtilityWeight] = None
    ):
        """
        Initialize UtilityEvaluator

        Args:
            utility_function: UtilityFunction instance (will create if not provided)
            weight_preset: Weight preset for utility function
        """
        if utility_function:
            self.utility_function = utility_function
        else:
            self.utility_function = UtilityFunction(weight_preset=weight_preset or UtilityWeight.BALANCED)

    def evaluate_intent_escalation(
        self,
        workspace_id: str,
        action_type: str,
        model_name: str,
        risk_level: Optional[RiskLevel] = None,
        urgency: Optional[str] = None,
        cost_constraint: Optional[str] = None,
        estimated_tokens: int = 1000
    ) -> UtilityScore:
        """
        Evaluate utility for intent filtering escalation decision

        Args:
            workspace_id: Workspace ID
            action_type: Action type (e.g., "tool_candidate_selection")
            model_name: Model name
            risk_level: Risk level
            urgency: Urgency level
            cost_constraint: Cost constraint
            estimated_tokens: Estimated token count

        Returns:
            UtilityScore instance
        """
        context = ScoringContext(
            workspace_id=workspace_id,
            action_type=action_type,
            model_name=model_name,
            risk_level=risk_level,
            urgency=urgency,
            cost_constraint=cost_constraint,
            metadata={"decision_point": "intent_escalation"}
        )

        return self.utility_function.evaluate(context, estimated_tokens)

    def should_escalate_intent(
        self,
        workspace_id: str,
        action_type: str,
        fast_model_name: str,
        strong_model_name: str,
        risk_level: Optional[RiskLevel] = None,
        urgency: Optional[str] = None,
        cost_constraint: Optional[str] = None,
        estimated_tokens: int = 1000,
        escalation_threshold: float = 0.1
    ) -> tuple[bool, UtilityScore, UtilityScore]:
        """
        Determine if intent filtering should escalate to strong model

        Args:
            workspace_id: Workspace ID
            action_type: Action type
            fast_model_name: Fast model name
            strong_model_name: Strong model name
            risk_level: Risk level
            urgency: Urgency level
            cost_constraint: Cost constraint
            estimated_tokens: Estimated token count
            escalation_threshold: Utility difference threshold for escalation

        Returns:
            Tuple of (should_escalate, fast_model_score, strong_model_score)
        """
        # Evaluate fast model
        fast_score = self.evaluate_intent_escalation(
            workspace_id=workspace_id,
            action_type=action_type,
            model_name=fast_model_name,
            risk_level=risk_level,
            urgency=urgency,
            cost_constraint=cost_constraint,
            estimated_tokens=estimated_tokens
        )

        # Evaluate strong model
        strong_score = self.evaluate_intent_escalation(
            workspace_id=workspace_id,
            action_type=action_type,
            model_name=strong_model_name,
            risk_level=risk_level,
            urgency=urgency,
            cost_constraint=cost_constraint,
            estimated_tokens=estimated_tokens
        )

        # Determine escalation
        utility_diff = strong_score.total_score - fast_score.total_score

        # Escalate if:
        # 1. Strong model has significantly higher utility (above threshold)
        # 2. Risk level is high or critical
        should_escalate = (
            utility_diff > escalation_threshold or
            risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]
        )

        logger.info(
            f"UtilityEvaluator: Intent escalation decision - "
            f"fast_score={fast_score.total_score:.3f}, "
            f"strong_score={strong_score.total_score:.3f}, "
            f"diff={utility_diff:.3f}, "
            f"should_escalate={should_escalate}"
        )

        return should_escalate, fast_score, strong_score

    def evaluate_plan_model_selection(
        self,
        workspace_id: str,
        model_name: str,
        risk_level: Optional[RiskLevel] = None,
        urgency: Optional[str] = None,
        cost_constraint: Optional[str] = None,
        estimated_tokens: int = 5000
    ) -> UtilityScore:
        """
        Evaluate utility for plan generation model selection

        Args:
            workspace_id: Workspace ID
            model_name: Model name
            risk_level: Risk level
            urgency: Urgency level
            cost_constraint: Cost constraint
            estimated_tokens: Estimated token count

        Returns:
            UtilityScore instance
        """
        context = ScoringContext(
            workspace_id=workspace_id,
            action_type="plan_generation",
            model_name=model_name,
            risk_level=risk_level,
            urgency=urgency,
            cost_constraint=cost_constraint,
            metadata={"decision_point": "plan_model_selection"}
        )

        return self.utility_function.evaluate(context, estimated_tokens)

    def evaluate_graph_variant_selection(
        self,
        workspace_id: str,
        variant_name: str,
        risk_level: Optional[RiskLevel] = None,
        urgency: Optional[str] = None,
        cost_constraint: Optional[str] = None,
        estimated_tokens: int = 3000
    ) -> UtilityScore:
        """
        Evaluate utility for graph variant selection

        Args:
            workspace_id: Workspace ID
            variant_name: Graph variant name (e.g., "fast_path", "safe_path")
            risk_level: Risk level
            urgency: Urgency level
            cost_constraint: Cost constraint
            estimated_tokens: Estimated token count

        Returns:
            UtilityScore instance
        """
        # Map variant to action type
        variant_action_map = {
            "fast_path": "tool_candidate_selection",  # Fast path uses faster models
            "safe_path": "plan_generation",  # Safe path uses stronger models
            "balanced": "plan_generation",
        }

        action_type = variant_action_map.get(variant_name, "plan_generation")

        context = ScoringContext(
            workspace_id=workspace_id,
            action_type=action_type,
            model_name=None,  # Variant selection doesn't specify model
            risk_level=risk_level,
            urgency=urgency,
            cost_constraint=cost_constraint,
            metadata={
                "decision_point": "graph_variant_selection",
                "variant_name": variant_name
            }
        )

        return self.utility_function.evaluate(context, estimated_tokens)









