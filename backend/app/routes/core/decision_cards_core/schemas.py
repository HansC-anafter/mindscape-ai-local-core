from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

class ConfirmDecisionRequest(BaseModel):
    """Request model for confirming a decision"""

    action: str = Field(
        ..., description="Action: confirm | reject | clarify | override"
    )
    clarificationAnswers: Optional[Dict[str, str]] = Field(
        None, description="Answers to clarification questions"
    )
    providedInputs: Optional[Dict[str, Any]] = Field(
        None, description="Provided inputs for missing inputs"
    )
    overridePlaybookCode: Optional[str] = Field(
        None, description="Override playbook code"
    )
    overrideReason: Optional[str] = Field(None, description="Reason for override")
    comment: Optional[str] = Field(None, description="Optional comment")


class BreakGlassRequestModel(BaseModel):
    """Request for break-glass permission"""

    operations: list[str] = Field(
        ..., description="Operations: read_file, write_file, execute_command, etc."
    )
    resource_patterns: list[str] = Field(..., description="Resource patterns to access")
    reason: str = Field(..., description="Why break-glass is needed")
    task_description: str = Field("", description="Task requiring break-glass")
    duration_minutes: int = Field(15, ge=5, le=60, description="Duration (5-60 min)")
    agent_id: Optional[str] = Field(
        None,
        description="Agent requesting (default: model-route-registry workspace executor route)",
    )


class BreakGlassApprovalModel(BaseModel):
    """Approve/deny break-glass request"""

    approved: bool
    comment: Optional[str] = None
    modified_operations: Optional[list[str]] = None
    modified_duration: Optional[int] = None
