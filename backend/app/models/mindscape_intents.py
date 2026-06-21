"""Intent, agent execution, and request models for Mindscape."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class IntentStatus(str, Enum):
    """Intent status enumeration"""

    ACTIVE = "active"
    COMPLETED = "completed"
    PAUSED = "paused"
    ARCHIVED = "archived"


class PriorityLevel(str, Enum):
    """Priority levels for intents"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IntentCard(BaseModel):
    """Intent card for tracking user goals and tasks"""

    id: str = Field(..., description="Unique intent identifier")
    profile_id: str = Field(..., description="Associated profile ID")
    project_id: Optional[str] = Field(
        None,
        description="Associated project ID for project-scoped intent queries",
    )
    title: str = Field(..., description="Intent title")
    description: str = Field(..., description="Detailed description")
    status: IntentStatus = Field(default=IntentStatus.ACTIVE)
    priority: PriorityLevel = Field(default=PriorityLevel.MEDIUM)
    tags: List[str] = Field(default_factory=list, description="Tags for categorization")
    storyline_tags: List[str] = Field(
        default_factory=list,
        description="Storyline tags for cross-project story tracking (e.g., brand storylines, learning paths, research themes)",
    )
    category: Optional[str] = None
    progress_percentage: int = Field(
        default=0, ge=0, le=100, description="Completion percentage (0-100)"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    due_date: Optional[datetime] = None
    parent_intent_id: Optional[str] = None
    child_intent_ids: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional intent-specific data"
    )

    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})


class IntentCluster(BaseModel):
    """Semantic cluster for related intent cards."""

    id: str = Field(..., description="Unique cluster identifier")
    label: str = Field(..., description="Human-readable cluster label")
    embedding: Optional[List[float]] = Field(
        default=None,
        description="Representative embedding for the cluster",
    )
    workspace_id: str = Field(..., description="Associated workspace ID")
    profile_id: str = Field(..., description="Associated profile ID")
    intent_card_ids: List[str] = Field(
        default_factory=list,
        description="Intent cards belonging to this cluster",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional cluster metadata",
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})


class AgentExecution(BaseModel):
    """Record of agent execution"""

    id: str
    profile_id: str
    agent_type: str
    task: str
    intent_ids: List[str] = Field(default_factory=list)
    status: str = "pending"
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    output: Optional[str] = None
    error_message: Optional[str] = None
    used_profile: Optional[Dict[str, Any]] = None
    used_intents: Optional[List[Dict[str, Any]]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})


class CreateIntentRequest(BaseModel):
    """Request to create a new intent"""

    title: str
    description: str
    priority: PriorityLevel = PriorityLevel.MEDIUM
    tags: List[str] = Field(default_factory=list)
    storyline_tags: List[str] = Field(
        default_factory=list,
        description="Storyline tags for cross-project story tracking",
    )
    category: Optional[str] = None
    due_date: Optional[datetime] = None
    parent_intent_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class UpdateIntentRequest(BaseModel):
    """Request to update an existing intent"""

    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[IntentStatus] = None
    priority: Optional[PriorityLevel] = None
    tags: Optional[List[str]] = None
    storyline_tags: Optional[List[str]] = Field(
        None, description="Storyline tags for cross-project story tracking"
    )
    category: Optional[str] = None
    progress_percentage: Optional[int] = None
    due_date: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None


class RunAgentRequest(BaseModel):
    """Request to run an agent"""

    task: str = Field(..., description="Task description")
    agent_type: str = Field(
        ..., description="Agent type: planner, writer, coach, coder"
    )
    intent_ids: List[str] = Field(
        default_factory=list, description="Related intent IDs"
    )
    use_mindscape: bool = Field(
        default=True, description="Whether to use mindscape context"
    )


class AgentResponse(BaseModel):
    """Response from agent execution"""

    execution_id: str
    status: str
    output: Optional[str] = None
    error_message: Optional[str] = None
    used_profile: Optional[Dict[str, Any]] = None
    used_intents: Optional[List[Dict[str, Any]]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
