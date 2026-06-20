"""Pure decision synthesis helpers for the coordinator facade."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.app.core.runtime_port import ExecutionProfile
from backend.app.services.decision.coordinator_models import (
    CostGovernanceDecision,
    IntentRoutingDecision,
    MemoryRecommendation,
    NodeGovernanceDecision,
    PlaybookPreflightResult,
    PolicyDecision,
    UnifiedDecisionResult,
)


def build_execution_profile(
    *,
    intent_decision: IntentRoutingDecision,
    playbook_preflight_result: Optional[PlaybookPreflightResult],
    cost_governance_decision: Optional[CostGovernanceDecision],
) -> ExecutionProfile:
    execution_mode = "simple"
    requires_human_approval = False
    side_effect_level = "low"

    if intent_decision.execution_profile_hint == "human_review":
        execution_mode = "durable"
        requires_human_approval = True
        side_effect_level = "high"
    elif intent_decision.execution_profile_hint == "durable":
        execution_mode = "durable"
        requires_human_approval = False
        side_effect_level = "low"

    if cost_governance_decision and not cost_governance_decision.approved:
        execution_mode = "simple"
        side_effect_level = "low"
        requires_human_approval = False

    return ExecutionProfile(
        execution_mode=execution_mode,
        supports_resume=(execution_mode == "durable"),
        requires_human_approval=requires_human_approval,
        side_effect_level=side_effect_level,
        required_capabilities=[],
    )


def synthesize_decision(
    *,
    intent_decision: IntentRoutingDecision,
    playbook_preflight_result: Optional[PlaybookPreflightResult],
    node_governance_decision: Optional[NodeGovernanceDecision],
    cost_governance_decision: Optional[CostGovernanceDecision],
    memory_recommendation: Optional[MemoryRecommendation],
    policy_decision: Optional[PolicyDecision],
    context: Dict[str, Any],
) -> UnifiedDecisionResult:
    if all_layers_agree(
        intent_decision=intent_decision,
        playbook_preflight_result=playbook_preflight_result,
        node_governance_decision=node_governance_decision,
        cost_governance_decision=cost_governance_decision,
        policy_decision=policy_decision,
    ):
        selected_playbook = intent_decision.recommended_playbook_code
        execution_profile = build_execution_profile(
            intent_decision=intent_decision,
            playbook_preflight_result=playbook_preflight_result,
            cost_governance_decision=cost_governance_decision,
        )
        return UnifiedDecisionResult(
            selected_playbook_code=selected_playbook,
            execution_profile=execution_profile,
            intent_contribution=intent_decision,
            playbook_contribution=playbook_preflight_result,
            node_governance_contribution=node_governance_decision,
            cost_governance_contribution=cost_governance_decision,
            memory_contribution=memory_recommendation,
            policy_contribution=policy_decision,
            can_auto_execute=True,
        )

    if playbook_preflight_result and playbook_preflight_result.status == "reject":
        if playbook_preflight_result.recommended_alternatives:
            selected_playbook = playbook_preflight_result.recommended_alternatives[0]
            execution_profile = build_execution_profile(
                intent_decision=intent_decision,
                playbook_preflight_result=playbook_preflight_result,
                cost_governance_decision=cost_governance_decision,
            )
            return UnifiedDecisionResult(
                selected_playbook_code=selected_playbook,
                execution_profile=execution_profile,
                intent_contribution=intent_decision,
                playbook_contribution=playbook_preflight_result,
                node_governance_contribution=node_governance_decision,
                cost_governance_contribution=cost_governance_decision,
                memory_contribution=memory_recommendation,
                policy_contribution=policy_decision,
                requires_user_approval=True,
            )

    if (
        playbook_preflight_result
        and playbook_preflight_result.status == "need_clarification"
    ):
        default_profile = ExecutionProfile(
            execution_mode="simple",
            supports_resume=False,
            requires_human_approval=False,
            side_effect_level="none",
        )
        return UnifiedDecisionResult(
            selected_playbook_code=None,
            execution_profile=default_profile,
            intent_contribution=intent_decision,
            playbook_contribution=playbook_preflight_result,
            node_governance_contribution=node_governance_decision,
            cost_governance_contribution=cost_governance_decision,
            memory_contribution=memory_recommendation,
            policy_contribution=policy_decision,
            requires_user_approval=True,
        )

    if cost_governance_decision and not cost_governance_decision.approved:
        downgraded_profile = build_execution_profile(
            intent_decision=intent_decision,
            playbook_preflight_result=playbook_preflight_result,
            cost_governance_decision=cost_governance_decision,
        )
        return UnifiedDecisionResult(
            selected_playbook_code=intent_decision.recommended_playbook_code,
            execution_profile=downgraded_profile,
            intent_contribution=intent_decision,
            playbook_contribution=playbook_preflight_result,
            node_governance_contribution=node_governance_decision,
            cost_governance_contribution=cost_governance_decision,
            memory_contribution=memory_recommendation,
            policy_contribution=policy_decision,
            requires_user_approval=True,
        )

    if policy_decision and not policy_decision.approved:
        default_profile = ExecutionProfile(
            execution_mode="simple",
            supports_resume=False,
            requires_human_approval=False,
            side_effect_level="none",
        )
        return UnifiedDecisionResult(
            selected_playbook_code=None,
            execution_profile=default_profile,
            intent_contribution=intent_decision,
            playbook_contribution=playbook_preflight_result,
            node_governance_contribution=node_governance_decision,
            cost_governance_contribution=cost_governance_decision,
            memory_contribution=memory_recommendation,
            policy_contribution=policy_decision,
            requires_user_approval=False,
        )

    selected_playbook = intent_decision.recommended_playbook_code
    execution_profile = build_execution_profile(
        intent_decision=intent_decision,
        playbook_preflight_result=playbook_preflight_result,
        cost_governance_decision=cost_governance_decision,
    )
    return UnifiedDecisionResult(
        selected_playbook_code=selected_playbook,
        execution_profile=execution_profile,
        intent_contribution=intent_decision,
        playbook_contribution=playbook_preflight_result,
        node_governance_contribution=node_governance_decision,
        cost_governance_contribution=cost_governance_decision,
        memory_contribution=memory_recommendation,
        policy_contribution=policy_decision,
        requires_user_approval=True,
    )


def all_layers_agree(
    *,
    intent_decision: IntentRoutingDecision,
    playbook_preflight_result: Optional[PlaybookPreflightResult],
    node_governance_decision: Optional[NodeGovernanceDecision],
    cost_governance_decision: Optional[CostGovernanceDecision],
    policy_decision: Optional[PolicyDecision],
) -> bool:
    if not intent_decision.recommended_playbook_code:
        return False
    if playbook_preflight_result and playbook_preflight_result.status != "accept":
        return False
    if node_governance_decision and not node_governance_decision.approved:
        return False
    if cost_governance_decision and not cost_governance_decision.approved:
        return False
    if policy_decision and not policy_decision.approved:
        return False
    return True


def detect_conflicts(decision_result: UnifiedDecisionResult) -> List[Dict[str, Any]]:
    conflicts: List[Dict[str, Any]] = []
    if (
        decision_result.playbook_contribution
        and decision_result.playbook_contribution.status == "reject"
        and decision_result.selected_playbook_code
    ):
        conflicts.append(
            {
                "type": "playbook_rejection",
                "layer1": "intent",
                "layer2": "playbook",
                "description": (
                    "Intent recommends "
                    f"{decision_result.selected_playbook_code}, "
                    "but Playbook Preflight rejects"
                ),
            }
        )
    if (
        decision_result.cost_governance_contribution
        and not decision_result.cost_governance_contribution.approved
        and decision_result.selected_playbook_code
    ):
        conflicts.append(
            {
                "type": "cost_exceeded",
                "layer1": "intent",
                "layer2": "cost_governance",
                "description": (
                    "Intent recommends execution, but Cost Governance rejects "
                    "due to cost limits"
                ),
            }
        )
    return conflicts


def resolve_conflicts(conflicts: List[Dict[str, Any]]) -> Optional[str]:
    if not conflicts:
        return None
    for conflict in conflicts:
        if conflict["type"] == "playbook_rejection":
            return "use_alternative_playbook"
        if conflict["type"] == "cost_exceeded":
            return "downgrade_execution_profile"
    return "require_user_approval"


def can_auto_execute(decision_result: UnifiedDecisionResult) -> bool:
    return bool(
        decision_result.selected_playbook_code
        and not decision_result.conflicts
        and not decision_result.requires_user_approval
    )


def requires_user_approval(decision_result: UnifiedDecisionResult) -> bool:
    if decision_result.conflicts:
        return True
    if (
        decision_result.playbook_contribution
        and decision_result.playbook_contribution.status == "need_clarification"
    ):
        return True
    if (
        decision_result.cost_governance_contribution
        and not decision_result.cost_governance_contribution.approved
    ):
        return True
    if decision_result.policy_contribution and not decision_result.policy_contribution.approved:
        return True
    if not decision_result.intent_contribution.is_overridable:
        return True
    return False
