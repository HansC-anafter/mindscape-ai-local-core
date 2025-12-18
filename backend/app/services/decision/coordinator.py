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
        """
        Store UnifiedDecisionResult to IntentLog.final_decision

        Actual implementation: includes existence check and retry
        """
        from backend.app.models.mindscape import IntentLog
        from backend.app.services.mindscape_store import MindscapeStore

        store = MindscapeStore()

        # Check if decision_id already exists (actual check)
        log_id = decision_result.decision_id
        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            existing_log = store.get_intent_log(log_id)
            if existing_log:
                logger.warning(
                    f"IntentLog with decision_id {log_id} already exists, "
                    f"generating new UUID (retry {retry_count + 1}/{max_retries})"
                )
                log_id = str(uuid.uuid4())
                decision_result.decision_id = log_id  # Update decision_id
                retry_count += 1
            else:
                break

        if retry_count >= max_retries:
            logger.error(
                f"Failed to generate unique IntentLog.id after {max_retries} retries, "
                f"using final attempt: {log_id}. This should be extremely rare (UUID collision)."
            )

        # Serialize UnifiedDecisionResult
        final_decision_dict = {
            # Final decision
            "selected_playbook_code": decision_result.selected_playbook_code,
            "execution_profile": decision_result.execution_profile.dict() if hasattr(decision_result.execution_profile, 'dict') else decision_result.execution_profile.__dict__,

            # Intent layer contribution (use IntentRoutingDecision.to_dict())
            "intent_contribution": decision_result.intent_contribution.to_dict() if hasattr(decision_result.intent_contribution, 'to_dict') else {
                "decision_id": getattr(decision_result.intent_contribution, 'decision_id', decision_result.decision_id),
                "suggested_playbook": {
                    "playbook_code": decision_result.intent_contribution.suggested_playbook.playbook_code if hasattr(decision_result.intent_contribution, 'suggested_playbook') and decision_result.intent_contribution.suggested_playbook else None,
                    "confidence": decision_result.intent_contribution.suggested_playbook.confidence if hasattr(decision_result.intent_contribution, 'suggested_playbook') and decision_result.intent_contribution.suggested_playbook else 0.0,
                    "rationale": decision_result.intent_contribution.suggested_playbook.rationale if hasattr(decision_result.intent_contribution, 'suggested_playbook') and decision_result.intent_contribution.suggested_playbook else "",
                    "is_orchestration": decision_result.intent_contribution.suggested_playbook.is_orchestration if hasattr(decision_result.intent_contribution, 'suggested_playbook') and decision_result.intent_contribution.suggested_playbook else False,
                    "orchestration_steps": decision_result.intent_contribution.suggested_playbook.orchestration_steps if hasattr(decision_result.intent_contribution, 'suggested_playbook') and decision_result.intent_contribution.suggested_playbook else [],
                } if hasattr(decision_result.intent_contribution, 'suggested_playbook') and decision_result.intent_contribution.suggested_playbook else None,
                "alternatives": [
                    {
                        "playbook_code": alt.playbook_code,
                        "confidence": alt.confidence,
                        "rationale": alt.rationale,
                        "is_orchestration": alt.is_orchestration,
                    }
                    for alt in (getattr(decision_result.intent_contribution, 'alternatives', []) if hasattr(decision_result.intent_contribution, 'alternatives') else [])
                ],
                "confidence": getattr(decision_result.intent_contribution, 'confidence', 0.0),
                "rationale": getattr(decision_result.intent_contribution, 'rationale', ""),
                "decision_method": getattr(decision_result.intent_contribution, 'decision_method', "unified_decision_coordinator"),
                "execution_profile_hint": getattr(decision_result.intent_contribution, 'execution_profile_hint', "fast"),
            },

            # Playbook layer contribution (handle None and minimum required fields)
            "playbook_contribution": self._serialize_playbook_contribution(decision_result.playbook_contribution) if decision_result.playbook_contribution else None,

            # Other governance layer contributions (handle None)
            "node_governance_contribution": self._serialize_governance_contribution(decision_result.node_governance_contribution),
            "cost_governance_contribution": self._serialize_governance_contribution(decision_result.cost_governance_contribution),
            "memory_contribution": self._serialize_governance_contribution(decision_result.memory_contribution),
            "policy_contribution": self._serialize_governance_contribution(decision_result.policy_contribution),

            # Conflicts and resolution
            "conflicts": [self._serialize_conflict(c) for c in decision_result.conflicts] if decision_result.conflicts else [],
            "resolution_strategy": decision_result.resolution_strategy,

            # Execution flags
            "can_auto_execute": decision_result.can_auto_execute,
            "requires_user_approval": decision_result.requires_user_approval,
        }

        intent_log = IntentLog(
            id=log_id,  # Use decision_id as log_id (checked for conflicts)
            timestamp=decision_result.timestamp,
            raw_input=user_input,
            channel="api",
            profile_id=user_id or "",
            project_id=project_id,
            workspace_id=workspace_id,
            pipeline_steps={
                "intent_analysis": getattr(intent_result, 'pipeline_steps', {}) if hasattr(intent_result, 'pipeline_steps') else {},
                "playbook_preflight": playbook_preflight_result.__dict__ if playbook_preflight_result else None,
                "node_governance": node_governance_decision.__dict__ if node_governance_decision else None,
                "cost_governance": cost_governance_decision.__dict__ if cost_governance_decision else None,
                "policy": policy_decision.__dict__ if policy_decision else None,
            },
            final_decision=final_decision_dict,  # Serialized UnifiedDecisionResult
            user_override=None,  # Initially None, updated when user overrides
            metadata={
                "decision_id": decision_result.decision_id,  # Backup decision_id
                "decision_method": "unified_decision_coordinator",
                "version": "1.0"  # For future compatibility
            }
        )

        try:
            store.create_intent_log(intent_log)
            logger.info(f"Successfully stored UnifiedDecisionResult to IntentLog: {log_id}")

            # Emit BRANCH_PROPOSED event if there are alternatives (ToT)
            # Check if there are multiple playbook alternatives
            has_alternatives = (
                decision_result.intent_contribution.alternatives and
                len(decision_result.intent_contribution.alternatives) > 0
            )

            if has_alternatives:
                self._emit_branch_proposed_event(
                    store=store,
                    intent_decision=decision_result.intent_contribution,
                    intent_result=None,  # Not needed here
                    workspace_id=workspace_id,
                    project_id=project_id,
                    user_id=user_id
                )

            # Emit DECISION_REQUIRED event if user approval is required (ReAct: Ask Human)
            if decision_result.requires_user_approval:
                self._emit_decision_required_event(
                    store=store,
                    decision_result=decision_result,
                    intent_log=intent_log,
                    workspace_id=workspace_id,
                    project_id=project_id,
                    user_id=user_id
                )
        except Exception as e:
            logger.error(f"Failed to store UnifiedDecisionResult to IntentLog: {e}", exc_info=True)
            raise

    def _serialize_playbook_contribution(self, playbook_contribution: Any) -> Optional[Dict[str, Any]]:
        """Serialize PlaybookPreflightResult (handle None and minimum required fields)"""
        if not playbook_contribution:
            return None

        # Minimum required fields: playbook_code, status, accepted
        result = {
            "playbook_code": getattr(playbook_contribution, 'playbook_code', None),
            "status": getattr(playbook_contribution.status, 'value', None) if hasattr(playbook_contribution, 'status') and playbook_contribution.status else (
                getattr(playbook_contribution, 'status', None) if isinstance(getattr(playbook_contribution, 'status', None), str) else None
            ),
            "accepted": getattr(playbook_contribution, 'accepted', False),
        }

        # Optional fields
        if hasattr(playbook_contribution, 'missing_inputs'):
            result["missing_inputs"] = playbook_contribution.missing_inputs or []
        if hasattr(playbook_contribution, 'clarification_questions'):
            result["clarification_questions"] = playbook_contribution.clarification_questions or []
        if hasattr(playbook_contribution, 'rejection_reason'):
            result["rejection_reason"] = playbook_contribution.rejection_reason
        if hasattr(playbook_contribution, 'recommended_alternatives'):
            result["recommended_alternatives"] = playbook_contribution.recommended_alternatives or []
        if hasattr(playbook_contribution, 'recommended_orchestration'):
            result["recommended_orchestration"] = playbook_contribution.recommended_orchestration

        return result

    def _serialize_governance_contribution(self, contribution: Any) -> Optional[Dict[str, Any]]:
        """Serialize governance layer contribution (handle None)"""
        if not contribution:
            return None

        # Use __dict__ but handle possible errors
        try:
            return contribution.__dict__ if hasattr(contribution, '__dict__') else None
        except Exception as e:
            logger.warning(f"Failed to serialize governance contribution: {e}")
            return None

    def _serialize_conflict(self, conflict: Any) -> Dict[str, Any]:
        """Serialize conflict (handle different types)"""
        if hasattr(conflict, '__dict__'):
            return conflict.__dict__
        elif isinstance(conflict, dict):
            return conflict
        else:
            return {"type": str(type(conflict)), "value": str(conflict)}

    def _emit_decision_required_event(
        self,
        store: Any,  # MindscapeStore
        decision_result: UnifiedDecisionResult,
        intent_log: Any,  # IntentLog
        workspace_id: str,
        project_id: Optional[str],
        user_id: Optional[str]
    ) -> None:
        """
        Emit DECISION_REQUIRED event for Human-in-the-loop (ReAct: Ask Human)

        This event is projected to the right panel as a blocker card.
        """
        from backend.app.models.mindscape import MindEvent, EventType, EventActor

        # Collect missing inputs and clarification questions
        missing_inputs = [
            ...(decision_result.intent_contribution.missing_inputs or []),
            ...(decision_result.playbook_contribution.missing_inputs or [] if decision_result.playbook_contribution else []),
        ]
        clarification_questions = (
            decision_result.playbook_contribution.clarification_questions or []
            if decision_result.playbook_contribution else []
        )

        # Calculate blocked steps (if execution plan is available)
        # Note: Execution plan may not be available at decision time
        # If available, we can extract step IDs that depend on this decision
        blocked_step_ids: List[str] = []

        # Try to get execution plan from intent_log metadata or pipeline_steps
        if intent_log and hasattr(intent_log, 'metadata') and intent_log.metadata:
            execution_plan = intent_log.metadata.get("execution_plan")
            if execution_plan and isinstance(execution_plan, dict):
                # Extract step IDs from execution plan
                tasks = execution_plan.get("tasks", [])
                if isinstance(tasks, list):
                    # If decision blocks execution, all steps are blocked
                    # Otherwise, identify steps that require the missing inputs
                    if missing_inputs or clarification_questions or decision_result.requires_user_approval:
                        blocked_step_ids = [
                            task.get("id") or f"step-{i}"
                            for i, task in enumerate(tasks)
                            if isinstance(task, dict)
                        ]

        # Determine card type
        card_type = "decision"
        if missing_inputs:
            card_type = "input"
        elif clarification_questions:
            card_type = "review"
        elif decision_result.conflicts:
            card_type = "review"

        # Determine priority
        priority = "blocker" if decision_result.requires_user_approval else "normal"
        if decision_result.conflicts:
            priority = "high"

        try:
            event = MindEvent(
                id=str(uuid.uuid4()),
                timestamp=datetime.utcnow(),
                actor=EventActor.AGENT,
                channel="api",
                profile_id=user_id or "",
                project_id=project_id,
                workspace_id=workspace_id,
                event_type=EventType.DECISION_REQUIRED,
                payload={
                    "decision_id": decision_result.decision_id,
                    "intent_log_id": intent_log.id,
                    "requires_user_approval": decision_result.requires_user_approval,
                    "can_auto_execute": decision_result.can_auto_execute,
                    "missing_inputs": missing_inputs,
                    "clarification_questions": clarification_questions,
                    "conflicts": [self._serialize_conflict(c) for c in decision_result.conflicts] if decision_result.conflicts else [],
                    "blocking_steps": blocked_step_ids,
                    "card_type": card_type,
                    "priority": priority,
                    "selected_playbook_code": decision_result.selected_playbook_code,
                    "rationale": decision_result.intent_contribution.rationale,
                },
                entity_ids={
                    "decision_id": decision_result.decision_id,
                    "intent_log_id": intent_log.id,
                },
                metadata={
                    "decision_method": decision_result.intent_contribution.decision_method,
                    "playbook_code": decision_result.selected_playbook_code,
                }
            )
            store.create_event(event)
            logger.info(f"Emitted DECISION_REQUIRED event for decision {decision_result.decision_id}")
        except Exception as e:
            logger.error(f"Failed to emit DECISION_REQUIRED event: {e}", exc_info=True)

    def _emit_branch_proposed_event(
        self,
        store: Any,  # MindscapeStore (will be set when storing decision)
        intent_decision: IntentRoutingDecision,
        intent_result: Any,  # IntentAnalysisResult
        workspace_id: str,
        project_id: Optional[str],
        user_id: Optional[str]
    ) -> None:
        """
        Emit BRANCH_PROPOSED event for Tree of Thoughts (ToT)

        This event is projected to the right panel as a branch choice card.
        """
        from backend.app.models.mindscape import MindEvent, EventType, EventActor

        # Collect alternatives and calculate differences
        alternatives = []
        if intent_decision.alternatives:
            # Calculate differences between alternatives
            for i, alt in enumerate(intent_decision.alternatives):
                differences = []

                # Compare with other alternatives
                for j, other_alt in enumerate(intent_decision.alternatives):
                    if i == j:
                        continue

                    # Compare playbook codes
                    if alt.playbook_code != other_alt.playbook_code:
                        differences.append(f"Different playbook: {alt.playbook_code} vs {other_alt.playbook_code}")

                    # Compare confidence levels
                    confidence_diff = abs(alt.confidence - other_alt.confidence)
                    if confidence_diff > 0.1:  # Significant difference
                        if alt.confidence > other_alt.confidence:
                            differences.append(f"Higher confidence ({alt.confidence:.2f} vs {other_alt.confidence:.2f})")
                        else:
                            differences.append(f"Lower confidence ({alt.confidence:.2f} vs {other_alt.confidence:.2f})")

                    # Compare required inputs
                    alt_inputs = set(alt.required_inputs or [])
                    other_inputs = set(other_alt.required_inputs or [])
                    if alt_inputs != other_inputs:
                        unique_inputs = alt_inputs - other_inputs
                        if unique_inputs:
                            differences.append(f"Requires additional inputs: {', '.join(unique_inputs)}")
                        missing_inputs = other_inputs - alt_inputs
                        if missing_inputs:
                            differences.append(f"Missing inputs compared to others: {', '.join(missing_inputs)}")

                # Limit differences to top 3 most significant
                differences = differences[:3]

                alternatives.append({
                    "playbook_code": alt.playbook_code,
                    "confidence": alt.confidence,
                    "rationale": alt.rationale,
                    "differences": differences,
                })
        elif intent_decision.suggested_playbook:
            # If no explicit alternatives, create from suggested playbook
            alternatives = [{
                "playbook_code": intent_decision.suggested_playbook.playbook_code,
                "confidence": intent_decision.suggested_playbook.confidence,
                "rationale": intent_decision.suggested_playbook.rationale,
                "differences": [],
            }]

        # Determine recommended branch
        recommended_branch = None
        if intent_decision.suggested_playbook:
            recommended_branch = intent_decision.suggested_playbook.playbook_code
        elif alternatives:
            # Use highest confidence alternative
            recommended_branch = max(alternatives, key=lambda a: a["confidence"])["playbook_code"]

        branch_id = f"branch-{intent_decision.decision_id}"

        try:
            # Note: store will be available when decision is stored
            # For now, we'll emit the event when storing the decision
            # Store event data in a way that can be emitted later
            if store:
                event = MindEvent(
                    id=str(uuid.uuid4()),
                    timestamp=datetime.utcnow(),
                    actor=EventActor.AGENT,
                    channel="api",
                    profile_id=user_id or "",
                    project_id=project_id,
                    workspace_id=workspace_id,
                    event_type=EventType.BRANCH_PROPOSED,
                    payload={
                        "branch_id": branch_id,
                        "decision_id": intent_decision.decision_id,
                        "alternatives": alternatives,
                        "recommended_branch": recommended_branch,
                        "context": f"Multiple playbook options available. Recommended: {recommended_branch}",
                        "rationale": intent_decision.rationale,
                    },
                    entity_ids={
                        "branch_id": branch_id,
                        "decision_id": intent_decision.decision_id,
                    },
                    metadata={
                        "decision_method": intent_decision.decision_method,
                    }
                )
                store.create_event(event)
                logger.info(f"Emitted BRANCH_PROPOSED event for branch {branch_id}")
        except Exception as e:
            logger.error(f"Failed to emit BRANCH_PROPOSED event: {e}", exc_info=True)

