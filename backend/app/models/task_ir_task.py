"""Task, update, and handoff models for the Task IR public facade."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from backend.app.models.task_ir_base import (
    ArtifactReference,
    CheckpointSnapshot,
    ExecutionMetadata,
    PhaseIR,
    PhaseStatus,
    TaskStatus,
    _utc_now,
)


class TaskIR(BaseModel):
    """Unified representation of a task across execution engines."""

    task_id: str = Field(..., description="Unique task identifier")
    intent_instance_id: str = Field(..., description="Associated intent instance ID")
    workspace_id: str = Field(..., description="Workspace ID")
    actor_id: str = Field(..., description="Actor who initiated the task")

    current_phase: Optional[str] = Field(
        None, description="ID of currently executing phase"
    )
    status: str = Field(default=TaskStatus.PENDING, description="Overall task status")

    phases: List[PhaseIR] = Field(
        default_factory=list, description="All phases in this task"
    )
    artifacts: List[ArtifactReference] = Field(
        default_factory=list, description="All artifacts produced during task execution"
    )
    metadata: ExecutionMetadata = Field(
        default_factory=ExecutionMetadata, description="Standardized execution metadata"
    )

    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="Task creation timestamp"
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow, description="Last update timestamp"
    )
    last_checkpoint_at: Optional[datetime] = Field(
        None, description="Last checkpoint timestamp"
    )

    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})

    def get_phase(self, phase_id: str) -> Optional[PhaseIR]:
        """Get a phase by ID."""
        return next((p for p in self.phases if p.id == phase_id), None)

    def get_artifact(self, artifact_id: str) -> Optional[ArtifactReference]:
        """Get an artifact by ID."""
        return next((a for a in self.artifacts if a.id == artifact_id), None)

    def add_artifact(self, artifact: ArtifactReference) -> None:
        """Add an artifact to the task."""
        self.artifacts.append(artifact)
        self.updated_at = _utc_now()

    def update_phase_status(self, phase_id: str, status: str, **kwargs) -> bool:
        """Update phase status and optional fields."""
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
        """Get all completed phases."""
        return [p for p in self.phases if p.status == PhaseStatus.COMPLETED]

    def get_pending_phases(self) -> List[PhaseIR]:
        """Get all pending phases."""
        return [p for p in self.phases if p.status == PhaseStatus.PENDING]

    def can_start_phase(self, phase_id: str) -> bool:
        """Check if a phase can be started after dependencies are complete."""
        phase = self.get_phase(phase_id)
        if not phase or not phase.depends_on:
            return True

        completed_phase_ids = {p.id for p in self.get_completed_phases()}
        return all(dep_id in completed_phase_ids for dep_id in phase.depends_on)

    def get_next_executable_phases(self) -> List[PhaseIR]:
        """Get phases that can be executed next."""
        return [
            p
            for p in self.phases
            if self.can_start_phase(p.id) and p.status == PhaseStatus.PENDING
        ]

    def lower_to_actuation_plan(
        self,
        default_engine: str = "playbook:generic",
        default_gate: Optional[str] = None,
    ) -> "TaskIR":
        """Lower pending phases into a dispatchable actuation plan."""
        for phase in self.phases:
            if phase.status != PhaseStatus.PENDING:
                continue
            if not phase.preferred_engine:
                phase.preferred_engine = default_engine
            if not phase.gate and default_gate:
                phase.gate = default_gate
            if not phase.checkpoint_label:
                phase.checkpoint_label = f"pre_{phase.id}"
        self.updated_at = _utc_now()
        return self

    def create_checkpoint(self, phase_id: str) -> "CheckpointSnapshot":
        """Create a checkpoint snapshot before executing a phase."""
        phase = self.get_phase(phase_id)
        label = (
            phase.checkpoint_label
            if phase and phase.checkpoint_label
            else f"pre_{phase_id}"
        )
        self.last_checkpoint_at = _utc_now()
        self.updated_at = _utc_now()
        return CheckpointSnapshot(
            checkpoint_id=f"ckpt_{phase_id}_{int(self.last_checkpoint_at.timestamp())}",
            label=label,
            task_id=self.task_id,
            phase_id=phase_id,
            snapshot=self.model_dump(),
        )

    @staticmethod
    def rollback_to_checkpoint(checkpoint: "CheckpointSnapshot") -> "TaskIR":
        """Restore TaskIR state from a checkpoint snapshot."""
        restored = TaskIR(**checkpoint.snapshot)
        restored.updated_at = _utc_now()
        return restored


class TaskIRUpdate(BaseModel):
    """Update operations for Task IR."""

    phase_updates: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Phase updates: {phase_id: {field: value, ...}}",
    )
    new_artifacts: List[ArtifactReference] = Field(
        default_factory=list, description="New artifacts to add"
    )
    status_update: Optional[str] = Field(None, description="New task status")
    current_phase_update: Optional[str] = Field(None, description="New current phase")

    def is_empty(self) -> bool:
        """Check if this update contains any changes."""
        return not any(
            [
                self.phase_updates,
                self.new_artifacts,
                self.status_update,
                self.current_phase_update,
            ]
        )


class HandoffEvent(BaseModel):
    """Event representing a handoff between execution engines."""

    event_type: str = Field(
        ..., description="Event type: handoff.to_playbook, handoff.to_skill, etc."
    )

    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Event timestamp"
    )

    from_engine: str = Field(
        ..., description="Source engine (e.g., 'playbook:yoga_course_outline')"
    )
    from_execution_id: str = Field(..., description="Source execution ID")
    from_phase_id: str = Field(..., description="Source phase ID")

    to_engine: str = Field(
        ..., description="Target engine (e.g., 'skill:policy_research')"
    )
    to_execution_id: Optional[str] = Field(
        None, description="Target execution ID (if known)"
    )

    task_ir: TaskIR = Field(..., description="Complete Task IR snapshot")
    input_artifacts: List[str] = Field(
        default_factory=list, description="Artifact IDs to pass as input"
    )
    input_summary: Optional[str] = Field(None, description="Text summary for context")

    workspace_id: str = Field(..., description="Workspace ID")
    metadata: ExecutionMetadata = Field(
        default_factory=ExecutionMetadata, description="Execution metadata"
    )

    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})
