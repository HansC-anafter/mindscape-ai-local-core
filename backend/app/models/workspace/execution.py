"""
Execution models — ExecutionStep, TaskPlan, ExecutionPlan, ExecutionSession, ExecutionChatMessage.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Dict, Any, List, Union, Literal, TYPE_CHECKING

from pydantic import BaseModel, Field

from ._common import _utc_now
from .enums import ExecutionChatMessageType, TaskStatus
from .task import Task

if TYPE_CHECKING:
    from ..mindscape import MindEvent


# ==================== Execution Plan Models (Internal) ====================


class ExecutionStep(BaseModel):
    """
    ExecutionStep model - represents a single step in the execution chain-of-thought

    This is the explicit "thinking step" that shows:
    - What the LLM decided to do
    - Why it chose this approach
    - What artifacts will be produced
    """

    step_id: str = Field(..., description="Unique step identifier (e.g., 'S1', 'S2')")
    intent: str = Field(..., description="Intent/purpose of this step")
    playbook_code: Optional[str] = Field(
        None, description="Playbook to execute (if applicable)"
    )
    tool_name: Optional[str] = Field(None, description="Tool to use (if applicable)")
    artifacts: List[str] = Field(
        default_factory=list,
        description="Expected artifact types (e.g., ['pptx', 'docx'])",
    )
    reasoning: Optional[str] = Field(
        None, description="Why this step was chosen (CoT reasoning)"
    )
    depends_on: List[str] = Field(
        default_factory=list, description="Step IDs this depends on"
    )
    requires_confirmation: bool = Field(
        False, description="Whether user confirmation is needed"
    )
    side_effect_level: Optional[str] = Field(
        None, description="Side effect level: readonly/soft_write/external_write"
    )
    estimated_duration: Optional[str] = Field(
        None, description="Estimated duration (e.g., '30s', '2m')"
    )


class TaskPlan(BaseModel):
    """
    TaskPlan model - represents a planned task in an execution plan

    Used internally by ConversationOrchestrator to plan task execution
    based on side_effect_level and user intent.
    """

    pack_id: str = Field(..., description="Pack identifier")
    task_type: str = Field(
        ..., description="Task type (e.g., 'extract_intents', 'generate_tasks')"
    )
    params: Dict[str, Any] = Field(default_factory=dict, description="Task parameters")
    side_effect_level: Optional[str] = Field(None, description="Side effect level")
    auto_execute: bool = Field(False, description="Whether to execute automatically")
    requires_cta: bool = Field(False, description="Whether to require CTA confirmation")


class ExecutionPlan(BaseModel):
    """
    ExecutionPlan model - represents a complete execution plan for a message

    This is the "Chain-of-Thought" for Execution Mode:
    - Shows what the LLM decided to do BEFORE doing it
    - Provides structured reasoning for debugging and replay
    - Can be recorded as EXECUTION_PLAN MindEvent for traceability

    See: docs-internal/architecture/workspace-llm-agent-execution-mode.md
    """

    id: str = Field(
        default_factory=lambda: str(__import__("uuid").uuid4()), description="Plan ID"
    )
    message_id: str = Field(..., description="Associated message/event ID")
    workspace_id: str = Field(..., description="Workspace ID")

    # Chain-of-Thought fields
    user_request_summary: Optional[str] = Field(
        None, description="Summary of what user asked for"
    )
    reasoning: Optional[str] = Field(
        None, description="Overall reasoning for the plan (CoT)"
    )
    plan_summary: Optional[str] = Field(
        None, description="Human-readable summary for display"
    )
    steps: List[ExecutionStep] = Field(
        default_factory=list, description="Execution steps (CoT)"
    )

    # Legacy compatibility - kept for backward compatibility
    tasks: List[TaskPlan] = Field(
        default_factory=list, description="Planned tasks (legacy)"
    )

    # Metadata
    execution_mode: Optional[str] = Field(None, description="qa/execution/hybrid")
    confidence: Optional[float] = Field(
        None, description="LLM confidence in this plan (0-1)"
    )
    created_at: datetime = Field(
        default_factory=_utc_now, description="Creation timestamp"
    )

    # Project and Phase association
    project_id: Optional[str] = Field(None, description="Associated Project ID")
    phase_id: Optional[str] = Field(None, description="Associated Project Phase ID")
    project_assignment_decision: Optional[Dict[str, Any]] = Field(
        None,
        description="Project assignment decision: {project_id, relation, confidence, reasoning, candidates}",
    )

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}

    def to_event_payload(self) -> Dict[str, Any]:
        """Convert to payload for EXECUTION_PLAN MindEvent"""
        import logging

        logger = logging.getLogger(__name__)

        payload = {
            "id": self.id,
            "plan_id": self.id,
            "user_request_summary": self.user_request_summary,
            "reasoning": self.reasoning,
            "plan_summary": self.plan_summary,
            "steps": [step.dict() for step in self.steps],
            "execution_mode": self.execution_mode,
            "confidence": self.confidence,
            "step_count": len(self.steps),
            "artifact_count": sum(len(s.artifacts) for s in self.steps),
        }

        metadata = (
            getattr(self, "_metadata", None) or getattr(self, "metadata", None) or {}
        )
        effective_playbooks = metadata.get("effective_playbooks")
        if effective_playbooks is not None:
            payload["effective_playbooks"] = effective_playbooks
            payload["effective_playbooks_count"] = len(effective_playbooks)

        # Extract AI team members from tasks or steps (for tool-based plans)
        ai_team_members = []
        try:
            from backend.app.services.ai_team_service import (
                get_members_from_tasks,
                get_member_info,
            )

            playbook_code = None
            if self.steps and len(self.steps) > 0:
                playbook_code = getattr(self.steps[0], "playbook_code", None)

            # First, try to get members from tasks (for playbook-based plans)
            if self.tasks:
                if not playbook_code and self.tasks and len(self.tasks) > 0:
                    first_task = self.tasks[0]
                    if (
                        hasattr(first_task, "playbook_code")
                        and first_task.playbook_code
                    ):
                        playbook_code = first_task.playbook_code
                    elif hasattr(first_task, "params") and isinstance(
                        first_task.params, dict
                    ):
                        playbook_code = first_task.params.get("playbook_code")

                ai_team_members = get_members_from_tasks(self.tasks, playbook_code)
                logger.info(
                    f"[ExecutionPlan] Extracted {len(ai_team_members)} AI team members from {len(self.tasks)} tasks, playbook_code={playbook_code}"
                )

            # If no members from tasks, try to get from steps (for tool-based plans)
            if not ai_team_members and self.steps:
                seen_pack_ids = set()
                for step in self.steps:
                    # Try tool_name as pack_id (tools can be AI team members too)
                    tool_name = getattr(step, "tool_name", None)
                    if tool_name and tool_name not in seen_pack_ids:
                        seen_pack_ids.add(tool_name)
                        member_info = get_member_info(tool_name, playbook_code)
                        if member_info and member_info.get("visible", True):
                            ai_team_members.append(member_info)
                            logger.info(
                                f"[ExecutionPlan] Added tool-based member: {member_info.get('name_zh') or member_info.get('name')}"
                            )

                    # Also try playbook_code as pack_id
                    step_playbook_code = getattr(step, "playbook_code", None)
                    if step_playbook_code and step_playbook_code not in seen_pack_ids:
                        seen_pack_ids.add(step_playbook_code)
                        member_info = get_member_info(step_playbook_code, playbook_code)
                        if member_info and member_info.get("visible", True):
                            ai_team_members.append(member_info)
                            logger.info(
                                f"[ExecutionPlan] Added playbook-based member: {member_info.get('name_zh') or member_info.get('name')}"
                            )

                if ai_team_members:
                    logger.info(
                        f"[ExecutionPlan] Extracted {len(ai_team_members)} AI team members from {len(self.steps)} steps"
                    )

            if ai_team_members:
                payload["ai_team_members"] = ai_team_members
                logger.info(
                    f"[ExecutionPlan] Added ai_team_members to payload: {[m.get('name_zh') or m.get('name') for m in ai_team_members]}"
                )
            else:
                logger.warning(
                    f"[ExecutionPlan] No AI team members extracted from tasks or steps"
                )
        except Exception as e:
            logger.warning(f"Failed to extract AI team members: {e}", exc_info=True)

        return payload


# ==================== Execution Session ====================


class ExecutionSession(BaseModel):
    """
    ExecutionSession view model - represents a playbook execution session

    ExecutionSession is a view model based on Task + execution_context.
    It does not have its own table but is constructed from Task records.
    """

    execution_id: str = Field(..., description="Execution ID (same as Task.id)")
    workspace_id: str = Field(..., description="Workspace ID")
    task: Task = Field(..., description="Underlying Task record")
    playbook_code: Optional[str] = Field(None, description="Playbook code")
    playbook_version: Optional[str] = Field(None, description="Playbook version")
    trigger_source: Optional[str] = Field(
        None, description="Trigger source: auto/suggestion/manual"
    )
    current_step_index: int = Field(
        default=0, description="Current step index (0-based)"
    )
    total_steps: int = Field(default=0, description="Total number of steps")
    paused_at: Optional[datetime] = Field(None, description="Pause timestamp")
    origin_intent_id: Optional[str] = Field(
        None, description="Origin intent ID reference"
    )
    origin_intent_label: Optional[str] = Field(None, description="Origin intent label")
    intent_confidence: Optional[float] = Field(
        None, description="Intent confidence (0-1)"
    )
    origin_suggestion_id: Optional[str] = Field(
        None, description="Origin suggestion ID"
    )
    initiator_user_id: Optional[str] = Field(None, description="Initiator user ID")
    failure_type: Optional[str] = Field(None, description="Failure type if failed")
    failure_reason: Optional[str] = Field(None, description="Failure reason if failed")
    default_cluster: Optional[str] = Field(
        None,
        description="Default cluster identifier for tool execution (e.g., 'local_mcp' or custom cluster name)",
    )

    last_checkpoint: Optional[Dict[str, Any]] = Field(
        None, description="Last checkpoint data (JSON snapshot of execution state)"
    )
    phase_summaries: List[Dict[str, Any]] = Field(
        default_factory=list, description="Phase summaries written to external memory"
    )
    supports_resume: bool = Field(
        default=True,
        description="Whether this execution supports resume from checkpoint",
    )
    storyline_tags: List[str] = Field(
        default_factory=list,
        description="Storyline tags for cross-project story tracking (e.g., brand storylines, learning paths, research themes)",
    )
    sandbox_id: Optional[str] = Field(
        None, description="Sandbox ID associated with this execution (if any)"
    )

    @classmethod
    def from_task(cls, task: "Task") -> "ExecutionSession":
        """Create ExecutionSession from Task

        Note: Due to Python import path issues (app.models vs backend.app.models),
        the input task may be a different class than the Task defined in this module.
        We handle this by converting to dict and reconstructing if needed.
        """
        # Handle Task from different import paths (app.models vs backend.app.models)
        # by converting to dict and reconstructing as local Task
        if not isinstance(task, Task):
            if hasattr(task, "model_dump"):
                task_dict = task.model_dump()
            elif hasattr(task, "dict"):
                task_dict = task.dict()
            else:
                task_dict = {
                    "id": task.id,
                    "workspace_id": task.workspace_id,
                    "message_id": task.message_id,
                    "execution_id": getattr(task, "execution_id", None),
                    "project_id": getattr(task, "project_id", None),
                    "pack_id": task.pack_id,
                    "task_type": task.task_type,
                    "status": task.status,
                    "params": task.params,
                    "result": getattr(task, "result", None),
                    "execution_context": getattr(task, "execution_context", None),
                    "storyline_tags": getattr(task, "storyline_tags", []),
                    "created_at": getattr(task, "created_at", None),
                    "started_at": getattr(task, "started_at", None),
                    "completed_at": getattr(task, "completed_at", None),
                    "error": getattr(task, "error", None),
                }
            task = Task.model_validate(task_dict)

        execution_context = task.execution_context or {}
        return cls(
            execution_id=task.execution_id or task.id,
            workspace_id=task.workspace_id,
            task=task,
            playbook_code=execution_context.get("playbook_code"),
            playbook_version=execution_context.get("playbook_version"),
            trigger_source=execution_context.get("trigger_source"),
            current_step_index=execution_context.get("current_step_index", 0),
            total_steps=execution_context.get("total_steps", 0),
            paused_at=(
                datetime.fromisoformat(execution_context["paused_at"])
                if execution_context.get("paused_at")
                else None
            ),
            origin_intent_id=execution_context.get("origin_intent_id"),
            origin_intent_label=execution_context.get("origin_intent_label"),
            intent_confidence=execution_context.get("intent_confidence"),
            origin_suggestion_id=execution_context.get("origin_suggestion_id"),
            initiator_user_id=execution_context.get("initiator_user_id"),
            failure_type=execution_context.get("failure_type"),
            failure_reason=execution_context.get("failure_reason"),
            default_cluster=execution_context.get("default_cluster"),
            last_checkpoint=execution_context.get("last_checkpoint"),
            phase_summaries=execution_context.get("phase_summaries", []),
            supports_resume=execution_context.get("supports_resume", True),
            storyline_tags=task.storyline_tags or [],
            sandbox_id=execution_context.get("sandbox_id"),
        )


# ==================== Execution Chat ====================


class ExecutionChatMessage(BaseModel):
    """
    ExecutionChatMessage - per-execution chat line between driver & AI

    Built from MindEvent(event_type=EXECUTION_CHAT).
    It does not have its own table but is constructed from MindEvent records.
    """

    id: str = Field(..., description="Message ID (same as MindEvent.id)")
    execution_id: str = Field(..., description="Associated execution ID")
    step_id: Optional[str] = Field(
        None, description="Optional: step ID this message is about"
    )
    role: Literal["user", "assistant", "agent"] = Field(..., description="Message role")
    speaker: Optional[str] = Field(
        None,
        description="Speaker name (e.g., 'Hans', 'Researcher', 'Script Assistant')",
    )
    content: str = Field(..., description="Message content")
    message_type: ExecutionChatMessageType = Field(
        default=ExecutionChatMessageType.QUESTION,
        description="Message type: question/note/route_proposal/system_hint",
    )
    created_at: datetime = Field(..., description="Creation timestamp")

    @classmethod
    def from_mind_event(
        cls, event: Union["MindEvent", Dict[str, Any]]
    ) -> "ExecutionChatMessage":
        """Create ExecutionChatMessage from MindEvent"""
        if hasattr(event, "payload"):
            payload = event.payload
            event_id = event.id
            timestamp = event.timestamp
        elif isinstance(event, dict):
            payload = event.get("payload", {})
            event_id = event.get("id", "")
            timestamp_str = event.get("timestamp")
            if isinstance(timestamp_str, str):
                timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            else:
                timestamp = timestamp_str if timestamp_str else _utc_now()
        else:
            payload = {}
            event_id = ""
            timestamp = _utc_now()

        message_type_str = payload.get("message_type", "question")
        try:
            message_type = ExecutionChatMessageType(message_type_str)
        except ValueError:
            message_type = ExecutionChatMessageType.QUESTION

        return cls(
            id=event_id,
            execution_id=payload.get("execution_id", ""),
            step_id=payload.get("step_id"),
            role=payload.get("role", "user"),
            speaker=payload.get("speaker"),
            content=payload.get("content", ""),
            message_type=message_type,
            created_at=timestamp,
        )

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}
