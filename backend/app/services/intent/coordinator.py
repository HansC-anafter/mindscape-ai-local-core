"""
Intent Decision Coordinator

Coordinates rule-based and LLM-based intent decision making.
"""

import logging
from typing import Optional

from .models import InteractionType
from .rule_matcher import RuleBasedIntentMatcher
from .llm_matcher import LLMBasedIntentMatcher

logger = logging.getLogger(__name__)


class IntentDecisionCoordinator:
    """Coordinates rule-based and LLM-based intent decision making"""

    def __init__(
        self,
        rule_matcher: RuleBasedIntentMatcher,
        llm_matcher: LLMBasedIntentMatcher,
        use_llm: bool = True,
        rule_priority: bool = True,
    ):
        self.rule_matcher = rule_matcher
        self.llm_matcher = llm_matcher
        self.use_llm = use_llm
        self.rule_priority = rule_priority

    async def decide_interaction_type(
        self, user_input: str, channel: str = "api", model_name: Optional[str] = None
    ) -> tuple[InteractionType, float, str]:
        """
        Decide interaction type using rule-based and/or LLM-based matching

        Returns:
            (InteractionType, confidence, method_used)
        """
        # Try rule-based first if rule_priority is True
        if self.rule_priority:
            rule_result = self.rule_matcher.match_interaction_type(user_input, channel)
            if rule_result:
                logger.info(
                    f"[IntentDecisionCoordinator] Rule-based match: {rule_result.value}"
                )
                return rule_result, 0.9, "rule_based"

        # Fallback to LLM if enabled
        if self.use_llm:
            try:
                interaction_type, confidence = (
                    await self.llm_matcher.determine_interaction_type(
                        user_input, channel, model_name=model_name
                    )
                )
                logger.info(
                    f"[IntentDecisionCoordinator] LLM-based match: {interaction_type.value} (confidence: {confidence:.2f})"
                )
                return interaction_type, confidence, "llm_based"
            except Exception as e:
                logger.warning(f"[IntentDecisionCoordinator] LLM matching failed: {e}")

        # If rule_priority is False and no rule match, try rules as fallback
        if not self.rule_priority:
            rule_result = self.rule_matcher.match_interaction_type(user_input, channel)
            if rule_result:
                logger.info(
                    f"[IntentDecisionCoordinator] Rule-based fallback: {rule_result.value}"
                )
                return rule_result, 0.7, "rule_based_fallback"

        # Default: unknown
        logger.warning(
            f"[IntentDecisionCoordinator] No match found for: {user_input[:50]}"
        )
        return InteractionType.UNKNOWN, 0.0, "none"
