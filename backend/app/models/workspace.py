"""
Workspace model for unified frontend interface

Workspace serves as the "cockpit" - a single entry point for:
- Chat interactions
- File uploads
- Playbook execution
- Task/progress viewing

All activities happen within a Workspace context, which can be associated
with one or more Projects/Themes and can receive events from multiple channels.
"""

from datetime import datetime
from typing import Optional, Dict, Any, List, TYPE_CHECKING, Union, Literal
from enum import Enum
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from ...models.mindscape import MindEvent


# ==================== Enums ====================

class SideEffectLevel(str, Enum):
    """
    Side effect level for capability packs and tools

    Determines execution strategy:
    - READONLY: Read-only analysis, can be executed automatically
    - SOFT_WRITE: Internal state writes, requires CTA confirmation
    - EXTERNAL_WRITE: External system writes, requires explicit confirmation
    """
    READONLY = "readonly"
    SOFT_WRITE = "soft_write"
    EXTERNAL_WRITE = "external_write"


class TaskStatus(str, Enum):
    """Task execution status"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED_BY_USER = "cancelled_by_user"
    EXPIRED = "expired"


class TimelineItemType(str, Enum):
    """Timeline item type"""
    INTENT_SEEDS = "INTENT_SEEDS"
    PLAN = "PLAN"
    SUMMARY = "SUMMARY"
    DRAFT = "DRAFT"
    ERROR = "ERROR"
    PROJECT_SUGGESTION = "PROJECT_SUGGESTION"


class ArtifactType(str, Enum):
    """Artifact type for playbook outputs"""
    CHECKLIST = "checklist"
    DRAFT = "draft"
    CONFIG = "config"
    CANVA = "canva"
    AUDIO = "audio"
    DOCX = "docx"
    FILE = "file"
    LINK = "link"
    POST = "post"
    IMAGE = "image"
    VIDEO = "video"
    CODE = "code"
    DATA = "data"


class PrimaryActionType(str, Enum):
    """Primary action type for artifact operations"""
    COPY = "copy"
    DOWNLOAD = "download"
    OPEN_EXTERNAL = "open_external"
    PUBLISH_WP = "publish_wp"
    NAVIGATE = "navigate"
    PREVIEW = "preview"
    EDIT = "edit"
    SHARE = "share"


class ExecutionChatMessageType(str, Enum):
    """
    Execution chat message type

    - question: User asking about current step/design
    - note: User's note or thought
    - route_proposal: AI proposing next route/branch
    - system_hint: System-generated hint or suggestion
    """
    QUESTION = "question"
    NOTE = "note"
    ROUTE_PROPOSAL = "route_proposal"
    SYSTEM_HINT = "system_hint"


class ExecutionMode(str, Enum):
    """
    Workspace execution mode

    Determines how the AI agent behaves:
    - QA: Chat-focused, discuss before acting
    - EXECUTION: Action-first, produce artifacts immediately
    - HYBRID: Balanced between chat and execution
    """
    QA = "qa"
    EXECUTION = "execution"
    HYBRID = "hybrid"


class ExecutionPriority(str, Enum):
    """
    Execution priority level

    Affects auto-execution confidence threshold:
    - LOW: Conservative, high confidence required (0.9)
    - MEDIUM: Balanced, default threshold (0.8)
    - HIGH: Aggressive, lower threshold (0.6), readonly tasks auto-execute
    """
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ProjectAssignmentMode(str, Enum):
    """
    Project assignment automation level

    Similar to playbook auto-execution, controls how project assignment decisions are made:
    - auto_silent: Auto-assign with minimal UI (default for most users)
    - assistive: Auto-assign with confirmation prompts for medium/low confidence
    - manual_first: Require user selection (for power users)
    """
    AUTO_SILENT = "auto_silent"
    ASSISTIVE = "assistive"
    MANUAL_FIRST = "manual_first"


# ==================== Workspace Models ====================

class Workspace(BaseModel):
    """
    Workspace model - unified frontend interface container

    A Workspace is a top-level container that represents a user's working context.
    It aggregates events from multiple channels (local_chat, line, wp, etc.)
    and provides a unified timeline view.

    Key characteristics:
    - One Workspace can be associated with one or more Projects/Themes
    - Multiple channels can feed events into the same Workspace
    - All user interactions (chat, file upload, playbook execution) happen within a Workspace
    """

    id: str = Field(..., description="Unique workspace identifier")
    title: str = Field(..., description="Workspace display title")
    description: Optional[str] = Field(None, description="Workspace description")

    # Owner and primary associations
    owner_user_id: str = Field(..., description="Owner profile ID")
    primary_project_id: Optional[str] = Field(
        None,
        description="Primary associated project ID (if applicable)"
    )

    # Optional configuration
    default_playbook_id: Optional[str] = Field(
        None,
        description="Default playbook to use for this workspace"
    )
    default_locale: Optional[str] = Field(
        None,
        description="Default locale for this workspace (e.g., 'zh-TW', 'en')"
    )
    mode: Optional[str] = Field(
        None,
        description="Workspace mode: 'research' | 'publishing' | 'planning' | null"
    )
    data_sources: Optional[Dict[str, Any]] = Field(
        None,
        description="Data sources configuration: local_folder, obsidian_vault, wordpress, rag_source"
    )
    playbook_auto_execution_config: Optional[Dict[str, Any]] = Field(
        None,
        description="Playbook auto-execution configuration: {playbook_code: {confidence_threshold: float, auto_execute: bool}}"
    )
    suggestion_history: Optional[List[Dict[str, Any]]] = Field(
        None,
        description="Suggestion history (last 3 rounds): [{round_id, timestamp, suggestions: [...]}]"
    )

    # Storage configuration
    storage_base_path: Optional[str] = Field(
        None,
        description="Workspace base storage path (e.g., ~/Documents/Mindscape/workspace_name)"
    )
    artifacts_dir: Optional[str] = Field(
        "artifacts",
        description="Artifacts subdirectory (default: 'artifacts')"
    )
    uploads_dir: Optional[str] = Field(
        "uploads",
        description="Uploads subdirectory (default: 'uploads')"
    )
    storage_config: Optional[Dict[str, Any]] = Field(
        None,
        description="Storage configuration (bucket rules, naming rules, etc.)"
    )
    playbook_storage_config: Optional[Dict[str, Dict[str, Any]]] = Field(
        None,
        description="Playbook-specific storage configuration: "
                    "{playbook_code: {base_path: str, artifacts_dir: str}}"
    )

    # Execution mode configuration
    execution_mode: Optional[str] = Field(
        default="qa",
        description="Workspace execution mode: 'qa' | 'execution' | 'hybrid'"
    )
    expected_artifacts: Optional[List[str]] = Field(
        default=None,
        description="Expected artifact types for this workspace (e.g., ['pptx', 'xlsx', 'docx'])"
    )
    execution_priority: Optional[str] = Field(
        default="medium",
        description="Execution priority: 'low' | 'medium' | 'high'"
    )

    # Project assignment configuration
    project_assignment_mode: Optional[ProjectAssignmentMode] = Field(
        default=ProjectAssignmentMode.AUTO_SILENT,
        description="Project assignment automation level"
    )

    # Extensible metadata for features (core_memory, preferences, etc.)
    metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Extensible metadata storage for workspace features (core_memory, preferences, etc.)"
    )

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


# ==================== API Request/Response Models ====================

class CreateWorkspaceRequest(BaseModel):
    """Request to create a new workspace"""
    title: str = Field(..., description="Workspace title")
    description: Optional[str] = Field(None, description="Workspace description")
    primary_project_id: Optional[str] = Field(None, description="Primary project ID to associate")
    default_playbook_id: Optional[str] = Field(None, description="Default playbook ID")
    default_locale: Optional[str] = Field(None, description="Default locale")
    storage_base_path: Optional[str] = Field(None, description="Storage base path (allows manual specification)")
    artifacts_dir: Optional[str] = Field(None, description="Artifacts directory name (default: 'artifacts')")
    execution_mode: Optional[str] = Field(None, description="Execution mode: 'qa' | 'execution' | 'hybrid'")
    expected_artifacts: Optional[List[str]] = Field(None, description="Expected artifact types")
    execution_priority: Optional[str] = Field(None, description="Execution priority: 'low' | 'medium' | 'high'")


class UpdateWorkspaceRequest(BaseModel):
    """Request to update an existing workspace"""
    title: Optional[str] = Field(None, description="Workspace title")
    description: Optional[str] = Field(None, description="Workspace description")
    primary_project_id: Optional[str] = Field(None, description="Primary project ID")
    default_playbook_id: Optional[str] = Field(None, description="Default playbook ID")
    default_locale: Optional[str] = Field(None, description="Default locale")
    mode: Optional[str] = Field(None, description="Workspace mode: 'research' | 'publishing' | 'planning' | null")
    storage_base_path: Optional[str] = Field(None, description="Storage base path (Changing this may affect existing artifacts)")
    artifacts_dir: Optional[str] = Field(None, description="Artifacts directory name (Changing this may affect existing artifacts)")
    playbook_storage_config: Optional[Dict[str, Dict[str, Any]]] = Field(
        None,
        description="Playbook-specific storage configuration: "
                    "{playbook_code: {base_path: str, artifacts_dir: str}}"
    )
    execution_mode: Optional[str] = Field(None, description="Execution mode: 'qa' | 'execution' | 'hybrid'")
    expected_artifacts: Optional[List[str]] = Field(None, description="Expected artifact types")
    execution_priority: Optional[str] = Field(None, description="Execution priority: 'low' | 'medium' | 'high'")


class WorkspaceChatRequest(BaseModel):
    """Request for workspace chat interaction"""
    message: Optional[str] = Field(None, description="User message")
    files: list[str] = Field(default_factory=list, description="List of uploaded file IDs")
    mode: str = Field(
        default="auto",
        description="Interaction mode: 'auto' | 'qa_only' | 'force_playbook'"
    )
    stream: bool = Field(default=True, description="Enable streaming response (SSE)")
    project_id: Optional[str] = Field(None, description="Project ID for project context")
    # CTA trigger fields
    timeline_item_id: Optional[str] = Field(None, description="Timeline item ID for CTA action")
    action: Optional[str] = Field(None, description="Action type: 'add_to_intents' | 'add_to_tasks' | 'publish_to_wordpress' | 'execute_playbook' | 'use_tool' | 'create_intent' | 'start_chat' | 'upload_file'")
    confirm: Optional[bool] = Field(None, description="Confirmation flag for external_write actions")
    action_params: Optional[Dict[str, Any]] = Field(None, description="Action parameters (for dynamic suggestions)")


class WorkspaceChatResponse(BaseModel):
    """Response from workspace chat interaction"""
    workspace_id: str = Field(..., description="Workspace ID")
    display_events: list[dict] = Field(
        default_factory=list,
        description="Recent events to display in timeline"
    )
    triggered_playbook: Optional[dict] = Field(
        None,
        description="Triggered playbook information (if any)"
    )
    pending_tasks: list[dict] = Field(
        default_factory=list,
        description="Pending task status cards"
    )


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
    playbook_code: Optional[str] = Field(None, description="Playbook to execute (if applicable)")
    tool_name: Optional[str] = Field(None, description="Tool to use (if applicable)")
    artifacts: List[str] = Field(default_factory=list, description="Expected artifact types (e.g., ['pptx', 'docx'])")
    reasoning: Optional[str] = Field(None, description="Why this step was chosen (CoT reasoning)")
    depends_on: List[str] = Field(default_factory=list, description="Step IDs this depends on")
    requires_confirmation: bool = Field(False, description="Whether user confirmation is needed")
    side_effect_level: Optional[str] = Field(None, description="Side effect level: readonly/soft_write/external_write")
    estimated_duration: Optional[str] = Field(None, description="Estimated duration (e.g., '30s', '2m')")


class TaskPlan(BaseModel):
    """
    TaskPlan model - represents a planned task in an execution plan

    Used internally by ConversationOrchestrator to plan task execution
    based on side_effect_level and user intent.
    """
    pack_id: str = Field(..., description="Pack identifier")
    task_type: str = Field(..., description="Task type (e.g., 'extract_intents', 'generate_tasks')")
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
    id: str = Field(default_factory=lambda: str(__import__('uuid').uuid4()), description="Plan ID")
    message_id: str = Field(..., description="Associated message/event ID")
    workspace_id: str = Field(..., description="Workspace ID")

    # Chain-of-Thought fields
    user_request_summary: Optional[str] = Field(None, description="Summary of what user asked for")
    reasoning: Optional[str] = Field(None, description="Overall reasoning for the plan (CoT)")
    plan_summary: Optional[str] = Field(None, description="Human-readable summary for display")
    steps: List[ExecutionStep] = Field(default_factory=list, description="Execution steps (CoT)")

    # Legacy compatibility - kept for backward compatibility
    tasks: List[TaskPlan] = Field(default_factory=list, description="Planned tasks (legacy)")

    # Metadata
    execution_mode: Optional[str] = Field(None, description="qa/execution/hybrid")
    confidence: Optional[float] = Field(None, description="LLM confidence in this plan (0-1)")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")

    # Project and Phase association
    project_id: Optional[str] = Field(None, description="Associated Project ID")
    phase_id: Optional[str] = Field(None, description="Associated Project Phase ID")
    project_assignment_decision: Optional[Dict[str, Any]] = Field(
        None,
        description="Project assignment decision: {project_id, relation, confidence, reasoning, candidates}"
    )

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

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
            "artifact_count": sum(len(s.artifacts) for s in self.steps)
        }

        metadata = getattr(self, "metadata", None) or {}
        effective_playbooks = metadata.get("effective_playbooks")
        if effective_playbooks is not None:
            payload["effective_playbooks"] = effective_playbooks
            payload["effective_playbooks_count"] = len(effective_playbooks)

        if self.tasks:
            try:
                from backend.app.services.ai_team_service import get_members_from_tasks
                playbook_code = None
                if self.steps and len(self.steps) > 0:
                    playbook_code = getattr(self.steps[0], 'playbook_code', None)
                elif self.tasks and len(self.tasks) > 0:
                    first_task = self.tasks[0]
                    if hasattr(first_task, 'playbook_code') and first_task.playbook_code:
                        playbook_code = first_task.playbook_code
                    elif hasattr(first_task, 'params') and isinstance(first_task.params, dict):
                        playbook_code = first_task.params.get('playbook_code')

                ai_team_members = get_members_from_tasks(self.tasks, playbook_code)
                logger.info(f"[ExecutionPlan] Extracted {len(ai_team_members)} AI team members from {len(self.tasks)} tasks, playbook_code={playbook_code}")
                if ai_team_members:
                    payload["ai_team_members"] = ai_team_members
                    logger.info(f"[ExecutionPlan] Added ai_team_members to payload: {[m.get('name_zh') or m.get('name') for m in ai_team_members]}")
                else:
                    logger.warning(f"[ExecutionPlan] No AI team members extracted from tasks")
            except Exception as e:
                logger.warning(f"Failed to extract AI team members: {e}", exc_info=True)

        return payload


# ==================== Task Models ====================

class Task(BaseModel):
    """
    Task model - represents a single execution task from a Pack

    Tasks are derived from MindEvents and stored in the tasks table.
    They represent the execution state of a Pack within a workspace.
    """
    id: str = Field(..., description="Unique task identifier")
    workspace_id: str = Field(..., description="Workspace ID")
    message_id: str = Field(..., description="Associated message/event ID")
    execution_id: Optional[str] = Field(
        None,
        description="Associated playbook execution ID (if applicable)"
    )
    pack_id: str = Field(..., description="Pack identifier")
    task_type: str = Field(..., description="Task type (e.g., 'extract_intents', 'generate_tasks')")
    status: TaskStatus = Field(..., description="Task execution status")
    params: Dict[str, Any] = Field(default_factory=dict, description="Task parameters")
    result: Optional[Dict[str, Any]] = Field(None, description="Task execution result")
    execution_context: Optional[Dict[str, Any]] = Field(
        None,
        description="Execution context (playbook_code, trigger_source, current_step_index, etc.)"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")
    started_at: Optional[datetime] = Field(None, description="Task start timestamp")
    completed_at: Optional[datetime] = Field(None, description="Task completion timestamp")
    error: Optional[str] = Field(None, description="Error message if task failed")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


# ==================== Execution Models ====================

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
    trigger_source: Optional[str] = Field(None, description="Trigger source: auto/suggestion/manual")
    current_step_index: int = Field(default=0, description="Current step index (0-based)")
    total_steps: int = Field(default=0, description="Total number of steps")
    paused_at: Optional[datetime] = Field(None, description="Pause timestamp")
    origin_intent_id: Optional[str] = Field(None, description="Origin intent ID reference")
    origin_intent_label: Optional[str] = Field(None, description="Origin intent label")
    intent_confidence: Optional[float] = Field(None, description="Intent confidence (0-1)")
    origin_suggestion_id: Optional[str] = Field(None, description="Origin suggestion ID")
    initiator_user_id: Optional[str] = Field(None, description="Initiator user ID")
    failure_type: Optional[str] = Field(None, description="Failure type if failed")
    failure_reason: Optional[str] = Field(None, description="Failure reason if failed")
    default_cluster: Optional[str] = Field(None, description="Default cluster identifier for tool execution (e.g., 'local_mcp' or custom cluster name)")

    last_checkpoint: Optional[Dict[str, Any]] = Field(
        None,
        description="Last checkpoint data (JSON snapshot of execution state)"
    )
    phase_summaries: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Phase summaries written to external memory"
    )
    supports_resume: bool = Field(
        default=True,
        description="Whether this execution supports resume from checkpoint"
    )

    @classmethod
    def from_task(cls, task: Task) -> "ExecutionSession":
        """Create ExecutionSession from Task"""
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
            paused_at=datetime.fromisoformat(execution_context["paused_at"]) if execution_context.get("paused_at") else None,
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
            supports_resume=execution_context.get("supports_resume", True)
        )


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
    total_steps: Optional[int] = Field(None, description="Total number of steps in this execution")
    status: str = Field(..., description="Status: pending/running/completed/failed/waiting_confirmation")
    step_type: str = Field(..., description="Step type: agent_action/tool_call/agent_collaboration/user_confirmation")
    agent_type: Optional[str] = Field(None, description="Agent type: researcher/editor/engineer")
    used_tools: Optional[List[str]] = Field(None, description="List of tools used in this step")
    assigned_agent: Optional[str] = Field(None, description="Assigned agent")
    collaborating_agents: Optional[List[str]] = Field(None, description="Collaborating agents")
    description: Optional[str] = Field(None, description="Step description")
    log_summary: Optional[str] = Field(None, description="One-line log summary")
    requires_confirmation: bool = Field(default=False, description="Whether step requires user confirmation")
    confirmation_prompt: Optional[str] = Field(None, description="Confirmation prompt text")
    confirmation_status: Optional[str] = Field(None, description="Confirmation status: pending/confirmed/rejected")
    intent_id: Optional[str] = Field(None, description="Associated intent ID")
    started_at: Optional[datetime] = Field(None, description="Start timestamp")
    completed_at: Optional[datetime] = Field(None, description="Completion timestamp")
    error: Optional[str] = Field(None, description="Error message if failed")
    failure_type: Optional[str] = Field(None, description="Failure type if failed")

    @classmethod
    def from_mind_event(cls, event: Union["MindEvent", Dict[str, Any]]) -> "PlaybookExecutionStep":
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
            started_at=datetime.fromisoformat(payload["started_at"]) if payload.get("started_at") else None,
            completed_at=datetime.fromisoformat(payload["completed_at"]) if payload.get("completed_at") else None,
            error=payload.get("error"),
            failure_type=payload.get("failure_type")
        )


class PlaybookExecution(BaseModel):
    """
    PlaybookExecution model - represents a playbook execution record

    This is the persistent record for playbook executions with checkpoint/resume support.
    """
    id: str = Field(..., description="Execution ID")
    workspace_id: str = Field(..., description="Workspace ID")
    playbook_code: str = Field(..., description="Playbook code")
    intent_instance_id: Optional[str] = Field(None, description="Origin intent instance ID")
    status: str = Field(..., description="Execution status: running/paused/done/failed")
    phase: Optional[str] = Field(None, description="Current phase ID")
    last_checkpoint: Optional[str] = Field(None, description="Last checkpoint data (JSON)")
    progress_log_path: Optional[str] = Field(None, description="Progress log file path")
    feature_list_path: Optional[str] = Field(None, description="Feature list file path")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ExecutionChatMessage(BaseModel):
    """
    ExecutionChatMessage - per-execution chat line between driver & AI

    Built from MindEvent(event_type=EXECUTION_CHAT).
    It does not have its own table but is constructed from MindEvent records.
    """
    id: str = Field(..., description="Message ID (same as MindEvent.id)")
    execution_id: str = Field(..., description="Associated execution ID")
    step_id: Optional[str] = Field(None, description="Optional: step ID this message is about")
    role: Literal["user", "assistant", "agent"] = Field(..., description="Message role")
    speaker: Optional[str] = Field(None, description="Speaker name (e.g., 'Hans', 'Researcher', 'Script Assistant')")
    content: str = Field(..., description="Message content")
    message_type: ExecutionChatMessageType = Field(
        default=ExecutionChatMessageType.QUESTION,
        description="Message type: question/note/route_proposal/system_hint"
    )
    created_at: datetime = Field(..., description="Creation timestamp")

    @classmethod
    def from_mind_event(cls, event: Union["MindEvent", Dict[str, Any]]) -> "ExecutionChatMessage":
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
                timestamp = timestamp_str if timestamp_str else datetime.utcnow()
        else:
            payload = {}
            event_id = ""
            timestamp = datetime.utcnow()

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
            created_at=timestamp
        )

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


# ==================== TimelineItem Models ====================

class TimelineItem(BaseModel):
    """
    TimelineItem model - represents a result card displayed in the timeline

    TimelineItems are derived from MindEvents and stored in the timeline_items table.
    They represent the results of Pack executions and are displayed in the right panel.
    """
    id: str = Field(..., description="Unique timeline item identifier")
    workspace_id: str = Field(..., description="Workspace ID")
    message_id: str = Field(..., description="Associated message/event ID")
    task_id: Optional[str] = Field(None, description="Associated task ID (optional for file analysis items)")
    type: TimelineItemType = Field(..., description="Timeline item type")
    title: str = Field(..., description="Display title")
    summary: str = Field(..., description="Summary text")
    data: Dict[str, Any] = Field(default_factory=dict, description="Additional data")
    cta: Optional[List[Dict[str, Any]]] = Field(
        None,
        description="Call-to-action buttons (if applicable)"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


# ==================== Artifact Models ====================

class Artifact(BaseModel):
    """
    Artifact model - represents a playbook execution output

    Artifacts are automatically created when playbooks complete execution.
    They represent the tangible outputs (checklists, drafts, configs, etc.)
    that users can view, copy, download, or publish.
    """
    id: str = Field(..., description="Unique artifact identifier")
    workspace_id: str = Field(..., description="Workspace ID")
    intent_id: Optional[str] = Field(
        None,
        description="Associated Intent ID (supports driver-led experience)"
    )
    task_id: Optional[str] = Field(None, description="Associated task ID")
    execution_id: Optional[str] = Field(None, description="Associated execution ID")
    playbook_code: str = Field(..., description="Source playbook code")
    artifact_type: ArtifactType = Field(..., description="Artifact type")
    title: str = Field(..., description="Artifact title")
    summary: str = Field(..., description="Artifact summary")
    content: Dict[str, Any] = Field(default_factory=dict, description="Artifact content (JSON)")
    storage_ref: Optional[str] = Field(
        None,
        description="Storage location: DB/file path/external URL (supports external sync)"
    )
    sync_state: Optional[str] = Field(
        None,
        description="Sync state: None (local) / pending / synced / failed (for external sync)"
    )
    primary_action_type: PrimaryActionType = Field(..., description="Primary action type")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


# ==================== Background Routine Models ====================

class BackgroundRoutine(BaseModel):
    """
    BackgroundRoutine model - represents a long-running background task

    Background routines are like cron jobs / daemons that run on a schedule.
    Once enabled, they run automatically without requiring user confirmation for each execution.
    Examples: habit_learning, daily_reminders
    """
    id: str = Field(..., description="Unique background routine identifier")
    workspace_id: str = Field(..., description="Workspace ID")
    playbook_code: str = Field(..., description="Playbook code to run")
    enabled: bool = Field(default=False, description="Whether the routine is enabled")
    config: Dict[str, Any] = Field(default_factory=dict, description="Schedule and condition configuration")
    last_run_at: Optional[datetime] = Field(None, description="Last execution timestamp")
    next_run_at: Optional[datetime] = Field(None, description="Next scheduled execution timestamp")
    last_status: Optional[str] = Field(None, description="Last execution status: 'ok' | 'failed'")

    # Tool dependency readiness status (system-managed, stored as separate columns)
    readiness_status: Optional[str] = Field(
        default=None,
        description="Readiness status: ready / needs_setup / unsupported"
    )
    tool_statuses: Optional[Dict[str, str]] = Field(
        default=None,
        description="Status of required tools: tool_type -> status (JSON string in DB)"
    )
    error_count: int = Field(
        default=0,
        description="Consecutive error count (for auto-pause)"
    )
    auto_paused: bool = Field(
        default=False,
        description="Whether routine was auto-paused due to errors"
    )

    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


# ==================== Task Feedback Models ====================

class TaskFeedbackAction(str, Enum):
    """Task feedback action type"""
    ACCEPT = "accept"
    REJECT = "reject"
    DISMISS = "dismiss"


class TaskFeedbackReasonCode(str, Enum):
    """Task feedback reason code"""
    IRRELEVANT = "irrelevant"
    DUPLICATE = "duplicate"
    TOO_MANY = "too_many"
    WRONG_TIMING = "wrong_timing"
    DONT_WANT_AUTO = "dont_want_auto"
    OTHER = "other"


class TaskFeedback(BaseModel):
    """
    Task feedback model - records user feedback on AI-generated tasks

    Used to track user rejections, dismissals, and acceptances of tasks
    to improve task recommendation strategies and personalize preferences.
    """
    id: str = Field(..., description="Unique feedback identifier")
    task_id: str = Field(..., description="Associated task ID")
    workspace_id: str = Field(..., description="Workspace ID")
    user_id: str = Field(..., description="User profile ID")
    action: TaskFeedbackAction = Field(..., description="Feedback action: accept/reject/dismiss")
    reason_code: Optional[TaskFeedbackReasonCode] = Field(
        None,
        description="Reason code for rejection/dismissal (optional)"
    )
    comment: Optional[str] = Field(
        None,
        description="Optional user comment explaining the feedback"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


# ==================== Task Preference Models ====================

class TaskPreferenceAction(str, Enum):
    """Task preference action type"""
    ENABLE = "enable"
    DISABLE = "disable"
    AUTO_SUGGEST = "auto_suggest"
    MANUAL_ONLY = "manual_only"


class TaskPreference(BaseModel):
    """
    Task preference model - records user preferences for task types and packs

    Used to personalize task recommendations by tracking which packs/task_types
    the user prefers, rejects, or wants to see less frequently.
    """
    id: str = Field(..., description="Unique preference identifier")
    workspace_id: str = Field(..., description="Workspace ID")
    user_id: str = Field(..., description="User profile ID")
    pack_id: Optional[str] = Field(
        None,
        description="Pack ID (if preference is pack-level)"
    )
    task_type: Optional[str] = Field(
        None,
        description="Task type (if preference is task-level, more specific than pack_id)"
    )
    action: TaskPreferenceAction = Field(
        ...,
        description="Preference action: enable/disable/auto_suggest/manual_only"
    )
    auto_suggest: bool = Field(
        default=True,
        description="Whether to auto-suggest this pack/task_type (default: True)"
    )
    last_feedback: Optional[TaskFeedbackAction] = Field(
        None,
        description="Last feedback action (accept/reject/dismiss) for this pack/task_type"
    )
    reject_count_30d: int = Field(
        default=0,
        description="Number of rejections in the last 30 days"
    )
    accept_count_30d: int = Field(
        default=0,
        description="Number of acceptances in the last 30 days"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
