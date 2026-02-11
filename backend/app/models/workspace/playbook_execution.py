"""
Playbook execution models — PlaybookExecution, PlaybookExecutionStep.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Dict, Any, List, Union, TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from ..mindscape import MindEvent


class PlaybookExecutionStep(BaseModel):
    """
    PlaybookExecutionStep view model - represents a single step in a playbook execution

    PlaybookExecutionStep is a view model based on MindEvent(event_type=PLAYBOOK_STEP).
    It does not have its own table but is constructed from MindEvent records.

    Note: This is different from ExecutionStep (used in ExecutionPlan for Chain-of-Thought).
    """

    id: str = Field(..., description="Step ID (same as MindEvent.id)")
    execution_id: str = Field(..., description="Associated execution ID")
    step_index: int = Field(..., description="Step index (1-based for display)")
    step_name: str = Field(..., description="Step name")
    total_steps: Optional[int] = Field(
        None, description="Total number of steps in this execution"
    )
    status: str = Field(
        ..., description="Status: pending/running/completed/failed/waiting_confirmation"
    )
    step_type: str = Field(
        ...,
        description="Step type: agent_action/tool_call/agent_collaboration/user_confirmation",
    )
    agent_type: Optional[str] = Field(
        None, description="Agent type: researcher/editor/engineer"
    )
    used_tools: Optional[List[str]] = Field(
        None, description="List of tools used in this step"
    )
    assigned_agent: Optional[str] = Field(None, description="Assigned agent")
    collaborating_agents: Optional[List[str]] = Field(
        None, description="Collaborating agents"
    )
    description: Optional[str] = Field(None, description="Step description")
    log_summary: Optional[str] = Field(None, description="One-line log summary")
    requires_confirmation: bool = Field(
        default=False, description="Whether step requires user confirmation"
    )
    confirmation_prompt: Optional[str] = Field(
        None, description="Confirmation prompt text"
    )
    confirmation_status: Optional[str] = Field(
        None, description="Confirmation status: pending/confirmed/rejected"
    )
    intent_id: Optional[str] = Field(None, description="Associated intent ID")
    started_at: Optional[datetime] = Field(None, description="Start timestamp")
    completed_at: Optional[datetime] = Field(None, description="Completion timestamp")
    error: Optional[str] = Field(None, description="Error message if failed")
    failure_type: Optional[str] = Field(None, description="Failure type if failed")

    @classmethod
    def from_mind_event(
        cls, event: Union["MindEvent", Dict[str, Any]]
    ) -> "PlaybookExecutionStep":
        """Create PlaybookExecutionStep from MindEvent"""
        if hasattr(event, "payload"):
            payload = event.payload
            event_id = event.id
        elif isinstance(event, dict):
            payload = event.get("payload", {})
            event_id = event.get("id", "")
        else:
            payload = {}
            event_id = ""

        return cls(
            id=event_id,
            execution_id=payload.get("execution_id", ""),
            step_index=payload.get("step_index", 0),
            step_name=payload.get("step_name", ""),
            total_steps=payload.get("total_steps"),
            status=payload.get("status", "pending"),
            step_type=payload.get("step_type", "agent_action"),
            agent_type=payload.get("agent_type"),
            used_tools=payload.get("used_tools"),
            assigned_agent=payload.get("assigned_agent"),
            collaborating_agents=payload.get("collaborating_agents"),
            description=payload.get("description"),
            log_summary=payload.get("log_summary"),
            requires_confirmation=payload.get("requires_confirmation", False),
            confirmation_prompt=payload.get("confirmation_prompt"),
            confirmation_status=payload.get("confirmation_status"),
            intent_id=payload.get("intent_id"),
            started_at=(
                datetime.fromisoformat(payload["started_at"])
                if payload.get("started_at")
                else None
            ),
            completed_at=(
                datetime.fromisoformat(payload["completed_at"])
                if payload.get("completed_at")
                else None
            ),
            error=payload.get("error"),
            failure_type=payload.get("failure_type"),
        )


class PlaybookExecution(BaseModel):
    """
    PlaybookExecution model - represents a playbook execution record

    This is the persistent record for playbook executions with checkpoint/resume support.
    """

    id: str = Field(..., description="Execution ID")
    workspace_id: str = Field(..., description="Workspace ID")
    playbook_code: str = Field(..., description="Playbook code")
    intent_instance_id: Optional[str] = Field(
        None, description="Origin intent instance ID"
    )
    thread_id: Optional[str] = Field(
        None, description="Associated conversation thread ID"
    )
    status: str = Field(..., description="Execution status: running/paused/done/failed")
    phase: Optional[str] = Field(None, description="Current phase ID")
    last_checkpoint: Optional[str] = Field(
        None, description="Last checkpoint data (JSON)"
    )
    progress_log_path: Optional[str] = Field(None, description="Progress log file path")
    feature_list_path: Optional[str] = Field(None, description="Feature list file path")
    metadata: Optional[Dict[str, Any]] = Field(
        None,
        description="Execution metadata (BYOP/BYOL fields: pack_id, card_id, scope, playbook_version)",
    )
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}
