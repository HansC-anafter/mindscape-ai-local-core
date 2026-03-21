"""
Pydantic request/response schemas for playbook execution endpoints.

Extracted from playbook_execution.py to reduce module size
and isolate data contracts from routing logic.
"""

from typing import Optional
from pydantic import BaseModel
from typing import Literal


class ContinueExecutionRequest(BaseModel):
    """Request to continue playbook execution"""

    user_message: str


class StartExecutionRequest(BaseModel):
    """Request to start playbook execution"""

    inputs: Optional[dict] = None
    tenant_id: Optional[str] = None
    execution_id: Optional[str] = None
    trace_id: Optional[str] = None
    remote_job_type: Optional[Literal["playbook", "tool", "chain"]] = None
    target_language: Optional[str] = None
    variant_id: Optional[str] = None
    auto_execute: Optional[bool] = (
        None  # If True, skip confirmations and execute tools directly
    )
    execution_backend: Optional[Literal["auto", "runner", "in_process", "remote"]] = (
        None
    )


class CancelExecutionRequest(BaseModel):
    """Request to cancel playbook execution"""

    reason: Optional[str] = None


class RerunExecutionRequest(BaseModel):
    """Request to rerun playbook execution with original inputs"""

    override_inputs: Optional[dict] = None


class ResumeExecutionRequest(BaseModel):
    """Request to resume a paused workflow execution"""

    action: Literal["approve", "reject"]
    step_id: Optional[str] = None
    comment: Optional[str] = None
