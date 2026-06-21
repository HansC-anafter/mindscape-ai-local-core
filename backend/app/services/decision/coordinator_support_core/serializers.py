"""Serialization helpers for decision coordinator support."""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("backend.app.services.decision.coordinator_support")


def serialize_playbook_contribution(
    playbook_contribution: Any,
) -> Optional[Dict[str, Any]]:
    """Serialize PlaybookPreflightResult with a stable minimum schema."""
    if not playbook_contribution:
        return None

    result = {
        "playbook_code": getattr(playbook_contribution, "playbook_code", None),
        "status": (
            getattr(playbook_contribution.status, "value", None)
            if hasattr(playbook_contribution, "status") and playbook_contribution.status
            else (
                getattr(playbook_contribution, "status", None)
                if isinstance(getattr(playbook_contribution, "status", None), str)
                else None
            )
        ),
        "accepted": getattr(playbook_contribution, "accepted", False),
    }
    if hasattr(playbook_contribution, "missing_inputs"):
        result["missing_inputs"] = playbook_contribution.missing_inputs or []
    if hasattr(playbook_contribution, "clarification_questions"):
        result["clarification_questions"] = (
            playbook_contribution.clarification_questions or []
        )
    if hasattr(playbook_contribution, "rejection_reason"):
        result["rejection_reason"] = playbook_contribution.rejection_reason
    if hasattr(playbook_contribution, "recommended_alternatives"):
        result["recommended_alternatives"] = (
            playbook_contribution.recommended_alternatives or []
        )
    if hasattr(playbook_contribution, "recommended_orchestration"):
        result["recommended_orchestration"] = (
            playbook_contribution.recommended_orchestration
        )
    return result


def serialize_governance_contribution(contribution: Any) -> Optional[Dict[str, Any]]:
    """Serialize arbitrary governance contributions defensively."""
    if not contribution:
        return None
    try:
        return contribution.__dict__ if hasattr(contribution, "__dict__") else None
    except Exception as exc:
        logger.warning("Failed to serialize governance contribution: %s", exc)
        return None


def serialize_conflict(conflict: Any) -> Dict[str, Any]:
    """Serialize conflicts coming from dataclasses or dicts."""
    if hasattr(conflict, "__dict__"):
        return conflict.__dict__
    if isinstance(conflict, dict):
        return conflict
    return {"type": str(type(conflict)), "value": str(conflict)}


def _serialize_intent_contribution(decision_result: Any) -> Dict[str, Any]:
    contribution = decision_result.intent_contribution
    if hasattr(contribution, "to_dict"):
        return contribution.to_dict()
    suggested = getattr(contribution, "suggested_playbook", None)
    return {
        "decision_id": getattr(contribution, "decision_id", decision_result.decision_id),
        "suggested_playbook": {
            "playbook_code": suggested.playbook_code if suggested else None,
            "confidence": suggested.confidence if suggested else 0.0,
            "rationale": suggested.rationale if suggested else "",
            "is_orchestration": suggested.is_orchestration if suggested else False,
            "orchestration_steps": suggested.orchestration_steps if suggested else [],
        }
        if suggested
        else None,
        "alternatives": [
            {
                "playbook_code": alt.playbook_code,
                "confidence": alt.confidence,
                "rationale": alt.rationale,
                "is_orchestration": alt.is_orchestration,
            }
            for alt in getattr(contribution, "alternatives", []) or []
        ],
        "confidence": getattr(contribution, "confidence", 0.0),
        "rationale": getattr(contribution, "rationale", ""),
        "decision_method": getattr(
            contribution, "decision_method", "unified_decision_coordinator"
        ),
        "execution_profile_hint": getattr(contribution, "execution_profile_hint", "fast"),
    }


def build_final_decision_dict(decision_result: Any) -> Dict[str, Any]:
    """Serialize the coordinator output into IntentLog.final_decision."""
    execution_profile = decision_result.execution_profile
    return {
        "selected_playbook_code": decision_result.selected_playbook_code,
        "execution_profile": execution_profile.model_dump()
        if hasattr(execution_profile, "model_dump")
        else execution_profile.__dict__,
        "intent_contribution": _serialize_intent_contribution(decision_result),
        "playbook_contribution": serialize_playbook_contribution(
            decision_result.playbook_contribution
        ),
        "node_governance_contribution": serialize_governance_contribution(
            decision_result.node_governance_contribution
        ),
        "cost_governance_contribution": serialize_governance_contribution(
            decision_result.cost_governance_contribution
        ),
        "memory_contribution": serialize_governance_contribution(
            decision_result.memory_contribution
        ),
        "policy_contribution": serialize_governance_contribution(
            decision_result.policy_contribution
        ),
        "conflicts": [serialize_conflict(c) for c in decision_result.conflicts]
        if decision_result.conflicts
        else [],
        "resolution_strategy": decision_result.resolution_strategy,
        "can_auto_execute": decision_result.can_auto_execute,
        "requires_user_approval": decision_result.requires_user_approval,
    }
