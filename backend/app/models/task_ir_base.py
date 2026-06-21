"""Base enums and models for the Task IR public facade."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from backend.app.services.orchestration.meeting.planner_contract_execution.models import (
    PlannerContractBinding,
)


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


class TaskStatus(str, Enum):
    """Task execution status."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class PhaseStatus(str, Enum):
    """Phase execution status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ExecutionEngine(str, Enum):
    """Well-known execution engines."""

    PLAYBOOK = "playbook"
    SKILL = "skill"
    MCP = "mcp"
    N8N = "n8n"
    LOCAL = "local"
    MEETING = "meeting"
    EXTERNAL = "external"


class ArtifactType(str, Enum):
    """Artifact content types."""

    TEXT_MARKDOWN = "text/markdown"
    TEXT_PLAIN = "text/plain"
    APPLICATION_JSON = "application/json"
    APPLICATION_PDF = "application/pdf"
    IMAGE_PNG = "image/png"
    IMAGE_JPEG = "image/jpeg"
    VIDEO_MP4 = "video/mp4"
    AUDIO_MP3 = "audio/mp3"


class ArtifactReference(BaseModel):
    """Reference to an artifact produced during task execution."""

    id: str = Field(..., description="Unique artifact identifier")
    type: str = Field(
        ..., description="MIME type (e.g., 'text/markdown', 'application/json')"
    )
    source: str = Field(
        ...,
        description="Source engine (e.g., 'playbook:yoga_course_outline', 'skill:policy_research')",
    )
    uri: str = Field(..., description="File path or external URL")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="Creation timestamp"
    )

    compiled_prompt_hash: Optional[str] = Field(
        None, description="Hash of the compiled prompt used to produce this artifact"
    )
    output_hash: Optional[str] = Field(
        None, description="Content hash for deduplication / change detection"
    )
    eval_summary: Optional[Dict[str, Any]] = Field(
        None, description="AcceptanceEvaluator result summary"
    )
    provenance_schema_version: Optional[str] = Field(
        None, description="Schema version of the provenance payload"
    )
    approved_by: Optional[str] = Field(
        None, description="Approver ID (human or automated judge)"
    )
    context_attachments: Optional[List[Dict[str, Any]]] = Field(
        None, description="Evidence provenance attachments from pack pipeline"
    )

    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})


class PhaseIR(BaseModel):
    """Phase intermediate representation."""

    id: str = Field(..., description="Unique phase identifier")
    name: str = Field(..., description="Human-readable phase name")
    description: Optional[str] = Field(None, description="Phase description")

    status: str = Field(default=PhaseStatus.PENDING, description="Current phase status")

    preferred_engine: Optional[str] = Field(
        None,
        description="Preferred execution engine (e.g., 'playbook:yoga_course_outline', 'skill:policy_research')",
    )
    executed_by: Optional[str] = Field(
        None, description="Actual engine that executed this phase"
    )
    execution_id: Optional[str] = Field(
        None, description="Execution ID from the engine that ran this phase"
    )

    summary_artifact: Optional[str] = Field(
        None, description="ID of summary artifact for this phase"
    )
    output_artifacts: List[str] = Field(
        default_factory=list, description="List of artifact IDs produced by this phase"
    )

    depends_on: Optional[List[str]] = Field(
        None, description="List of phase IDs this phase depends on"
    )

    input_artifacts: Optional[List[str]] = Field(
        None, description="Artifact IDs required as input"
    )
    gate: Optional[str] = Field(
        None, description="HITL gate identifier before execution"
    )
    checkpoint_label: Optional[str] = Field(
        None, description="Named checkpoint for rollback"
    )
    action_space: Optional[str] = Field(
        None, description="Allowed side-effect level for this phase"
    )
    rollback_strategy: Optional[str] = Field(
        None, description="Rollback strategy (revert/retry/skip)"
    )

    target_workspace_id: Optional[str] = Field(
        None,
        description="Target workspace for execution (from planner asset-boundary routing)",
    )
    asset_refs: List[str] = Field(
        default_factory=list,
        description="Asset URNs this phase depends on (for DataLocality validation)",
    )

    tool_name: Optional[str] = Field(
        None,
        description="Direct tool name for tool_execution task type",
    )
    input_params: Optional[Dict[str, Any]] = Field(
        None,
        description="Input parameters for tool invocation",
    )
    planner_contract_binding: Optional[PlannerContractBinding] = Field(
        None,
        description="Deterministic binding to an installed planner_contract tool",
    )
    blocked_by: Optional[List[int]] = Field(
        None,
        description="Indices of action items that must complete before this phase",
    )

    latest_attempt_id: Optional[str] = Field(
        None,
        description="ID of the latest PhaseAttempt for this phase",
    )

    capability_profile: Optional[str] = Field(
        None,
        description="Capability profile for model selection (from meeting role or ProgramSpec)",
    )

    started_at: Optional[datetime] = Field(None, description="Phase start timestamp")
    completed_at: Optional[datetime] = Field(
        None, description="Phase completion timestamp"
    )

    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})


GOVERNANCE_SCHEMA_VERSION = "0.1"


class GovernanceContext(BaseModel):
    """Typed governance context stored in ExecutionMetadata.governance."""

    schema_version: str = Field(default=GOVERNANCE_SCHEMA_VERSION)
    goals: Optional[List[str]] = None
    non_goals: Optional[List[str]] = None
    deliverables: Optional[List[Dict[str, Any]]] = None
    constraints: Optional[Dict[str, Any]] = None
    acceptance_tests: Optional[List[str]] = None
    risk_profile: Optional[Dict[str, Any]] = None
    open_questions: Optional[List[str]] = None
    lens_snapshot_ref: Optional[str] = None
    memory_refs: Optional[List[str]] = None
    handoff_id: Optional[str] = None

    trace_id: Optional[str] = None
    governance_constraints: Optional[Dict[str, Any]] = None
    requested_output_type: Optional[str] = None
    human_instructions: Optional[str] = None
    context_attachments: Optional[List[Dict[str, Any]]] = None


class ExecutionMetadata(BaseModel):
    """Standardized execution metadata structure."""

    intent: Optional[Dict[str, str]] = Field(
        None, description="Intent-related IDs: {intent_id, intent_instance_id}"
    )
    execution: Optional[Dict[str, str]] = Field(
        None,
        description="Execution-related IDs: {playbook_code, playbook_execution_id, skill_id, skill_execution_id}",
    )
    cloud: Optional[Dict[str, str]] = Field(
        None, description="Cloud-related IDs: {tenant_id, cloud_workspace_id, job_id}"
    )
    governance: Optional[Dict[str, Any]] = Field(
        None, description="Governance context validated by GovernanceContext model"
    )

    def get_intent_id(self) -> Optional[str]:
        """Get intent ID."""
        return self.intent.get("intent_id") if self.intent else None

    def get_intent_instance_id(self) -> Optional[str]:
        """Get intent instance ID."""
        return self.intent.get("intent_instance_id") if self.intent else None

    def get_playbook_code(self) -> Optional[str]:
        """Get playbook code."""
        return self.execution.get("playbook_code") if self.execution else None

    def get_playbook_execution_id(self) -> Optional[str]:
        """Get playbook execution ID."""
        return self.execution.get("playbook_execution_id") if self.execution else None

    def get_skill_id(self) -> Optional[str]:
        """Get skill ID."""
        return self.execution.get("skill_id") if self.execution else None

    def get_skill_execution_id(self) -> Optional[str]:
        """Get skill execution ID."""
        return self.execution.get("skill_execution_id") if self.execution else None

    def get_tenant_id(self) -> Optional[str]:
        """Get tenant ID."""
        return self.cloud.get("tenant_id") if self.cloud else None

    def get_cloud_workspace_id(self) -> Optional[str]:
        """Get cloud workspace ID."""
        return self.cloud.get("cloud_workspace_id") if self.cloud else None

    def get_job_id(self) -> Optional[str]:
        """Get job ID."""
        return self.cloud.get("job_id") if self.cloud else None

    def set_execution_context(self, **kwargs) -> None:
        """Set execution-related metadata fields."""
        if self.execution is None:
            self.execution = {}
        self.execution.update(kwargs)

    def set_intent_context(self, **kwargs) -> None:
        """Set intent-related metadata fields."""
        if self.intent is None:
            self.intent = {}
        self.intent.update(kwargs)

    def get_governance(self) -> Optional["GovernanceContext"]:
        """Deserialize governance dict into typed GovernanceContext."""
        if not self.governance:
            return None
        return GovernanceContext(**self.governance)

    def set_governance(self, ctx: "GovernanceContext") -> None:
        """Serialize typed GovernanceContext into governance dict."""
        self.governance = ctx.model_dump()


class CheckpointSnapshot(BaseModel):
    """Saved state at a named checkpoint for rollback."""

    checkpoint_id: str = Field(..., description="Unique checkpoint identifier")
    label: str = Field(..., description="Human-readable checkpoint name")
    task_id: str = Field(..., description="Task this checkpoint belongs to")
    phase_id: str = Field(..., description="Phase about to execute when snapshot taken")
    snapshot: Dict[str, Any] = Field(
        ..., description="Serialized TaskIR state at checkpoint"
    )
    created_at: datetime = Field(
        default_factory=_utc_now, description="Checkpoint creation timestamp"
    )

    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})
