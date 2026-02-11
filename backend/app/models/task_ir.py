"""
Task IR (Task Intermediate Representation) Schema

Task IR is the unified intermediate representation for cross-engine task execution,
enabling seamless handoffs between different execution engines (Playbook, Claude Skills, MCP, n8n).

This follows the "EDL/XML" analogy - just as video editing uses intermediate formats
for interoperability between Davinci, PR, and AE, Task IR enables interoperability
between different AI execution engines.
"""

from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
from typing import Dict, Any, List, Optional, Union
from enum import Enum
from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """Task execution status"""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class PhaseStatus(str, Enum):
    """Phase execution status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ExecutionEngine(str, Enum):
    """Supported execution engines"""
    PLAYBOOK = "playbook"
    SKILL = "skill"
    MCP = "mcp"
    N8N = "n8n"
    LOCAL = "local"


class ArtifactType(str, Enum):
    """Artifact content types"""
    TEXT_MARKDOWN = "text/markdown"
    TEXT_PLAIN = "text/plain"
    APPLICATION_JSON = "application/json"
    APPLICATION_PDF = "application/pdf"
    IMAGE_PNG = "image/png"
    IMAGE_JPEG = "image/jpeg"
    VIDEO_MP4 = "video/mp4"
    AUDIO_MP3 = "audio/mp3"


class ArtifactReference(BaseModel):
    """
    Reference to an artifact produced during task execution

    Artifacts are the "media files" in our video editing analogy -
    they can be text, images, JSON data, or any output from execution.
    """
    id: str = Field(..., description="Unique artifact identifier")
    type: str = Field(..., description="MIME type (e.g., 'text/markdown', 'application/json')")
    source: str = Field(..., description="Source engine (e.g., 'playbook:yoga_course_outline', 'skill:policy_research')")
    uri: str = Field(..., description="File path or external URL")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class PhaseIR(BaseModel):
    """
    Phase Intermediate Representation

    A phase represents a logical step in task execution.
    Phases can be executed by different engines and can depend on each other.
    """
    id: str = Field(..., description="Unique phase identifier")
    name: str = Field(..., description="Human-readable phase name")
    description: Optional[str] = Field(None, description="Phase description")

    status: str = Field(default=PhaseStatus.PENDING, description="Current phase status")

    # Execution preferences
    preferred_engine: Optional[str] = Field(
        None,
        description="Preferred execution engine (e.g., 'playbook:yoga_course_outline', 'skill:policy_research')"
    )
    executed_by: Optional[str] = Field(
        None,
        description="Actual engine that executed this phase"
    )
    execution_id: Optional[str] = Field(
        None,
        description="Execution ID from the engine that ran this phase"
    )

    # Results
    summary_artifact: Optional[str] = Field(
        None,
        description="ID of summary artifact for this phase"
    )
    output_artifacts: List[str] = Field(
        default_factory=list,
        description="List of artifact IDs produced by this phase"
    )

    # Dependencies
    depends_on: Optional[List[str]] = Field(
        None,
        description="List of phase IDs this phase depends on"
    )

    # Timing
    started_at: Optional[datetime] = Field(None, description="Phase start timestamp")
    completed_at: Optional[datetime] = Field(None, description="Phase completion timestamp")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ExecutionMetadata(BaseModel):
    """
    Standardized execution metadata structure

    Provides consistent metadata structure for cross-engine interoperability.
    Separates concerns into intent, execution, and cloud namespaces.
    """

    # Intent-related metadata
    intent: Optional[Dict[str, str]] = Field(
        None,
        description="Intent-related IDs: {intent_id, intent_instance_id}"
    )

    # Execution-related metadata
    execution: Optional[Dict[str, str]] = Field(
        None,
        description="Execution-related IDs: {playbook_code, playbook_execution_id, skill_id, skill_execution_id}"
    )

    # Cloud-related metadata
    cloud: Optional[Dict[str, str]] = Field(
        None,
        description="Cloud-related IDs: {tenant_id, cloud_workspace_id, job_id}"
    )

    def get_intent_id(self) -> Optional[str]:
        """Get intent ID"""
        return self.intent.get("intent_id") if self.intent else None

    def get_intent_instance_id(self) -> Optional[str]:
        """Get intent instance ID"""
        return self.intent.get("intent_instance_id") if self.intent else None

    def get_playbook_code(self) -> Optional[str]:
        """Get playbook code"""
        return self.execution.get("playbook_code") if self.execution else None

    def get_playbook_execution_id(self) -> Optional[str]:
        """Get playbook execution ID"""
        return self.execution.get("playbook_execution_id") if self.execution else None

    def get_skill_id(self) -> Optional[str]:
        """Get skill ID"""
        return self.execution.get("skill_id") if self.execution else None

    def get_skill_execution_id(self) -> Optional[str]:
        """Get skill execution ID"""
        return self.execution.get("skill_execution_id") if self.execution else None

    def get_tenant_id(self) -> Optional[str]:
        """Get tenant ID"""
        return self.cloud.get("tenant_id") if self.cloud else None

    def get_cloud_workspace_id(self) -> Optional[str]:
        """Get cloud workspace ID"""
        return self.cloud.get("cloud_workspace_id") if self.cloud else None

    def get_job_id(self) -> Optional[str]:
        """Get job ID"""
        return self.cloud.get("job_id") if self.cloud else None


class TaskIR(BaseModel):
    """
    Task Intermediate Representation

    The unified representation of a task across all execution engines.
    This is the "EDL/XML" that enables interoperability between different tools.

    Task IR maintains the complete state of a task, allowing any engine to:
    - Understand what the task is about (intent)
    - Know what's been done so far (phases, artifacts)
    - Know what needs to be done next (current_phase, dependencies)
    - Pick up where another engine left off (checkpoint/resume)
    """

    # Identification
    task_id: str = Field(..., description="Unique task identifier")
    intent_instance_id: str = Field(..., description="Associated intent instance ID")
    workspace_id: str = Field(..., description="Workspace ID")
    actor_id: str = Field(..., description="Actor who initiated the task")

    # Current state
    current_phase: Optional[str] = Field(None, description="ID of currently executing phase")
    status: str = Field(default=TaskStatus.PENDING, description="Overall task status")

    # Execution structure
    phases: List[PhaseIR] = Field(default_factory=list, description="All phases in this task")

    # Artifacts
    artifacts: List[ArtifactReference] = Field(
        default_factory=list,
        description="All artifacts produced during task execution"
    )

    # Metadata (standardized structure)
    metadata: ExecutionMetadata = Field(
        default_factory=ExecutionMetadata,
        description="Standardized execution metadata"
    )

    # Timing
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Task creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")
    last_checkpoint_at: Optional[datetime] = Field(None, description="Last checkpoint timestamp")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

    def get_phase(self, phase_id: str) -> Optional[PhaseIR]:
        """Get a phase by ID"""
        return next((p for p in self.phases if p.id == phase_id), None)

    def get_artifact(self, artifact_id: str) -> Optional[ArtifactReference]:
        """Get an artifact by ID"""
        return next((a for a in self.artifacts if a.id == artifact_id), None)

    def add_artifact(self, artifact: ArtifactReference) -> None:
        """Add an artifact to the task"""
        self.artifacts.append(artifact)
        self.updated_at = _utc_now()

    def update_phase_status(self, phase_id: str, status: str, **kwargs) -> bool:
        """Update phase status and optional fields"""
        phase = self.get_phase(phase_id)
        if not phase:
            return False

        phase.status = status
        for key, value in kwargs.items():
            if hasattr(phase, key):
                setattr(phase, key, value)

        self.updated_at = _utc_now()
        return True

    def get_completed_phases(self) -> List[PhaseIR]:
        """Get all completed phases"""
        return [p for p in self.phases if p.status == PhaseStatus.COMPLETED]

    def get_pending_phases(self) -> List[PhaseIR]:
        """Get all pending phases"""
        return [p for p in self.phases if p.status == PhaseStatus.PENDING]

    def can_start_phase(self, phase_id: str) -> bool:
        """Check if a phase can be started (all dependencies completed)"""
        phase = self.get_phase(phase_id)
        if not phase or not phase.depends_on:
            return True

        completed_phase_ids = {p.id for p in self.get_completed_phases()}
        return all(dep_id in completed_phase_ids for dep_id in phase.depends_on)

    def get_next_executable_phases(self) -> List[PhaseIR]:
        """Get phases that can be executed next"""
        return [p for p in self.phases if self.can_start_phase(p.id) and p.status == PhaseStatus.PENDING]


class TaskIRUpdate(BaseModel):
    """
    Update operations for Task IR

    Used to communicate changes between different components
    without passing the entire Task IR object.
    """

    phase_updates: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Phase updates: {phase_id: {field: value, ...}}"
    )
    new_artifacts: List[ArtifactReference] = Field(
        default_factory=list,
        description="New artifacts to add"
    )
    status_update: Optional[str] = Field(None, description="New task status")
    current_phase_update: Optional[str] = Field(None, description="New current phase")

    def is_empty(self) -> bool:
        """Check if this update contains any changes"""
        return not any([
            self.phase_updates,
            self.new_artifacts,
            self.status_update,
            self.current_phase_update
        ])


class HandoffEvent(BaseModel):
    """
    Event representing a handoff between execution engines

    This is the "cut point" in our video editing analogy -
    where one tool hands off work to another tool.
    """

    event_type: str = Field(..., description="Event type: handoff.to_playbook, handoff.to_skill, etc.")

    # Timing
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Event timestamp")

    # Source information
    from_engine: str = Field(..., description="Source engine (e.g., 'playbook:yoga_course_outline')")
    from_execution_id: str = Field(..., description="Source execution ID")
    from_phase_id: str = Field(..., description="Source phase ID")

    # Target information
    to_engine: str = Field(..., description="Target engine (e.g., 'skill:policy_research')")
    to_execution_id: Optional[str] = Field(None, description="Target execution ID (if known)")

    # Context for handoff
    task_ir: TaskIR = Field(..., description="Complete Task IR snapshot")
    input_artifacts: List[str] = Field(
        default_factory=list,
        description="Artifact IDs to pass as input"
    )
    input_summary: Optional[str] = Field(None, description="Text summary for context")

    # Metadata
    workspace_id: str = Field(..., description="Workspace ID")
    metadata: ExecutionMetadata = Field(
        default_factory=ExecutionMetadata,
        description="Execution metadata"
    )

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
