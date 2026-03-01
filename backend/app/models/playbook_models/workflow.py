"""Workflow and handoff models for playbooks."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from .enums import ErrorHandlingStrategy, InteractionMode, PlaybookKind


class RetryPolicy(BaseModel):
    """Retry policy for workflow step execution."""

    max_retries: int = Field(default=3, description="Maximum retry attempts")
    retry_delay: float = Field(default=1.0, description="Delay between retries (sec)")
    exponential_backoff: bool = Field(
        default=True, description="Use exponential backoff"
    )
    retryable_errors: List[str] = Field(
        default_factory=list,
        description="Error types that should trigger retry (empty means retry all)",
    )


class WorkflowStep(BaseModel):
    """Workflow step in HandoffPlan."""

    playbook_code: str = Field(..., description="Playbook to execute")
    kind: PlaybookKind = Field(..., description="Playbook type")
    inputs: Dict[str, Any] = Field(
        ..., description="Input parameters (supports $previous, $context syntax)"
    )
    input_mapping: Dict[str, str] = Field(
        default_factory=dict,
        description="Input mapping from previous steps or context",
    )
    condition: Optional[str] = Field(None, description="Optional execution condition")
    interaction_mode: List[InteractionMode] = Field(
        default_factory=lambda: [InteractionMode.CONVERSATIONAL],
        description="How this step interacts with users",
    )
    retry_policy: Optional[RetryPolicy] = Field(
        None,
        description="Retry policy for this step",
    )
    error_handling: ErrorHandlingStrategy = Field(
        default=ErrorHandlingStrategy.RETRY_THEN_STOP,
        description="Error handling strategy when step fails",
    )


class HandoffPlan(BaseModel):
    """Workspace LLM -> Playbook LLM handoff protocol."""

    steps: List[WorkflowStep] = Field(..., description="Workflow steps to execute")
    context: Dict[str, Any] = Field(
        default_factory=dict, description="Initial context (e.g., uploaded files)"
    )
    estimated_duration: Optional[int] = Field(
        None, description="Estimated execution time in seconds"
    )

    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})

