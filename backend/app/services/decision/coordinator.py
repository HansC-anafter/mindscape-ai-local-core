"""
Decision Coordinator

Integrates decisions from Intent, Playbook, Node Governance, Cost Governance,
Memory, and Policy layers into a unified decision pipeline.

The coordinator synthesizes inputs from multiple governance layers to produce
a single, traceable, and learnable decision result.

Class name: UnifiedDecisionCoordinator (also available as DecisionCoordinator alias)
"""

import logging
import uuid
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime

from backend.app.core.runtime_port import ExecutionProfile
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

logger = logging.getLogger(__name__)


@dataclass
class PlaybookCandidate:
    """Candidate Playbook (unified schema)"""
    playbook_code: str
    confidence: float  # 0.0-1.0
    rationale: str
    required_inputs: List[str] = field(default_factory=list)
    missing_inputs: List[str] = field(default_factory=list)
    is_orchestration: bool = False  # True for complete workflow playbooks
    orchestration_steps: List[str] = field(default_factory=list)  # Sub-playbooks if orchestration


@dataclass
class IntentRoutingDecision:
    """
    Intent layer routing decision (unified schema, traceable, overridable, learnable)
    """

    # Core identifiers
    decision_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    intent_id: Optional[str] = None  # If linked to an IntentCard

    # Primary recommendation
    suggested_playbook: Optional[PlaybookCandidate] = None

    # Alternatives
    alternatives: List[PlaybookCandidate] = field(default_factory=list)

    # Decision metadata
    confidence: float = 0.0  # Overall confidence (0.0-1.0)
    rationale: str = ""  # Why this playbook was selected
    decision_method: str = ""  # "rule_based" | "llm_based" | "intent_card" | "user_override" | "intent_pipeline"

    # Execution context
    execution_profile_hint: str = "fast"  # "fast" | "durable" | "human_review" (maps to ExecutionProfile)
    required_inputs: List[str] = field(default_factory=list)
    missing_inputs: List[str] = field(default_factory=list)

    # Override and learning
    user_override: Optional[PlaybookCandidate] = None  # If user manually selected different playbook
    override_reason: Optional[str] = None
    should_learn: bool = False  # Whether to update intent routing memory

    # Traceability
    timestamp: datetime = field(default_factory=datetime.utcnow)
    source_intent_analysis: Optional[Dict[str, Any]] = None  # Link back to IntentAnalysisResult
    workspace_id: Optional[str] = None
    project_id: Optional[str] = None
    profile_id: Optional[str] = None

    # Convenience properties (backward compatibility)
    @property
    def recommended_playbook_code(self) -> Optional[str]:
        """Convenience property: get recommended playbook_code"""
        return self.suggested_playbook.playbook_code if self.suggested_playbook else None

    @property
    def is_overridable(self) -> bool:
        """Convenience property: whether override is allowed (default True)"""
        return True  # Default overridable unless explicitly marked

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary (for serialization to IntentLog.final_decision)"""
        return {
            "decision_id": self.decision_id,
            "intent_id": self.intent_id,
            "suggested_playbook": {
                "playbook_code": self.suggested_playbook.playbook_code if self.suggested_playbook else None,
                "confidence": self.suggested_playbook.confidence if self.suggested_playbook else 0.0,
                "rationale": self.suggested_playbook.rationale if self.suggested_playbook else "",
                "is_orchestration": self.suggested_playbook.is_orchestration if self.suggested_playbook else False,
                "orchestration_steps": self.suggested_playbook.orchestration_steps if self.suggested_playbook else [],
            } if self.suggested_playbook else None,
            "alternatives": [
                {
                    "playbook_code": alt.playbook_code,
                    "confidence": alt.confidence,
                    "rationale": alt.rationale,
                    "is_orchestration": alt.is_orchestration,
                }
                for alt in self.alternatives
            ],
            "confidence": self.confidence,
            "rationale": self.rationale,
            "decision_method": self.decision_method,
            "execution_profile_hint": self.execution_profile_hint,
            "required_inputs": self.required_inputs,
            "missing_inputs": self.missing_inputs,
            "user_override": {
                "playbook_code": self.user_override.playbook_code,
                "confidence": self.user_override.confidence,
                "rationale": self.user_override.rationale,
            } if self.user_override else None,
            "override_reason": self.override_reason,
            "should_learn": self.should_learn,
            "timestamp": self.timestamp.isoformat(),
            "workspace_id": self.workspace_id,
            "project_id": self.project_id,
            "profile_id": self.profile_id,
        }

    @classmethod
    def from_intent_analysis_result(
        cls,
        intent_result: Any,  # IntentAnalysisResult
        workspace_id: Optional[str] = None,
        project_id: Optional[str] = None,
        profile_id: Optional[str] = None
    ) -> "IntentRoutingDecision":
        """Build IntentRoutingDecision from IntentAnalysisResult"""
        suggested_playbook = None
        if intent_result.selected_playbook_code:
            suggested_playbook = PlaybookCandidate(
                playbook_code=intent_result.selected_playbook_code,
                confidence=intent_result.playbook_confidence,
                rationale=f"Selected by IntentPipeline (confidence: {intent_result.playbook_confidence:.2f})",
                is_orchestration=intent_result.is_multi_step,
                orchestration_steps=[
                    step.get("playbook_code", "")
                    for step in intent_result.workflow_steps
                ] if intent_result.workflow_steps else []
            )

        return cls(
            decision_id=str(uuid.uuid4()),
            suggested_playbook=suggested_playbook,
            alternatives=[],
            confidence=intent_result.playbook_confidence,
            rationale=f"Intent analysis result: {intent_result.task_domain.value if hasattr(intent_result.task_domain, 'value') and intent_result.task_domain else 'unknown'}",
            decision_method="intent_pipeline",
            execution_profile_hint="fast",  # Default, can be adjusted as needed
            source_intent_analysis={
                "interaction_type": intent_result.interaction_type.value if hasattr(intent_result.interaction_type, 'value') and intent_result.interaction_type else None,
                "task_domain": intent_result.task_domain.value if hasattr(intent_result.task_domain, 'value') and intent_result.task_domain else None,
                "selected_playbook_code": intent_result.selected_playbook_code,
                "playbook_confidence": intent_result.playbook_confidence,
                "is_multi_step": intent_result.is_multi_step,
            },
            workspace_id=workspace_id,
            project_id=project_id,
            profile_id=profile_id
        )


# Stub types (will be imported from governance.stubs when available)
# These are placeholders to allow type hints
@dataclass
class PlaybookPreflightResult:
    """Playbook Preflight result (minimum required fields: playbook_code, status, accepted)"""
    playbook_code: str
    status: str  # "accept" | "reject" | "need_clarification"
    accepted: bool
    missing_inputs: List[str] = field(default_factory=list)
    clarification_questions: List[str] = field(default_factory=list)
    rejection_reason: Optional[str] = None
    recommended_alternatives: List[str] = field(default_factory=list)
    recommended_orchestration: Optional[str] = None


@dataclass
class NodeGovernanceDecision:
    """Node governance decision (minimum required field: approved)"""
    approved: bool
    reason: Optional[str] = None


@dataclass
class CostGovernanceDecision:
    """Cost governance decision (minimum required field: approved)"""
    approved: bool
    reason: Optional[str] = None
    estimated_cost: Optional[float] = None


@dataclass
class PolicyDecision:
    """Policy decision (minimum required field: approved)"""
    approved: bool
    reason: Optional[str] = None


@dataclass
class MemoryRecommendation:
    """Memory recommendation (optional)"""
    recommended_playbook_code: Optional[str] = None
    confidence: float = 0.0


@dataclass
class UnifiedDecisionResult:
    """Unified decision result from all governance layers"""
    selected_playbook_code: Optional[str]
    execution_profile: ExecutionProfile
    intent_contribution: IntentRoutingDecision
    playbook_contribution: Optional[PlaybookPreflightResult] = None
    node_governance_contribution: Optional[NodeGovernanceDecision] = None
    cost_governance_contribution: Optional[CostGovernanceDecision] = None
    memory_contribution: Optional[MemoryRecommendation] = None
    policy_contribution: Optional[PolicyDecision] = None
    conflicts: List[Dict[str, Any]] = field(default_factory=list)
    resolution_strategy: Optional[str] = None
    can_auto_execute: bool = False
    requires_user_approval: bool = False
    decision_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)


class UnifiedDecisionCoordinator:
    """Unified decision coordinator"""

    def __init__(
        self,
        intent_pipeline: Any,  # IntentPipeline
        playbook_preflight: Any,  # PlaybookPreflight
        node_governance: Optional[Any] = None,  # NodeGovernance
        cost_governance: Optional[Any] = None,  # CostGovernance
        memory_service: Optional[Any] = None,  # MemoryService
        policy_service: Optional[Any] = None  # PolicyService
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
        cost_governance_decision: Optional[CostGovernanceDecision]
    ) -> ExecutionProfile:
        """
        Build ExecutionProfile (using existing ExecutionProfile structure)
        """
        # Initialize variables (avoid undefined errors)
        execution_mode = "simple"  # Default
        requires_human_approval = False
        side_effect_level = "low"  # Default

        # Determine initial values based on execution_profile_hint
        if intent_decision.execution_profile_hint == "human_review":
            execution_mode = "durable"  # human_review also needs durable runtime
            requires_human_approval = True
            side_effect_level = "high"
        elif intent_decision.execution_profile_hint == "durable":
            execution_mode = "durable"
            requires_human_approval = False
            side_effect_level = "low"  # Note: ExecutionProfile only allows "none"|"low"|"high", no "medium"
        else:  # "fast"
            execution_mode = "simple"
            requires_human_approval = False
            side_effect_level = "low"

        # Downgrade based on cost_governance
        if cost_governance_decision and not cost_governance_decision.approved:
            # Cost exceeded, downgrade to simple mode
            execution_mode = "simple"
            side_effect_level = "low"
            requires_human_approval = False

        return ExecutionProfile(
            execution_mode=execution_mode,
            supports_resume=(execution_mode == "durable"),
            requires_human_approval=requires_human_approval,
            side_effect_level=side_effect_level,  # Must be "none"|"low"|"high"
            required_capabilities=[]  # Can be obtained from playbook
        )

    async def make_unified_decision(
        self,
        user_input: str,
        workspace_id: str,
        project_id: Optional[str] = None,
        user_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> UnifiedDecisionResult:
        """
        Make unified decision integrating all governance layers

        This is the main entry point for unified decision coordination.
        """
        # Intent layer analysis
        intent_result = await self.intent_pipeline.analyze(
            user_input=user_input,
            profile_id=user_id or "",
            workspace_id=workspace_id,
            project_id=project_id,
            context=context
        )

        # Convert to IntentRoutingDecision
        intent_decision = IntentRoutingDecision.from_intent_analysis_result(
            intent_result=intent_result,
            workspace_id=workspace_id,
            project_id=project_id,
            profile_id=user_id
        )

        # Playbook layer preflight
        playbook_preflight_result = None
        if intent_decision.recommended_playbook_code:
            playbook_preflight_result = await self.playbook_preflight.preflight(
                playbook_code=intent_decision.recommended_playbook_code,
                intent_decision=intent_decision,
                context=context or {}
            )

        # Node governance layer check
        node_governance_decision = None
        if self.node_governance:
            node_governance_decision = await self.node_governance.check(
                playbook_code=intent_decision.recommended_playbook_code,
                workspace_id=workspace_id,
                context=context or {}
            )

        # Cost governance layer check
        cost_governance_decision = None
        if self.cost_governance:
            # Build temporary execution_profile for cost check
            temp_profile = self._build_execution_profile(
                intent_decision,
                playbook_preflight_result,
                None  # No cost_governance yet
            )
            cost_governance_decision = await self.cost_governance.check(
                playbook_code=intent_decision.recommended_playbook_code,
                execution_profile=temp_profile,
                workspace_id=workspace_id,
                context=context or {}
            )

        # Memory layer recommendation
        memory_recommendation = None
        if self.memory_service:
            memory_recommendation = await self.memory_service.get_recommendation(
                user_input=user_input,
                workspace_id=workspace_id,
                project_id=project_id
            )

        # Policy layer check
        policy_decision = None
        if self.policy_service:
            policy_decision = await self.policy_service.check(
                playbook_code=intent_decision.recommended_playbook_code,
                workspace_id=workspace_id,
                user_id=user_id,
                context=context or {}
            )

        # Synthesize decision from all governance layers
        decision_result = await self._synthesize_decision(
            intent_decision=intent_decision,
            playbook_preflight_result=playbook_preflight_result,
            node_governance_decision=node_governance_decision,
            cost_governance_decision=cost_governance_decision,
            memory_recommendation=memory_recommendation,
            policy_decision=policy_decision,
            context=context or {}
        )

        # Conflict resolution
        conflicts = self._detect_conflicts(decision_result)
        if conflicts:
            decision_result.conflicts = conflicts
            decision_result.resolution_strategy = self._resolve_conflicts(conflicts)

        # Auto-execute judgment
        decision_result.can_auto_execute = self._can_auto_execute(decision_result)

        # User override support
        decision_result.requires_user_approval = self._requires_user_approval(decision_result)

        # Store decision to IntentLog
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
            policy_decision=policy_decision
        )

        # Record governance decisions to database (Cloud environment)
        await self._record_governance_decisions(
            workspace_id=workspace_id,
            execution_id=None,  # Will be set when execution starts
            node_governance_decision=node_governance_decision,
            cost_governance_decision=cost_governance_decision,
            policy_decision=policy_decision,
            playbook_preflight_result=playbook_preflight_result,
            playbook_code=intent_decision.recommended_playbook_code
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
        context: Dict[str, Any]
    ) -> UnifiedDecisionResult:
        """Synthesize decision from all layers"""

        # Strategy 1: If all layers agree, forward execution
        if self._all_layers_agree(
            intent_decision,
            playbook_preflight_result,
            node_governance_decision,
            cost_governance_decision,
            policy_decision
        ):
            selected_playbook = intent_decision.recommended_playbook_code
            execution_profile = self._build_execution_profile(
                intent_decision,
                playbook_preflight_result,
                cost_governance_decision
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
                can_auto_execute=True
            )

        # Strategy 2: If Playbook Preflight rejects, use recommended alternatives
        if playbook_preflight_result and playbook_preflight_result.status == "reject":
            if playbook_preflight_result.recommended_alternatives:
                selected_playbook = playbook_preflight_result.recommended_alternatives[0]
                execution_profile = self._build_execution_profile(
                    intent_decision,
                    playbook_preflight_result,
                    cost_governance_decision
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
                    requires_user_approval=True  # Because of rejection, need user confirmation
                )

        # Strategy 3: If Playbook Preflight needs clarification, return clarification questions
        if playbook_preflight_result and playbook_preflight_result.status == "need_clarification":
            default_profile = ExecutionProfile(
                execution_mode="simple",
                supports_resume=False,
                requires_human_approval=False,
                side_effect_level="none"
            )
            return UnifiedDecisionResult(
                selected_playbook_code=None,  # Not selected yet, waiting for clarification
                execution_profile=default_profile,
                intent_contribution=intent_decision,
                playbook_contribution=playbook_preflight_result,
                node_governance_contribution=node_governance_decision,
                cost_governance_contribution=cost_governance_decision,
                memory_contribution=memory_recommendation,
                policy_contribution=policy_decision,
                requires_user_approval=True  # Need clarification
            )

        # Strategy 4: If cost governance rejects, downgrade execution profile
        if cost_governance_decision and not cost_governance_decision.approved:
            downgraded_profile = self._build_execution_profile(
                intent_decision,
                playbook_preflight_result,
                cost_governance_decision  # Will trigger downgrade logic
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
                requires_user_approval=True  # Because of downgrade, need user confirmation
            )

        # Strategy 5: If Policy layer rejects, reject execution
        if policy_decision and not policy_decision.approved:
            default_profile = ExecutionProfile(
                execution_mode="simple",
                supports_resume=False,
                requires_human_approval=False,
                side_effect_level="none"
            )
            return UnifiedDecisionResult(
                selected_playbook_code=None,
                execution_profile=default_profile,  # Must provide ExecutionProfile
                intent_contribution=intent_decision,
                playbook_contribution=playbook_preflight_result,
                node_governance_contribution=node_governance_decision,
                cost_governance_contribution=cost_governance_decision,
                memory_contribution=memory_recommendation,
                policy_contribution=policy_decision,
                requires_user_approval=False  # Policy rejects, execution not allowed
            )

        # Default: Use Intent's recommendation
        selected_playbook = intent_decision.recommended_playbook_code
        execution_profile = self._build_execution_profile(
            intent_decision,
            playbook_preflight_result,
            cost_governance_decision
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
            requires_user_approval=True  # Default requires user confirmation
        )

    def _all_layers_agree(
        self,
        intent_decision: IntentRoutingDecision,
        playbook_preflight_result: Optional[PlaybookPreflightResult],
        node_governance_decision: Optional[NodeGovernanceDecision],
        cost_governance_decision: Optional[CostGovernanceDecision],
        policy_decision: Optional[PolicyDecision]
    ) -> bool:
        """Check if all layers agree"""
        # Intent layer has recommendation
        if not intent_decision.recommended_playbook_code:
            return False

        # Playbook layer accepts
        if playbook_preflight_result:
            if playbook_preflight_result.status != "accept":
                return False

        # Node governance layer approves (if exists)
        if node_governance_decision and not node_governance_decision.approved:
            return False

        # Cost governance layer approves (if exists)
        if cost_governance_decision and not cost_governance_decision.approved:
            return False

        # Policy layer approves (if exists)
        if policy_decision and not policy_decision.approved:
            return False

        return True

    def _detect_conflicts(self, decision_result: UnifiedDecisionResult) -> List[Dict[str, Any]]:
        """Detect conflicts between layers"""
        conflicts = []

        # Check if playbook preflight rejects but intent recommends
        if (decision_result.playbook_contribution and
            decision_result.playbook_contribution.status == "reject" and
            decision_result.selected_playbook_code):
            conflicts.append({
                "type": "playbook_rejection",
                "layer1": "intent",
                "layer2": "playbook",
                "description": f"Intent recommends {decision_result.selected_playbook_code}, but Playbook Preflight rejects"
            })

        # Check if cost governance rejects but other layers approve
        if (decision_result.cost_governance_contribution and
            not decision_result.cost_governance_contribution.approved and
            decision_result.selected_playbook_code):
            conflicts.append({
                "type": "cost_exceeded",
                "layer1": "intent",
                "layer2": "cost_governance",
                "description": "Intent recommends execution, but Cost Governance rejects due to cost limits"
            })

        return conflicts

    def _resolve_conflicts(self, conflicts: List[Dict[str, Any]]) -> str:
        """Resolve conflicts between layers"""
        if not conflicts:
            return None

        # Simple resolution: prioritize playbook preflight and cost governance
        for conflict in conflicts:
            if conflict["type"] == "playbook_rejection":
                return "use_alternative_playbook"
            elif conflict["type"] == "cost_exceeded":
                return "downgrade_execution_profile"

        return "require_user_approval"

    def _can_auto_execute(self, decision_result: UnifiedDecisionResult) -> bool:
        """Check if decision can be auto-executed"""
        # Can auto-execute if all layers agree and no conflicts
        if (decision_result.selected_playbook_code and
            not decision_result.conflicts and
            not decision_result.requires_user_approval):
            return True
        return False

    def _requires_user_approval(self, decision_result: UnifiedDecisionResult) -> bool:
        """Check if user approval is required"""
        # Require approval if there are conflicts or if intent_decision is not overridable
        if decision_result.conflicts:
            return True

        # Require approval if playbook preflight needs clarification
        if (decision_result.playbook_contribution and
            decision_result.playbook_contribution.status == "need_clarification"):
            return True

        # Require approval if cost governance downgrades
        if (decision_result.cost_governance_contribution and
            not decision_result.cost_governance_contribution.approved):
            return True

        # Require approval if policy rejects
        if (decision_result.policy_contribution and
            not decision_result.policy_contribution.approved):
            return True

        # Default: require approval if intent_decision is not overridable
        if not decision_result.intent_contribution.is_overridable:
            return True

        return False

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
        policy_decision: Optional[Any]
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

    def _serialize_playbook_contribution(self, playbook_contribution: Any) -> Optional[Dict[str, Any]]:
        """Serialize PlaybookPreflightResult (handle None and minimum required fields)."""
        return serialize_playbook_contribution(playbook_contribution)

    def _serialize_governance_contribution(self, contribution: Any) -> Optional[Dict[str, Any]]:
        """Serialize governance layer contribution (handle None)."""
        return serialize_governance_contribution(contribution)

    def _serialize_conflict(self, conflict: Any) -> Dict[str, Any]:
        """Serialize conflict (handle different types)."""
        return serialize_conflict(conflict)

    def _emit_decision_required_event(
        self,
        store: Any,  # MindscapeStore
        decision_result: UnifiedDecisionResult,
        intent_log: Any,  # IntentLog
        workspace_id: str,
        project_id: Optional[str],
        user_id: Optional[str]
    ) -> None:
        """Emit DECISION_REQUIRED event for Human-in-the-loop (ReAct: Ask Human)."""
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
        decision_result: UnifiedDecisionResult
    ) -> Optional[Dict[str, Any]]:
        """Build governance_decision payload for event."""
        return build_governance_decision_payload(self, decision_result)

    async def _record_governance_decisions(
        self,
        workspace_id: str,
        execution_id: Optional[str],
        node_governance_decision: Optional[NodeGovernanceDecision],
        cost_governance_decision: Optional[CostGovernanceDecision],
        policy_decision: Optional[PolicyDecision],
        playbook_preflight_result: Optional[PlaybookPreflightResult],
        playbook_code: Optional[str]
    ) -> None:
        """Record governance decisions to database (Cloud environment)."""
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
        store: Any,  # MindscapeStore (will be set when storing decision)
        intent_decision: IntentRoutingDecision,
        intent_result: Any,  # IntentAnalysisResult
        workspace_id: str,
        project_id: Optional[str],
        user_id: Optional[str]
    ) -> None:
        """Emit BRANCH_PROPOSED event for Tree of Thoughts (ToT)."""
        emit_branch_proposed_event(
            store=store,
            intent_decision=intent_decision,
            workspace_id=workspace_id,
            project_id=project_id,
            user_id=user_id,
        )
