"""Intent-tag, steward, and log models for Mindscape."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from .mindscape_intents import IntentCard


class IntentSource(str, Enum):
    """Intent source enumeration"""

    LLM = "llm"
    USER = "user"
    SYSTEM = "system"
    IDE = "ide"


class IntentTagStatus(str, Enum):
    """IntentTag status enumeration"""

    CANDIDATE = "candidate"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class IntentTag(BaseModel):
    """
    IntentTag model - represents candidate/confirmed intent tags

    IntentTags are used to track LLM-suggested intents (candidate status)
    and user-confirmed intents (confirmed status) for Playbook Runtime execution context.
    Only confirmed intents are written to long-term memory (IntentCard).

    Key characteristics:
    - Candidate intents: LLM-suggested, not yet confirmed by user
    - Confirmed intents: User-confirmed, can be used for execution context
    - Rejected intents: User-rejected, not used for execution
    """

    id: str = Field(..., description="Unique intent tag identifier")
    workspace_id: str = Field(..., description="Associated workspace ID")
    profile_id: str = Field(..., description="Associated profile ID")
    label: str = Field(
        ...,
        description="Intent label (e.g., 'Grant Proposal Draft', 'December Marketing Plan Support')",
    )
    confidence: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Confidence score (0-1)"
    )
    status: IntentTagStatus = Field(
        default=IntentTagStatus.CANDIDATE, description="Intent tag status"
    )
    source: IntentSource = Field(..., description="Intent source")
    execution_id: Optional[str] = Field(
        None, description="Associated execution ID (if from execution)"
    )
    playbook_code: Optional[str] = Field(None, description="Suggested playbook code")
    message_id: Optional[str] = Field(None, description="Source message/event ID")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="Creation timestamp"
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow, description="Last update timestamp"
    )
    confirmed_at: Optional[datetime] = Field(
        None, description="Confirmation timestamp (if confirmed)"
    )
    rejected_at: Optional[datetime] = Field(
        None, description="Rejection timestamp (if rejected)"
    )

    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})


class IntentSignal(BaseModel):
    """
    IntentSignal - represents a candidate intent signal for steward analysis.

    Collected from IntentTags with CANDIDATE status and fed into
    IntentStewardService for filtering and layout plan generation.
    """

    id: str = Field(..., description="Unique signal identifier")
    workspace_id: str = Field(..., description="Associated workspace ID")
    profile_id: str = Field(..., description="Associated profile ID")
    label: str = Field(..., description="Signal label text")
    confidence: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Confidence score"
    )
    status: str = Field(default="candidate", description="Signal status")
    source: str = Field(
        default="llm", description="Signal source (llm, user, system, ide)"
    )
    signal_type: str = Field(default="intent", description="Signal type")
    message_id: Optional[str] = Field(None, description="Source message/event ID")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="Creation timestamp"
    )

    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})


class IntentOperation(BaseModel):
    """
    IntentOperation - a planned create/update operation on an IntentCard.

    Part of IntentLayoutPlan.long_term_intents.
    """

    operation_type: str = Field(
        ..., description="Operation type: CREATE_INTENT_CARD | UPDATE_INTENT_CARD"
    )
    intent_id: Optional[str] = Field(
        None, description="Existing IntentCard ID (required for UPDATE)"
    )
    intent_data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Intent data (title, description, priority, status)",
    )
    relation_signals: List[str] = Field(
        default_factory=list, description="Related signal IDs"
    )
    confidence: float = Field(
        default=0.7, ge=0.0, le=1.0, description="Operation confidence"
    )
    reasoning: str = Field(default="", description="Reasoning for this operation")


class EphemeralTask(BaseModel):
    """
    EphemeralTask - a short-lived task that doesn't warrant an IntentCard.

    Part of IntentLayoutPlan.ephemeral_tasks.
    """

    signal_id: str = Field(..., description="Source signal ID")
    title: str = Field(..., description="Task title")
    description: Optional[str] = Field(None, description="Task description")
    reasoning: str = Field(
        default="", description="Reasoning for ephemeral classification"
    )


class SignalMapping(BaseModel):
    """
    SignalMapping - tracks how a signal was processed.

    Part of IntentLayoutPlan.signal_mapping.
    """

    signal_id: str = Field(..., description="Signal ID")
    action: str = Field(..., description="Action taken: mapped_to_intent_id | ignored")
    target_intent_id: Optional[str] = Field(
        None, description="Target IntentCard ID (if mapped)"
    )
    reasoning: str = Field(default="", description="Reasoning for mapping decision")


class IntentLayoutPlan(BaseModel):
    """
    IntentLayoutPlan - the output of IntentSteward analysis.

    Contains planned IntentCard operations, ephemeral tasks,
    and signal-to-intent mappings.
    """

    long_term_intents: List[IntentOperation] = Field(
        default_factory=list, description="Planned IntentCard create/update operations"
    )
    ephemeral_tasks: List[EphemeralTask] = Field(
        default_factory=list, description="Short-lived tasks"
    )
    signal_mapping: List[SignalMapping] = Field(
        default_factory=list, description="Signal processing mappings"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Analysis metadata"
    )


class IntentStewardInput(BaseModel):
    """
    IntentStewardInput - collected input data for steward analysis.

    Aggregates recent messages, candidate signals, and current IntentCards.
    """

    recent_messages: List[Dict[str, Any]] = Field(
        default_factory=list, description="Recent conversation messages"
    )
    recent_signals: List[IntentSignal] = Field(
        default_factory=list, description="Recent candidate IntentSignals"
    )
    current_intent_cards: List[IntentCard] = Field(
        default_factory=list, description="Currently visible IntentCards"
    )


class IntentLog(BaseModel):
    """
    Intent decision log for offline optimization and evaluation

    Records all intent analysis decisions with pipeline steps,
    allowing offline replay and evaluation.
    """

    id: str = Field(..., description="Unique log identifier")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Log timestamp"
    )
    raw_input: str = Field(..., description="Original user input")
    channel: str = Field(..., description="Channel: api|line|wp|playbook")
    profile_id: str = Field(..., description="User profile ID")
    project_id: Optional[str] = Field(
        None, description="Associated project ID (if applicable)"
    )
    workspace_id: Optional[str] = Field(
        None, description="Associated workspace ID (if applicable)"
    )
    pipeline_steps: Dict[str, Any] = Field(
        default_factory=dict,
        description="All pipeline layer results (layer1_method, layer2_method, etc.)",
    )
    final_decision: Dict[str, Any] = Field(
        default_factory=dict,
        description="Final intent analysis result (interaction_type, task_domain, playbook_code, etc.)",
    )
    user_override: Optional[Dict[str, Any]] = Field(
        None,
        description="User manual correction (correct_interaction_type, correct_task_domain, correct_playbook_code)",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata (model_version, prompt_version, etc.)",
    )

    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})
