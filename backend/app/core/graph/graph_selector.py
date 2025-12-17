"""
Graph Selection Logic

Selects appropriate graph variant based on utility function u(a,s).
Initial implementation uses simple rules, can be extended with full utility function.
"""

import logging
from typing import Optional, Dict, Any
from enum import Enum

from backend.app.core.ir.graph_ir import GraphIR
from .graph_variant_registry import GraphVariantRegistry, VariantType

logger = logging.getLogger(__name__)


class SelectionCriteria(str, Enum):
    """Selection criteria"""
    SPEED = "speed"  # Prioritize speed
    SAFETY = "safety"  # Prioritize safety/reliability
    BALANCED = "balanced"  # Balance between speed and safety
    COST = "cost"  # Prioritize cost efficiency
    CUSTOM = "custom"  # Custom criteria


class GraphSelector:
    """
    Graph variant selector

    Selects appropriate graph variant based on context and utility function.
    Initial implementation uses simple rules, can be extended with full utility function.
    """

    def __init__(self, registry: Optional[GraphVariantRegistry] = None):
        """
        Initialize GraphSelector

        Args:
            registry: GraphVariantRegistry instance (will create if not provided)
        """
        self.registry = registry or GraphVariantRegistry()

    def select_variant(
        self,
        graph_id: str,
        context: Dict[str, Any],
        criteria: Optional[SelectionCriteria] = None
    ) -> Optional[GraphIR]:
        """
        Select graph variant based on context and criteria

        Args:
            graph_id: Graph ID
            context: Execution context (risk_level, urgency, cost_constraint, etc.)
            criteria: Selection criteria (defaults to auto-select based on context)

        Returns:
            Selected GraphIR variant or None if not found
        """
        # Auto-select criteria if not provided
        if criteria is None:
            criteria = self._infer_criteria(context)

        # Get available variants
        available_variants = self.registry.list_variants(graph_id)
        if not available_variants:
            logger.warning(f"GraphSelector: No variants found for graph '{graph_id}'")
            return None

        # Select variant based on criteria
        if criteria == SelectionCriteria.SPEED:
            variant_name = self._select_fast_path(available_variants)
        elif criteria == SelectionCriteria.SAFETY:
            variant_name = self._select_safe_path(available_variants)
        elif criteria == SelectionCriteria.BALANCED:
            variant_name = self._select_balanced(available_variants)
        elif criteria == SelectionCriteria.COST:
            variant_name = self._select_cost_optimized(available_variants)
        else:
            variant_name = self._select_default(available_variants)

        # Get selected variant
        variant = self.registry.get_variant(graph_id, variant_name)
        if variant:
            logger.info(f"GraphSelector: Selected variant '{variant_name}' for graph '{graph_id}' based on criteria '{criteria.value}'")
        return variant

    def _infer_criteria(self, context: Dict[str, Any]) -> SelectionCriteria:
        """
        Infer selection criteria from context

        Args:
            context: Execution context

        Returns:
            Inferred SelectionCriteria
        """
        # Check risk level
        risk_level = context.get("risk_level", "low")
        if risk_level in ["high", "critical"]:
            return SelectionCriteria.SAFETY

        # Check urgency
        urgency = context.get("urgency", "normal")
        if urgency == "high":
            return SelectionCriteria.SPEED

        # Check cost constraint
        cost_constraint = context.get("cost_constraint", "normal")
        if cost_constraint == "strict":
            return SelectionCriteria.COST

        # Default to balanced
        return SelectionCriteria.BALANCED

    def _select_fast_path(self, available_variants: list) -> str:
        """Select fast path variant"""
        for variant_name in [VariantType.FAST_PATH.value, VariantType.BALANCED.value, "default"]:
            if variant_name in available_variants:
                return variant_name
        return available_variants[0] if available_variants else "default"

    def _select_safe_path(self, available_variants: list) -> str:
        """Select safe path variant"""
        for variant_name in [VariantType.SAFE_PATH.value, VariantType.BALANCED.value, "default"]:
            if variant_name in available_variants:
                return variant_name
        return available_variants[0] if available_variants else "default"

    def _select_balanced(self, available_variants: list) -> str:
        """Select balanced variant"""
        for variant_name in [VariantType.BALANCED.value, VariantType.FAST_PATH.value, VariantType.SAFE_PATH.value, "default"]:
            if variant_name in available_variants:
                return variant_name
        return available_variants[0] if available_variants else "default"

    def _select_cost_optimized(self, available_variants: list) -> str:
        """Select cost-optimized variant"""
        # Cost-optimized is similar to fast path (fewer expensive model calls)
        return self._select_fast_path(available_variants)

    def _select_default(self, available_variants: list) -> str:
        """Select default variant"""
        return available_variants[0] if available_variants else "default"

    def select_with_utility(
        self,
        graph_id: str,
        context: Dict[str, Any],
        utility_scores: Optional[Dict[str, float]] = None,
        workspace_id: Optional[str] = None,
        use_utility_evaluator: bool = True
    ) -> Optional[GraphIR]:
        """
        Select graph variant using utility function scores

        Args:
            graph_id: Graph ID
            context: Execution context
            utility_scores: Dictionary mapping variant names to utility scores (optional, will compute if not provided)
            workspace_id: Workspace ID (for utility evaluation)
            use_utility_evaluator: Whether to use UtilityEvaluator to compute scores (default: True)

        Returns:
            Selected GraphIR variant (highest utility score) or None if not found
        """
        # Compute utility scores if not provided
        if utility_scores is None and use_utility_evaluator and workspace_id:
            try:
                from backend.app.core.utility.utility_evaluator import UtilityEvaluator
                from backend.app.core.utility.scoring_dimensions import RiskLevel as UtilityRiskLevel

                evaluator = UtilityEvaluator()

                # Get available variants
                available_variants = self.registry.list_variants(graph_id)
                if not available_variants:
                    return self.select_variant(graph_id, context)

                # Map risk level
                utility_risk_level = None
                risk_level = context.get("risk_level", "low")
                if risk_level:
                    risk_map = {
                        "low": UtilityRiskLevel.LOW,
                        "medium": UtilityRiskLevel.MEDIUM,
                        "high": UtilityRiskLevel.HIGH,
                        "critical": UtilityRiskLevel.CRITICAL,
                    }
                    utility_risk_level = risk_map.get(risk_level)

                # Evaluate each variant
                utility_scores = {}
                for variant_name in available_variants:
                    score = evaluator.evaluate_graph_variant_selection(
                        workspace_id=workspace_id,
                        variant_name=variant_name,
                        risk_level=utility_risk_level,
                        urgency=context.get("urgency", "normal"),
                        cost_constraint=context.get("cost_constraint", "normal"),
                        estimated_tokens=3000
                    )
                    utility_scores[variant_name] = score.total_score
                    logger.debug(f"GraphSelector: Variant '{variant_name}' utility score: {score.total_score:.3f}")

            except Exception as e:
                logger.warning(f"Utility-based graph variant selection failed: {e}, falling back to rule-based", exc_info=True)
                return self.select_variant(graph_id, context)

        if not utility_scores:
            return self.select_variant(graph_id, context)

        # Select variant with highest utility score
        best_variant_name = max(utility_scores.items(), key=lambda x: x[1])[0]
        variant = self.registry.get_variant(graph_id, best_variant_name)

        if variant:
            logger.info(f"GraphSelector: Selected variant '{best_variant_name}' for graph '{graph_id}' with utility score {utility_scores[best_variant_name]:.3f}")
        return variant

