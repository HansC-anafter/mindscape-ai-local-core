"""
Handoff models for cross-boundary task delegation.

Defines HandoffIn (upstream request) and Commitment (downstream response)
for structured agent-to-agent task handoffs.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


class DeliverableSpec(BaseModel):
    """Typed output specification for a handoff."""

    name: str
    mime_type: str
    description: Optional[str] = None


class HandoffConstraints(BaseModel):
    """Execution constraints for a handoff."""

    style_refs: Optional[List[str]] = None
    ip_policy: Optional[str] = None
    action_space: Optional[str] = Field(
        None,
        description="Allowed side-effect level: READ_ONLY / WRITE_WS / NETWORK_CALL / PUBLISH / BILLING / DESTRUCTIVE",
    )
    max_duration_seconds: Optional[int] = None


class HandoffIn(BaseModel):
    """Cross-boundary handoff request from upstream to downstream (A -> B).

    Represents the contract that entity A sends to entity B,
    specifying what needs to be done, with what constraints,
    and how to validate completion.
    """

    handoff_id: str
    workspace_id: str
    intent_summary: str = Field(..., description="What the task is about")
    goals: List[str] = Field(
        default_factory=list, description="Explicit deliverable goals"
    )
    non_goals: Optional[List[str]] = None
    deliverables: List[DeliverableSpec] = Field(default_factory=list)
    constraints: Optional[HandoffConstraints] = None
    acceptance_tests: Optional[List[str]] = None  # Deprecated: use GovernanceContext.acceptance_tests
    risk_notes: Optional[List[str]] = None

    # Optional governance transport fields.
    trace_id: Optional[str] = Field(None, description="End-to-end trace identifier")
    governance_constraints: Optional[Dict[str, Any]] = Field(
        None, description="Typed governance constraints for downstream engines"
    )
    requested_output_type: Optional[str] = Field(
        None, description="Expected output MIME type (e.g. text/markdown)"
    )
    human_instructions: Optional[str] = Field(
        None, description="Free-form human instructions for the pack"
    )
    context_attachments: Optional[List[Dict[str, Any]]] = Field(
        None, description="Evidence / provenance attachments passed to downstream"
    )
    deadline: Optional[datetime] = None
    assets: List[str] = Field(
        default_factory=list, description="Input artifact references"
    )
    source_device_id: Optional[str] = None
    target_device_id: Optional[str] = None
    created_at: datetime = Field(default_factory=_utc_now)
    metadata: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})


class Commitment(BaseModel):
    """Downstream commitment response to a HandoffIn (B -> A).

    Represents entity B's acceptance or rejection of the handoff,
    along with scope negotiation details.
    """

    commitment_id: str
    handoff_id: str = Field(..., description="References the originating HandoffIn")
    accepted: bool
    scope_summary: str
    open_questions: Optional[List[str]] = None
    estimated_phases: Optional[int] = None
    estimated_duration_seconds: Optional[int] = None
    task_ir_id: Optional[str] = Field(
        None, description="References compiled TaskIR if accepted"
    )
    created_at: datetime = Field(default_factory=_utc_now)

    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})
