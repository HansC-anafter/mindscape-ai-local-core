from typing import Any, Optional, Tuple

from .model_routing import resolve_intent_stage_model
from .schemas import ToolSlotAnalysisResult


def is_ambiguous_message(user_message: str) -> bool:
    """Return whether a user message needs the precision stage."""
    if not user_message:
        return True

    message_lower = user_message.lower().strip()
    if len(message_lower) < 10:
        return True

    action_verbs = ["and", "also", "plus", "then", "after", "before", "while"]
    verb_count = sum(1 for verb in action_verbs if verb in message_lower)
    if verb_count >= 2:
        return True

    question_words = ["what", "which", "how", "when", "where", "why"]
    if any(word in message_lower for word in question_words) and len(message_lower) < 30:
        return True

    return False


def should_escalate_for_intent(
    *,
    recall_result: ToolSlotAnalysisResult,
    risk_level: str,
    user_message: str,
    workspace_id: Optional[str] = None,
    llm_provider_manager: Optional[Any] = None,
    profile_id: Optional[str] = None,
    logger: Optional[Any] = None,
    use_utility: bool = True,
) -> Tuple[bool, Optional[Any]]:
    """Evaluate whether tool selection needs the strong precision stage."""
    manager = llm_provider_manager
    if use_utility and workspace_id:
        try:
            from backend.app.core.utility.scoring_dimensions import (
                RiskLevel as UtilityRiskLevel,
            )
            from backend.app.core.utility.utility_evaluator import UtilityEvaluator

            evaluator = UtilityEvaluator()
            manager, fast_model = resolve_intent_stage_model(
                llm_provider_manager=manager,
                profile_id=profile_id,
                stage_name="intent_analysis",
                risk_level=risk_level,
            )
            manager, strong_model = resolve_intent_stage_model(
                llm_provider_manager=manager,
                profile_id=profile_id,
                stage_name="plan_generation",
                risk_level=risk_level,
            )
            if not fast_model or not strong_model:
                raise ValueError(
                    "Intent analyzer models must resolve through model-routing-registry"
                )

            risk_map = {
                "read": UtilityRiskLevel.LOW,
                "write": UtilityRiskLevel.HIGH,
                "publish": UtilityRiskLevel.CRITICAL,
            }
            utility_risk_level = risk_map.get(risk_level) if risk_level else None
            should_escalate, fast_score, strong_score = evaluator.should_escalate_intent(
                workspace_id=workspace_id,
                action_type="tool_candidate_selection",
                fast_model_name=fast_model,
                strong_model_name=strong_model,
                risk_level=utility_risk_level,
                urgency="normal",
                cost_constraint="normal",
                estimated_tokens=1000,
                escalation_threshold=0.1,
            )

            if logger:
                logger.info(
                    "Utility-based escalation decision: should_escalate=%s, "
                    "fast_score=%.3f, strong_score=%.3f",
                    should_escalate,
                    fast_score.total_score,
                    strong_score.total_score,
                )
            return should_escalate, manager
        except Exception as exc:
            if logger:
                logger.warning(
                    "Utility-based escalation evaluation failed: %s, falling back to rule-based",
                    exc,
                    exc_info=True,
                )

    if len(recall_result.relevant_tools) > 15:
        if logger:
            logger.debug(
                "Escalation triggered: too many candidates (%s)",
                len(recall_result.relevant_tools),
            )
        return True, manager

    if risk_level in ["write", "publish"]:
        if logger:
            logger.debug("Escalation triggered: high risk level (%s)", risk_level)
        return True, manager

    if recall_result.confidence and recall_result.confidence < 0.6:
        if logger:
            logger.debug(
                "Escalation triggered: low confidence (%s)",
                recall_result.confidence,
            )
        return True, manager

    if user_message and is_ambiguous_message(user_message):
        if logger:
            logger.debug("Escalation triggered: ambiguous message")
        return True, manager

    return False, manager
