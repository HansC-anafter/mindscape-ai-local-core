"""
Decision Coordinator

Integrates decisions from Intent, Playbook, Node Governance, Cost Governance,
Memory, and Policy layers into a unified decision pipeline.

Class name: UnifiedDecisionCoordinator (also available as DecisionCoordinator alias)
"""

from typing import Any, Dict, Optional

from backend.app.core.runtime_port import ExecutionProfile
from backend.app.services.decision.coordinator_decision_logic import (
    all_layers_agree,
    build_execution_profile,
    can_auto_execute,
    detect_conflicts,
    requires_user_approval,
    resolve_conflicts,
    synthesize_decision,
)
from backend.app.services.decision.coordinator_models import (
    CostGovernanceDecision,
    IntentRoutingDecision,
    MemoryRecommendation,
    NodeGovernanceDecision,
    PlaybookCandidate,
    PlaybookPreflightResult,
    PolicyDecision,
    UnifiedDecisionResult,
)
from backend.app.services.decision.coordinator_support import (
    build_governance_decision_payload,
    emit_branch_proposed_event,
    emit_decision_required_event,
    record_governance_decisions,
    serialize_conflict,
    serialize_governance_contribution,
    serialize_playbook_contribution,
    store_decision_to_intent_log,
)


class UnifiedDecisionCoordinator:
    """Unified decision coordinator."""

    def __init__(
        self,
        intent_pipeline: Any,
        playbook_preflight: Any,
        node_governance: Optional[Any] = None,
        cost_governance: Optional[Any] = None,
        memory_service: Optional[Any] = None,
        policy_service: Optional[Any] = None,
    ):
        self.intent_pipeline = intent_pipeline
        self.playbook_preflight = playbook_preflight
        self.node_governance = node_governance
        self.cost_governance = cost_governance
        self.memory_service = memory_service
        self.policy_service = policy_service

    def _build_execution_profile(
        self,
        intent_decision: IntentRoutingDecision,
        playbook_preflight_result: Optional[PlaybookPreflightResult],
        cost_governance_decision: Optional[CostGovernanceDecision],
    ) -> ExecutionProfile:
        return build_execution_profile(
            intent_decision=intent_decision,
            playbook_preflight_result=playbook_preflight_result,
            cost_governance_decision=cost_governance_decision,
        )

    async def make_unified_decision(
        self,
        user_input: str,
        workspace_id: str,
        project_id: Optional[str] = None,
        user_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> UnifiedDecisionResult:
        """Make unified decision integrating all governance layers."""
        intent_result = await self.intent_pipeline.analyze(
            user_input=user_input,
            profile_id=user_id or "",
            workspace_id=workspace_id,
            project_id=project_id,
            context=context,
        )

        intent_decision = IntentRoutingDecision.from_intent_analysis_result(
            intent_result=intent_result,
            workspace_id=workspace_id,
            project_id=project_id,
            profile_id=user_id,
        )

        playbook_preflight_result = None
        if intent_decision.recommended_playbook_code:
            playbook_preflight_result = await self.playbook_preflight.preflight(
                playbook_code=intent_decision.recommended_playbook_code,
                intent_decision=intent_decision,
                context=context or {},
            )

        node_governance_decision = None
        if self.node_governance:
            node_governance_decision = await self.node_governance.check(
                playbook_code=intent_decision.recommended_playbook_code,
                workspace_id=workspace_id,
                context=context or {},
            )

        cost_governance_decision = None
        if self.cost_governance:
            temp_profile = self._build_execution_profile(
                intent_decision,
                playbook_preflight_result,
                None,
            )
            cost_governance_decision = await self.cost_governance.check(
                playbook_code=intent_decision.recommended_playbook_code,
                execution_profile=temp_profile,
                workspace_id=workspace_id,
                context=context or {},
            )

        memory_recommendation = None
        if self.memory_service:
            memory_recommendation = await self.memory_service.get_recommendation(
                user_input=user_input,
                workspace_id=workspace_id,
                project_id=project_id,
            )

        policy_decision = None
        if self.policy_service:
            policy_decision = await self.policy_service.check(
                playbook_code=intent_decision.recommended_playbook_code,
                workspace_id=workspace_id,
                user_id=user_id,
                context=context or {},
            )

        decision_result = await self._synthesize_decision(
            intent_decision=intent_decision,
            playbook_preflight_result=playbook_preflight_result,
            node_governance_decision=node_governance_decision,
            cost_governance_decision=cost_governance_decision,
            memory_recommendation=memory_recommendation,
            policy_decision=policy_decision,
            context=context or {},
        )

        conflicts = self._detect_conflicts(decision_result)
        if conflicts:
            decision_result.conflicts = conflicts
            decision_result.resolution_strategy = self._resolve_conflicts(conflicts)

        decision_result.can_auto_execute = self._can_auto_execute(decision_result)
        decision_result.requires_user_approval = self._requires_user_approval(
            decision_result
        )

        await self._store_decision_to_intent_log(
            decision_result=decision_result,
            user_input=user_input,
            workspace_id=workspace_id,
            project_id=project_id,
            user_id=user_id,
            intent_result=intent_result,
            playbook_preflight_result=playbook_preflight_result,
            node_governance_decision=node_governance_decision,
            cost_governance_decision=cost_governance_decision,
            memory_recommendation=memory_recommendation,
            policy_decision=policy_decision,
        )

        await self._record_governance_decisions(
            workspace_id=workspace_id,
            execution_id=None,
            node_governance_decision=node_governance_decision,
            cost_governance_decision=cost_governance_decision,
            policy_decision=policy_decision,
            playbook_preflight_result=playbook_preflight_result,
            playbook_code=intent_decision.recommended_playbook_code,
        )

        return decision_result

    async def _synthesize_decision(
        self,
        intent_decision: IntentRoutingDecision,
        playbook_preflight_result: Optional[PlaybookPreflightResult],
        node_governance_decision: Optional[NodeGovernanceDecision],
        cost_governance_decision: Optional[CostGovernanceDecision],
        memory_recommendation: Optional[MemoryRecommendation],
        policy_decision: Optional[PolicyDecision],
        context: Dict[str, Any],
    ) -> UnifiedDecisionResult:
        return synthesize_decision(
            intent_decision=intent_decision,
            playbook_preflight_result=playbook_preflight_result,
            node_governance_decision=node_governance_decision,
            cost_governance_decision=cost_governance_decision,
            memory_recommendation=memory_recommendation,
            policy_decision=policy_decision,
            context=context,
        )

    def _all_layers_agree(
        self,
        intent_decision: IntentRoutingDecision,
        playbook_preflight_result: Optional[PlaybookPreflightResult],
        node_governance_decision: Optional[NodeGovernanceDecision],
        cost_governance_decision: Optional[CostGovernanceDecision],
        policy_decision: Optional[PolicyDecision],
    ) -> bool:
        return all_layers_agree(
            intent_decision=intent_decision,
            playbook_preflight_result=playbook_preflight_result,
            node_governance_decision=node_governance_decision,
            cost_governance_decision=cost_governance_decision,
            policy_decision=policy_decision,
        )

    def _detect_conflicts(
        self,
        decision_result: UnifiedDecisionResult,
    ) -> list[Dict[str, Any]]:
        return detect_conflicts(decision_result)

    def _resolve_conflicts(self, conflicts: list[Dict[str, Any]]) -> Optional[str]:
        return resolve_conflicts(conflicts)

    def _can_auto_execute(self, decision_result: UnifiedDecisionResult) -> bool:
        return can_auto_execute(decision_result)

    def _requires_user_approval(self, decision_result: UnifiedDecisionResult) -> bool:
        return requires_user_approval(decision_result)

    async def _store_decision_to_intent_log(
        self,
        decision_result: UnifiedDecisionResult,
        user_input: str,
        workspace_id: str,
        project_id: Optional[str],
        user_id: Optional[str],
        intent_result: Any,
        playbook_preflight_result: Optional[Any],
        node_governance_decision: Optional[Any],
        cost_governance_decision: Optional[Any],
        memory_recommendation: Optional[Any],
        policy_decision: Optional[Any],
    ):
        return await store_decision_to_intent_log(
            self,
            decision_result=decision_result,
            user_input=user_input,
            workspace_id=workspace_id,
            project_id=project_id,
            user_id=user_id,
            intent_result=intent_result,
            playbook_preflight_result=playbook_preflight_result,
            node_governance_decision=node_governance_decision,
            cost_governance_decision=cost_governance_decision,
            memory_recommendation=memory_recommendation,
            policy_decision=policy_decision,
        )

    def _serialize_playbook_contribution(
        self,
        playbook_contribution: Any,
    ) -> Optional[Dict[str, Any]]:
        return serialize_playbook_contribution(playbook_contribution)

    def _serialize_governance_contribution(
        self,
        contribution: Any,
    ) -> Optional[Dict[str, Any]]:
        return serialize_governance_contribution(contribution)

    def _serialize_conflict(self, conflict: Any) -> Dict[str, Any]:
        return serialize_conflict(conflict)

    def _emit_decision_required_event(
        self,
        store: Any,
        decision_result: UnifiedDecisionResult,
        intent_log: Any,
        workspace_id: str,
        project_id: Optional[str],
        user_id: Optional[str],
    ) -> None:
        emit_decision_required_event(
            self,
            store=store,
            decision_result=decision_result,
            intent_log=intent_log,
            workspace_id=workspace_id,
            project_id=project_id,
            user_id=user_id,
        )

    def _build_governance_decision_payload(
        self,
        decision_result: UnifiedDecisionResult,
    ) -> Optional[Dict[str, Any]]:
        return build_governance_decision_payload(self, decision_result)

    async def _record_governance_decisions(
        self,
        workspace_id: str,
        execution_id: Optional[str],
        node_governance_decision: Optional[NodeGovernanceDecision],
        cost_governance_decision: Optional[CostGovernanceDecision],
        policy_decision: Optional[PolicyDecision],
        playbook_preflight_result: Optional[PlaybookPreflightResult],
        playbook_code: Optional[str],
    ) -> None:
        await record_governance_decisions(
            workspace_id=workspace_id,
            execution_id=execution_id,
            node_governance_decision=node_governance_decision,
            cost_governance_decision=cost_governance_decision,
            policy_decision=policy_decision,
            playbook_preflight_result=playbook_preflight_result,
            playbook_code=playbook_code,
        )

    def _emit_branch_proposed_event(
        self,
        store: Any,
        intent_decision: IntentRoutingDecision,
        intent_result: Any,
        workspace_id: str,
        project_id: Optional[str],
        user_id: Optional[str],
    ) -> None:
        emit_branch_proposed_event(
            store=store,
            intent_decision=intent_decision,
            workspace_id=workspace_id,
            project_id=project_id,
            user_id=user_id,
        )
