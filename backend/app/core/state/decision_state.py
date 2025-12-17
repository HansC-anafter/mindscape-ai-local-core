"""
DecisionState Schema

Scope/publish/important decisions (only policy can write).
DecisionState can only be written by policy, not by LLM or tools.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum


class DecisionType(str, Enum):
    """Decision type"""
    SCOPE = "scope"  # Scope resolution decision
    PUBLISH = "publish"  # Publish decision
    APPROVAL = "approval"  # Approval decision
    ROLLBACK = "rollback"  # Rollback decision
    RISK_ASSESSMENT = "risk_assessment"  # Risk assessment decision
    POLICY_OVERRIDE = "policy_override"  # Policy override decision


class DecisionStatus(str, Enum):
    """Decision status"""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    DEFERRED = "deferred"


@dataclass
class DecisionState:
    """
    DecisionState Schema

    Scope/publish/important decisions (only policy can write).
    DecisionState can only be written by policy, not by LLM or tools.

    Write rule: Only policy can write to DecisionState.
    """
    # State identification
    state_id: str
    workspace_id: str

    # Decision identification
    decision_id: str
    decision_type: DecisionType

    # Decision content
    decision_data: Dict[str, Any]  # Decision content

    # Policy information (required fields must come before optional fields)
    policy_name: str  # Policy name that made this decision

    # Decision metadata
    status: DecisionStatus = DecisionStatus.PENDING
    reasoning: Optional[str] = None  # Policy reasoning
    policy_version: Optional[str] = None  # Policy version

    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = None

    # Resolution information
    resolved_by: Optional[str] = None  # Resolver identifier (policy_name, user_id, etc.)
    resolution_notes: Optional[str] = None

    # Version for backward compatibility
    version: str = "1.0"

    # Additional metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def update_decision(
        self,
        decision_data: Dict[str, Any],
        policy_name: str,
        reasoning: Optional[str] = None,
        policy_version: Optional[str] = None
    ) -> None:
        """
        Update decision (only policy can call this)

        Args:
            decision_data: Updated decision data
            policy_name: Policy name making the update
            reasoning: Policy reasoning
            policy_version: Policy version

        Raises:
            ValueError: If not called by policy
        """
        # Validate that this is called by policy
        if not policy_name.startswith("policy_"):
            raise ValueError(f"DecisionState can only be written by policy. Invalid policy_name: {policy_name}")

        self.decision_data = decision_data
        self.policy_name = policy_name
        self.reasoning = reasoning
        if policy_version:
            self.policy_version = policy_version
        self.updated_at = datetime.utcnow()

    def resolve_decision(
        self,
        status: DecisionStatus,
        resolved_by: str,
        resolution_notes: Optional[str] = None
    ) -> None:
        """
        Resolve decision

        Args:
            status: Decision status
            resolved_by: Resolver identifier
            resolution_notes: Resolution notes
        """
        self.status = status
        self.resolved_by = resolved_by
        self.resolution_notes = resolution_notes
        self.resolved_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        result = {
            "version": self.version,
            "state_id": self.state_id,
            "workspace_id": self.workspace_id,
            "decision_id": self.decision_id,
            "decision_type": self.decision_type.value,
            "decision_data": self.decision_data,
            "status": self.status.value,
            "policy_name": self.policy_name,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata,
        }

        if self.reasoning:
            result["reasoning"] = self.reasoning
        if self.policy_version:
            result["policy_version"] = self.policy_version
        if self.resolved_at:
            result["resolved_at"] = self.resolved_at.isoformat()
        if self.resolved_by:
            result["resolved_by"] = self.resolved_by
        if self.resolution_notes:
            result["resolution_notes"] = self.resolution_notes

        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DecisionState":
        """Create DecisionState from dictionary"""
        decision_type = DecisionType(data["decision_type"])
        status = DecisionStatus(data.get("status", "pending"))

        created_at = datetime.fromisoformat(data["created_at"]) if isinstance(data.get("created_at"), str) else data.get("created_at", datetime.utcnow())
        updated_at = datetime.fromisoformat(data["updated_at"]) if isinstance(data.get("updated_at"), str) else data.get("updated_at", datetime.utcnow())

        resolved_at = None
        if data.get("resolved_at"):
            resolved_at = datetime.fromisoformat(data["resolved_at"]) if isinstance(data.get("resolved_at"), str) else data.get("resolved_at")

        return cls(
            state_id=data["state_id"],
            workspace_id=data["workspace_id"],
            decision_id=data["decision_id"],
            decision_type=decision_type,
            decision_data=data["decision_data"],
            status=status,
            reasoning=data.get("reasoning"),
            policy_name=data["policy_name"],
            policy_version=data.get("policy_version"),
            created_at=created_at,
            updated_at=updated_at,
            resolved_at=resolved_at,
            resolved_by=data.get("resolved_by"),
            resolution_notes=data.get("resolution_notes"),
            version=data.get("version", "1.0"),
            metadata=data.get("metadata", {}),
        )

