"""
Scoring Dimensions

Scoring dimensions for utility function: cost, risk, success rate, human friction.
"""

import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class RiskLevel(str, Enum):
    """Risk level"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ScoringContext:
    """Context for scoring"""
    workspace_id: str
    action_type: str  # e.g., "tool_call", "plan_generation", "intent_analysis"
    model_name: Optional[str] = None
    capability_profile: Optional[str] = None
    risk_level: Optional[RiskLevel] = None
    urgency: Optional[str] = None  # "low", "normal", "high"
    cost_constraint: Optional[str] = None  # "loose", "normal", "strict"
    metadata: Optional[Dict[str, Any]] = None


class CostScorer:
    """
    Cost scorer

    Scores actions based on cost (model API cost, latency, etc.)
    Loads model costs from ModelUtilityConfigStore if available, falls back to defaults.
    """

    def __init__(self, use_config_store: bool = True):
        """
        Initialize CostScorer

        Args:
            use_config_store: Whether to load costs from ModelUtilityConfigStore (default: True)
        """
        self.use_config_store = use_config_store
        # Default model cost mapping (fallback)
        self._default_costs = {
            "gpt-4o": 0.005,  # $5 per 1M tokens
            "gpt-4o-mini": 0.00015,  # $0.15 per 1M tokens
            "gpt-4-turbo": 0.01,  # $10 per 1M tokens
            "gpt-3.5-turbo": 0.0005,  # $0.5 per 1M tokens
            "claude-3-5-sonnet": 0.003,  # $3 per 1M tokens
            "claude-3-opus": 0.015,  # $15 per 1M tokens
            "claude-3-haiku": 0.00025,  # $0.25 per 1M tokens
        }
        self._config_store = None
        if use_config_store:
            try:
                from backend.app.services.model_utility_config_store import ModelUtilityConfigStore
                self._config_store = ModelUtilityConfigStore()
            except Exception as e:
                logger.warning(f"Failed to initialize ModelUtilityConfigStore: {e}, using defaults")

    def _get_model_cost(self, model_name: str) -> float:
        """
        Get model cost per 1M tokens

        Args:
            model_name: Model name

        Returns:
            Cost per 1M tokens
        """
        if self._config_store:
            try:
                config = self._config_store.get_model_config(model_name)
                if config:
                    return config.cost_per_1m_tokens / 1000000  # Convert to per-token cost
            except Exception as e:
                logger.debug(f"Failed to get model cost from config store for {model_name}: {e}")

        # Fall back to default
        return self._default_costs.get(model_name, 0.001) / 1000000  # Default $1 per 1M tokens

    def score(
        self,
        context: ScoringContext,
        estimated_tokens: int = 1000
    ) -> float:
        """
        Score cost

        Args:
            context: Scoring context
            estimated_tokens: Estimated token count

        Returns:
            Cost score (lower is better, normalized to 0-1)
        """
        model_name = context.model_name or "gpt-3.5-turbo"

        # Get model cost per token (from config store or defaults)
        cost_per_1m_tokens = self._get_model_cost(model_name) * 1000000  # Convert back to per 1M

        # Calculate estimated cost
        estimated_cost = cost_per_1m_tokens * (estimated_tokens / 1000000)

        # Normalize to 0-1 (assuming max cost is $0.1 per call)
        cost_score = min(estimated_cost / 0.1, 1.0)

        # Adjust based on cost constraint
        if context.cost_constraint == "strict":
            cost_score *= 2.0  # Penalize cost more
        elif context.cost_constraint == "loose":
            cost_score *= 0.5  # Penalize cost less

        return cost_score


class RiskScorer:
    """
    Risk scorer

    Scores actions based on risk (error probability, impact, etc.)
    """

    def __init__(self):
        """Initialize RiskScorer"""
        # Risk level mapping
        self.risk_scores = {
            RiskLevel.LOW: 0.1,
            RiskLevel.MEDIUM: 0.3,
            RiskLevel.HIGH: 0.6,
            RiskLevel.CRITICAL: 0.9,
        }

        # Action type risk mapping
        self.action_risk_base = {
            "intent_analysis": 0.2,  # Low risk (can be corrected)
            "tool_candidate_selection": 0.3,  # Medium risk
            "plan_generation": 0.4,  # Medium-high risk
            "tool_call": 0.5,  # High risk (executes action)
            "write_operation": 0.8,  # Very high risk
            "publish_operation": 0.9,  # Critical risk
        }

    def score(
        self,
        context: ScoringContext
    ) -> float:
        """
        Score risk

        Args:
            context: Scoring context

        Returns:
            Risk score (higher is worse, normalized to 0-1)
        """
        # Base risk from action type
        base_risk = self.action_risk_base.get(context.action_type, 0.5)

        # Adjust based on explicit risk level
        if context.risk_level:
            risk_level_score = self.risk_scores.get(context.risk_level, 0.5)
            # Combine base and explicit risk
            risk_score = (base_risk + risk_level_score) / 2
        else:
            risk_score = base_risk

        return risk_score


class SuccessRateScorer:
    """
    Success rate scorer

    Scores actions based on expected success rate (model capability, task complexity, etc.)
    Loads success rates from ModelUtilityConfigStore if available, falls back to defaults.
    """

    def __init__(self, use_config_store: bool = True):
        """
        Initialize SuccessRateScorer

        Args:
            use_config_store: Whether to load success rates from ModelUtilityConfigStore (default: True)
        """
        self.use_config_store = use_config_store
        # Default model success rates (fallback)
        self._default_success_rates = {
            "gpt-4o": 0.95,
            "gpt-4o-mini": 0.85,
            "gpt-4-turbo": 0.92,
            "gpt-3.5-turbo": 0.80,
            "claude-3-5-sonnet": 0.93,
            "claude-3-opus": 0.96,
            "claude-3-haiku": 0.82,
        }
        self._config_store = None
        if use_config_store:
            try:
                from backend.app.services.model_utility_config_store import ModelUtilityConfigStore
                self._config_store = ModelUtilityConfigStore()
            except Exception as e:
                logger.warning(f"Failed to initialize ModelUtilityConfigStore: {e}, using defaults")

    def _get_model_success_rate(self, model_name: str) -> float:
        """
        Get model success rate

        Args:
            model_name: Model name

        Returns:
            Success rate (0-1)
        """
        if self._config_store:
            try:
                config = self._config_store.get_model_config(model_name)
                if config:
                    return config.success_rate
            except Exception as e:
                logger.debug(f"Failed to get model success rate from config store for {model_name}: {e}")

        # Fall back to default
        return self._default_success_rates.get(model_name, 0.80)  # Default 80%

        # Action type complexity mapping
        self.action_complexity = {
            "intent_analysis": 0.9,  # High success rate expected
            "tool_candidate_selection": 0.85,  # Medium-high
            "plan_generation": 0.80,  # Medium
            "tool_call": 0.75,  # Medium-low (depends on tool)
            "write_operation": 0.70,  # Lower (more complex)
            "publish_operation": 0.65,  # Lower (most complex)
        }

    def score(
        self,
        context: ScoringContext
    ) -> float:
        """
        Score success rate

        Args:
            context: Scoring context

        Returns:
            Success rate score (higher is better, normalized to 0-1)
        """
        # Base success rate from action type
        base_success = self.action_complexity.get(context.action_type, 0.75)

        # Adjust based on model capability (from config store or defaults)
        if context.model_name:
            model_success = self._get_model_success_rate(context.model_name)
            # Combine base and model success rate
            success_rate = (base_success + model_success) / 2
        else:
            success_rate = base_success

        # Adjust based on capability profile
        if context.capability_profile == "precise":
            success_rate *= 1.1  # Boost success rate
        elif context.capability_profile == "fast":
            success_rate *= 0.95  # Slight reduction

        return min(success_rate, 1.0)


class HumanFrictionScorer:
    """
    Human friction scorer

    Scores actions based on human friction (confirmation requests, errors requiring human intervention, etc.)
    """

    def __init__(self):
        """Initialize HumanFrictionScorer"""
        # Action type friction mapping
        self.action_friction = {
            "intent_analysis": 0.1,  # Low friction (transparent)
            "tool_candidate_selection": 0.2,  # Low-medium
            "plan_generation": 0.3,  # Medium (may need review)
            "tool_call": 0.4,  # Medium-high (may need confirmation)
            "write_operation": 0.6,  # High (often needs confirmation)
            "publish_operation": 0.8,  # Very high (always needs confirmation)
        }

    def score(
        self,
        context: ScoringContext
    ) -> float:
        """
        Score human friction

        Args:
            context: Scoring context

        Returns:
            Human friction score (higher is worse, normalized to 0-1)
        """
        # Base friction from action type
        base_friction = self.action_friction.get(context.action_type, 0.5)

        # Adjust based on risk level (higher risk = more friction)
        if context.risk_level:
            risk_multiplier = {
                RiskLevel.LOW: 0.8,
                RiskLevel.MEDIUM: 1.0,
                RiskLevel.HIGH: 1.3,
                RiskLevel.CRITICAL: 1.5,
            }.get(context.risk_level, 1.0)
            friction = base_friction * risk_multiplier
        else:
            friction = base_friction

        # Adjust based on urgency (higher urgency = less acceptable friction)
        if context.urgency == "high":
            friction *= 1.2  # Penalize friction more
        elif context.urgency == "low":
            friction *= 0.9  # Accept more friction

        return min(friction, 1.0)


class ScoringDimensions:
    """
    Scoring dimensions aggregator

    Combines all scoring dimensions into a unified interface.
    Loads model configurations from ModelUtilityConfigStore if available.
    """

    def __init__(self, use_config_store: bool = True):
        """
        Initialize ScoringDimensions

        Args:
            use_config_store: Whether to load model configs from ModelUtilityConfigStore (default: True)
        """
        self.cost_scorer = CostScorer(use_config_store=use_config_store)
        self.risk_scorer = RiskScorer()
        self.success_rate_scorer = SuccessRateScorer(use_config_store=use_config_store)
        self.human_friction_scorer = HumanFrictionScorer()

    def score_all(
        self,
        context: ScoringContext,
        estimated_tokens: int = 1000
    ) -> Dict[str, float]:
        """
        Score all dimensions

        Args:
            context: Scoring context
            estimated_tokens: Estimated token count (for cost scoring)

        Returns:
            Dictionary with scores for all dimensions
        """
        return {
            "cost": self.cost_scorer.score(context, estimated_tokens),
            "risk": self.risk_scorer.score(context),
            "success_rate": self.success_rate_scorer.score(context),
            "human_friction": self.human_friction_scorer.score(context),
        }

