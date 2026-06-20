"""Public decision coordinator schemas."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from backend.app.core.runtime_port import ExecutionProfile


@dataclass
class PlaybookCandidate:
    """Candidate playbook."""

    playbook_code: str
    confidence: float
    rationale: str
    required_inputs: List[str] = field(default_factory=list)
    missing_inputs: List[str] = field(default_factory=list)
    is_orchestration: bool = False
    orchestration_steps: List[str] = field(default_factory=list)


@dataclass
class IntentRoutingDecision:
    """Intent layer routing decision."""

    decision_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    intent_id: Optional[str] = None
    suggested_playbook: Optional[PlaybookCandidate] = None
    alternatives: List[PlaybookCandidate] = field(default_factory=list)
    confidence: float = 0.0
    rationale: str = ""
    decision_method: str = ""
    execution_profile_hint: str = "fast"
    required_inputs: List[str] = field(default_factory=list)
    missing_inputs: List[str] = field(default_factory=list)
    user_override: Optional[PlaybookCandidate] = None
    override_reason: Optional[str] = None
    should_learn: bool = False
    timestamp: datetime = field(default_factory=datetime.utcnow)
    source_intent_analysis: Optional[Dict[str, Any]] = None
    workspace_id: Optional[str] = None
    project_id: Optional[str] = None
    profile_id: Optional[str] = None

    @property
    def recommended_playbook_code(self) -> Optional[str]:
        """Return the selected playbook code."""
        return self.suggested_playbook.playbook_code if self.suggested_playbook else None

    @property
    def is_overridable(self) -> bool:
        """Return whether override is allowed."""
        return True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for persistence."""
        return {
            "decision_id": self.decision_id,
            "intent_id": self.intent_id,
            "suggested_playbook": (
                {
                    "playbook_code": self.suggested_playbook.playbook_code,
                    "confidence": self.suggested_playbook.confidence,
                    "rationale": self.suggested_playbook.rationale,
                    "is_orchestration": self.suggested_playbook.is_orchestration,
                    "orchestration_steps": self.suggested_playbook.orchestration_steps,
                }
                if self.suggested_playbook
                else None
            ),
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
            "user_override": (
                {
                    "playbook_code": self.user_override.playbook_code,
                    "confidence": self.user_override.confidence,
                    "rationale": self.user_override.rationale,
                }
                if self.user_override
                else None
            ),
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
        intent_result: Any,
        workspace_id: Optional[str] = None,
        project_id: Optional[str] = None,
        profile_id: Optional[str] = None,
    ) -> "IntentRoutingDecision":
        """Build IntentRoutingDecision from an intent analysis result."""
        suggested_playbook = None
        if intent_result.selected_playbook_code:
            suggested_playbook = PlaybookCandidate(
                playbook_code=intent_result.selected_playbook_code,
                confidence=intent_result.playbook_confidence,
                rationale=(
                    "Selected by IntentPipeline "
                    f"(confidence: {intent_result.playbook_confidence:.2f})"
                ),
                is_orchestration=intent_result.is_multi_step,
                orchestration_steps=[
                    step.get("playbook_code", "")
                    for step in intent_result.workflow_steps
                ]
                if intent_result.workflow_steps
                else [],
            )

        task_domain = intent_result.task_domain
        interaction_type = intent_result.interaction_type
        return cls(
            decision_id=str(uuid.uuid4()),
            suggested_playbook=suggested_playbook,
            alternatives=[],
            confidence=intent_result.playbook_confidence,
            rationale=(
                "Intent analysis result: "
                f"{task_domain.value if hasattr(task_domain, 'value') and task_domain else 'unknown'}"
            ),
            decision_method="intent_pipeline",
            execution_profile_hint="fast",
            source_intent_analysis={
                "interaction_type": (
                    interaction_type.value
                    if hasattr(interaction_type, "value") and interaction_type
                    else None
                ),
                "task_domain": (
                    task_domain.value
                    if hasattr(task_domain, "value") and task_domain
                    else None
                ),
                "selected_playbook_code": intent_result.selected_playbook_code,
                "playbook_confidence": intent_result.playbook_confidence,
                "is_multi_step": intent_result.is_multi_step,
            },
            workspace_id=workspace_id,
            project_id=project_id,
            profile_id=profile_id,
        )


@dataclass
class PlaybookPreflightResult:
    """Playbook preflight result."""

    playbook_code: str
    status: str
    accepted: bool
    missing_inputs: List[str] = field(default_factory=list)
    clarification_questions: List[str] = field(default_factory=list)
    rejection_reason: Optional[str] = None
    recommended_alternatives: List[str] = field(default_factory=list)
    recommended_orchestration: Optional[str] = None


@dataclass
class NodeGovernanceDecision:
    """Node governance decision."""

    approved: bool
    reason: Optional[str] = None


@dataclass
class CostGovernanceDecision:
    """Cost governance decision."""

    approved: bool
    reason: Optional[str] = None
    estimated_cost: Optional[float] = None


@dataclass
class PolicyDecision:
    """Policy decision."""

    approved: bool
    reason: Optional[str] = None


@dataclass
class MemoryRecommendation:
    """Memory recommendation."""

    recommended_playbook_code: Optional[str] = None
    confidence: float = 0.0


@dataclass
class UnifiedDecisionResult:
    """Unified decision result from all governance layers."""

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
