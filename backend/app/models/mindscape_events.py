"""Event models for the Mindscape timeline."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EventType(str, Enum):
    """Event type enumeration for mindspace timeline"""

    MESSAGE = "message"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    PLAYBOOK_STEP = "playbook_step"
    INSIGHT = "insight"
    HABIT_OBSERVATION = "habit_observation"
    PROJECT_CREATED = "project_created"
    PROJECT_UPDATED = "project_updated"
    INTENT_CREATED = "intent_created"
    INTENT_UPDATED = "intent_updated"
    AGENT_EXECUTION = "agent_execution"
    EXECUTION_CHAT = "execution_chat"
    OBSIDIAN_NOTE_UPDATED = "obsidian_note_updated"
    EXECUTION_PLAN = "execution_plan"
    PHASE_SUMMARY = "phase_summary"
    PIPELINE_STAGE = "pipeline_stage"
    DECISION_REQUIRED = "decision_required"
    BRANCH_PROPOSED = "branch_proposed"
    ARTIFACT_CREATED = "artifact_created"
    POLICY_CHECK = "policy_check"
    LOOP_BUDGET_EXHAUSTED = "loop_budget_exhausted"
    QUALITY_GATE_CHECK = "quality_gate_check"
    ARTIFACT_UPDATED = "artifact_updated"
    RUN_STATE_CHANGED = "run_state_changed"
    AGENT_TURN = "agent_turn"
    DECISION_PROPOSAL = "decision_proposal"
    DECISION_FINAL = "decision_final"
    ACTION_ITEM = "action_item"
    MEETING_ROUND = "meeting_round"
    MEETING_START = "meeting_start"
    MEETING_END = "meeting_end"
    MEMORY_WRITEBACK = "memory_writeback"
    DECISION_MADE = "decision_made"
    REASONING_COMMITTED = "reasoning_committed"
    INTENT_PATCHED = "intent_patched"
    STATE_VECTOR_COMPUTED = "state_vector_computed"
    MODE_TRANSITION = "mode_transition"
    CAPABILITY_EVENT = "capability_event"


class EventActor(str, Enum):
    """Event actor enumeration"""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    AGENT = "agent"
    PERSONA = "persona"


class MindEvent(BaseModel):
    """
    Governance state transition log

    All events that happen in the mindspace are recorded here,
    serving as the auditable state transition log for:
    - Intent governance (decision tracking, reasoning audit)
    - Meeting session replay and state diffs
    - Annual book generation
    - Project proposal compilation
    - Habit learning analysis
    """

    id: str = Field(..., description="Unique event identifier")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Event timestamp"
    )
    actor: EventActor = Field(..., description="Who/what triggered this event")
    channel: str = Field(..., description="Channel: local_chat|line|wp|playbook|api")
    profile_id: str = Field(..., description="Associated profile ID")
    project_id: Optional[str] = Field(
        None, description="Associated project ID (if applicable)"
    )
    workspace_id: Optional[str] = Field(
        None, description="Associated workspace ID (if applicable)"
    )
    thread_id: Optional[str] = Field(
        None, description="Associated conversation thread ID (if applicable)"
    )
    event_type: EventType = Field(..., description="Type of event")
    payload: Dict[str, Any] = Field(
        default_factory=dict, description="Event-specific data (varies by event_type)"
    )

    @field_validator("payload", mode="before")
    @classmethod
    def clean_payload(cls, v):
        """Clean payload to ensure it's a dict and doesn't contain sqlite3.Row objects"""
        if v is None:
            return {}

        if hasattr(v, "__class__"):
            class_name = v.__class__.__name__
            module_name = getattr(v.__class__, "__module__", "")
            is_row = (
                class_name == "Row"
                or "sqlite3" in module_name
                or (hasattr(v, "keys") and not hasattr(v, "get"))
            )
            if is_row:
                import logging

                logger = logging.getLogger("app.models.mindscape")
                logger.error(
                    f"clean_payload received sqlite3.Row object! Type: {class_name}, Module: {module_name}"
                )
                return {}

        if isinstance(v, dict):
            cleaned = {}
            for key, value in v.items():
                if hasattr(value, "__class__"):
                    value_class = value.__class__.__name__
                    value_module = getattr(value.__class__, "__module__", "")
                    is_row_value = (
                        value_class == "Row"
                        or "sqlite3" in value_module
                        or (hasattr(value, "keys") and not hasattr(value, "get"))
                    )
                    if is_row_value:
                        import logging

                        logger = logging.getLogger("app.models.mindscape")
                        logger.error(
                            f"clean_payload found sqlite3.Row value in dict! Key: {key}, Type: {value_class}"
                        )
                        continue
                cleaned[key] = value
            return cleaned
        return {}

    entity_ids: List[str] = Field(
        default_factory=list,
        description="Associated entity IDs (Person/Project/Artifact/Theme)",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata (source, trace_id, etc.)"
    )

    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})
