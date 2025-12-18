"""
Data models for My Agent Console Mindscape
Defines the core data structures for user profiles and intent management
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field, field_validator


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


class CommunicationStyle(str, Enum):
    """User communication style preferences"""
    FORMAL = "formal"
    CASUAL = "casual"
    TECHNICAL = "technical"
    CONCISE = "concise"
    DETAILED = "detailed"


class ResponseLength(str, Enum):
    """Preferred response length"""
    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"


class ReviewPreferences(BaseModel):
    """Annual review preference settings"""
    cadence: str = Field(default="manual", description="Review cadence: 'manual' | 'weekly' | 'monthly'")
    day_of_week: int = Field(default=6, ge=0, le=6, description="Day of week reminder (0=Mon ... 6=Sun, if weekly)")
    day_of_month: int = Field(default=28, ge=1, le=31, description="Day of month reminder (if monthly)")
    time_of_day: str = Field(default="21:00", description="Reminder time (e.g., '21:00' local time)")
    min_entries: int = Field(default=10, ge=0, description="Minimum accumulated entries before reminder")
    min_insight_events: int = Field(default=3, ge=0, description="Minimum 'has_insight_signal = True' events before reminder")


class UserPreferences(BaseModel):
    """User preference settings"""
    communication_style: CommunicationStyle = CommunicationStyle.CASUAL
    response_length: ResponseLength = ResponseLength.MEDIUM
    language: str = "en"  # Legacy field, use preferred_ui_language instead
    preferred_ui_language: str = Field(
        default="zh-TW",
        description="Preferred UI language (e.g., 'zh-TW', 'en')"
    )
    preferred_content_language: str = Field(
        default="zh-TW",
        description="Preferred content language for writing/working (e.g., 'zh-TW', 'en')"
    )
    secondary_languages: List[str] = Field(
        default_factory=list,
        description="Secondary languages the user can work with"
    )
    timezone: str = "UTC"
    enable_notifications: bool = True
    auto_save: bool = True
    theme: str = "light"
    enable_habit_suggestions: bool = Field(
        default=False,
        description="Enable habit learning and suggestions (default: False for privacy)"
    )
    review_preferences: ReviewPreferences = Field(
        default_factory=ReviewPreferences,
        description="Annual review preference settings"
    )


class MindscapeProfile(BaseModel):
    """User mindscape profile"""
    id: str = Field(..., description="Unique profile identifier")
    name: str = Field(..., description="Display name")
    email: Optional[str] = None

    # Identity and roles
    roles: List[str] = Field(default_factory=list,
                           description="User roles (e.g., developer, writer, entrepreneur)")
    domains: List[str] = Field(default_factory=list,
                             description="Expertise domains (e.g., tech, business, health)")

    # Onboarding and self-description
    onboarding_state: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Onboarding task completion state"
    )
    self_description: Optional[Dict[str, Any]] = Field(
        default=None,
        description="User's self-description from onboarding (identity, solving, thinking)"
    )

    # Preferences
    preferences: UserPreferences = Field(default_factory=UserPreferences,
                                       description="User preferences")

    # External references (for external integration)
    external_ref: Optional[Dict[str, Any]] = Field(
        default=None,
        description="External references (e.g., tenant_uuid, site_uuid) - optional, used by external extensions"
    )

    # Tags for categorization and template export
    tags: List[str] = Field(
        default_factory=list,
        description="Tags for profile categorization (e.g., 'wordpress-site-owner', 'agency')"
    )

    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    version: int = Field(default=1, description="Profile version for optimistic locking")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class IntentCard(BaseModel):
    """Intent card for tracking user goals and tasks"""
    id: str = Field(..., description="Unique intent identifier")
    profile_id: str = Field(..., description="Associated profile ID")

    # Basic info
    title: str = Field(..., description="Intent title")
    description: str = Field(..., description="Detailed description")

    # Status and priority
    status: IntentStatus = Field(default=IntentStatus.ACTIVE)
    priority: PriorityLevel = Field(default=PriorityLevel.MEDIUM)

    # Categorization
    tags: List[str] = Field(default_factory=list, description="Tags for categorization")
    storyline_tags: List[str] = Field(
        default_factory=list,
        description="Storyline tags for cross-project story tracking (e.g., brand storylines, learning paths, research themes)"
    )
    category: Optional[str] = None

    # Progress tracking
    progress_percentage: int = Field(default=0, ge=0, le=100,
                                   description="Completion percentage (0-100)")

    # Time tracking
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    due_date: Optional[datetime] = None

    # Relationships
    parent_intent_id: Optional[str] = None
    child_intent_ids: List[str] = Field(default_factory=list)

    # Additional metadata
    metadata: Dict[str, Any] = Field(default_factory=dict,
                                   description="Additional intent-specific data")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class AgentExecution(BaseModel):
    """Record of agent execution"""
    id: str
    profile_id: str
    agent_type: str  # "planner", "writer", "coach", "coder"
    task: str
    intent_ids: List[str] = Field(default_factory=list)

    # Execution details
    status: str = "pending"  # pending, running, completed, failed
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None

    # Results
    output: Optional[str] = None
    error_message: Optional[str] = None

    # Context
    used_profile: Optional[Dict[str, Any]] = None
    used_intents: Optional[List[Dict[str, Any]]] = None

    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


# API Request/Response models

class CreateProfileRequest(BaseModel):
    """Request to create a new profile"""
    name: str
    email: Optional[str] = None
    roles: List[str] = Field(default_factory=list)
    domains: List[str] = Field(default_factory=list)
    preferences: Optional[UserPreferences] = None


class UpdateProfileRequest(BaseModel):
    """Request to update an existing profile"""
    name: Optional[str] = None
    email: Optional[str] = None
    roles: Optional[List[str]] = None
    domains: Optional[List[str]] = None
    preferences: Optional[UserPreferences] = None


class CreateIntentRequest(BaseModel):
    """Request to create a new intent"""
    title: str
    description: str
    priority: PriorityLevel = PriorityLevel.MEDIUM
    tags: List[str] = Field(default_factory=list)
    storyline_tags: List[str] = Field(default_factory=list, description="Storyline tags for cross-project story tracking")
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
    storyline_tags: Optional[List[str]] = Field(None, description="Storyline tags for cross-project story tracking")
    category: Optional[str] = None
    progress_percentage: Optional[int] = None
    due_date: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None


class RunAgentRequest(BaseModel):
    """Request to run an agent"""
    task: str = Field(..., description="Task description")
    agent_type: str = Field(..., description="Agent type: planner, writer, coach, coder")
    intent_ids: List[str] = Field(default_factory=list,
                                description="Related intent IDs")
    use_mindscape: bool = Field(default=True,
                              description="Whether to use mindscape context")


class AgentResponse(BaseModel):
    """Response from agent execution"""
    execution_id: str
    status: str
    output: Optional[str] = None
    error_message: Optional[str] = None
    used_profile: Optional[Dict[str, Any]] = None
    used_intents: Optional[List[Dict[str, Any]]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ==================== Event-based Mindspace Timeline ====================

class EventType(str, Enum):
    """Event type enumeration for mindspace timeline"""
    MESSAGE = "message"                    # User/assistant messages
    TOOL_CALL = "tool_call"                # Tool/function calls
    TOOL_RESULT = "tool_result"            # Tool execution results (ReAct: Observe)
    PLAYBOOK_STEP = "playbook_step"        # Playbook execution steps
    INSIGHT = "insight"                   # Generated insights or observations
    HABIT_OBSERVATION = "habit_observation" # Habit learning observations
    PROJECT_CREATED = "project_created"   # Project creation events
    PROJECT_UPDATED = "project_updated"     # Project update events
    INTENT_CREATED = "intent_created"      # Intent creation events
    INTENT_UPDATED = "intent_updated"      # Intent update events
    AGENT_EXECUTION = "agent_execution"    # Agent execution events
    EXECUTION_CHAT = "execution_chat"      # Execution-scoped chat messages
    OBSIDIAN_NOTE_UPDATED = "obsidian_note_updated"  # Obsidian note creation/update events
    EXECUTION_PLAN = "execution_plan"      # Chain-of-Thought execution plan
    PHASE_SUMMARY = "phase_summary"        # Playbook phase summary for external memory
    # Unified Decision & ReAct Loop Events
    DECISION_REQUIRED = "decision_required"  # Human-in-the-loop: requires user decision (ReAct: Ask Human)
    BRANCH_PROPOSED = "branch_proposed"      # Tree of Thoughts: alternative branches proposed
    ARTIFACT_CREATED = "artifact_created"    # Artifact created/updated
    ARTIFACT_UPDATED = "artifact_updated"    # Artifact updated
    RUN_STATE_CHANGED = "run_state_changed"  # Execution state changed (WAITING_HUMAN / READY / RUNNING / DONE)


class EventActor(str, Enum):
    """Event actor enumeration"""
    USER = "user"                          # User actions
    ASSISTANT = "assistant"                # AI assistant actions
    SYSTEM = "system"                      # System events


class MindEvent(BaseModel):
    """
    Mindspace event for timeline reconstruction

    All events that happen in the mindspace are recorded here,
    allowing replay and recombination for features like:
    - Annual book generation
    - Project proposal compilation
    - Habit learning analysis
    """
    id: str = Field(..., description="Unique event identifier")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Event timestamp")

    # Actor and channel
    actor: EventActor = Field(..., description="Who/what triggered this event")
    channel: str = Field(..., description="Channel: local_chat|line|wp|playbook|api")

    # Context
    profile_id: str = Field(..., description="Associated profile ID")
    project_id: Optional[str] = Field(None, description="Associated project ID (if applicable)")
    workspace_id: Optional[str] = Field(
        None,
        description="Associated workspace ID (if applicable)"
    )

    # Event classification
    event_type: EventType = Field(..., description="Type of event")

    # Event-specific payload (flexible JSON structure)
    payload: Dict[str, Any] = Field(
        default_factory=dict,
        description="Event-specific data (varies by event_type)"
    )

    @field_validator('payload', mode='before')
    @classmethod
    def clean_payload(cls, v):
        """Clean payload to ensure it's a dict and doesn't contain sqlite3.Row objects"""
        if v is None:
            return {}

        # Check if v itself is a sqlite3.Row object
        if hasattr(v, '__class__'):
            class_name = v.__class__.__name__
            module_name = getattr(v.__class__, '__module__', '')
            # Check if it's sqlite3.Row by checking for keys() but not get()
            is_row = (
                class_name == 'Row' or
                'sqlite3' in module_name or
                (hasattr(v, 'keys') and not hasattr(v, 'get'))
            )
            if is_row:
                # This is a sqlite3.Row object, return empty dict
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"clean_payload received sqlite3.Row object! Type: {class_name}, Module: {module_name}")
                return {}

        # If it's already a dict, check for sqlite3.Row values
        if isinstance(v, dict):
            cleaned = {}
            for key, value in v.items():
                # Check if value is sqlite3.Row
                if hasattr(value, '__class__'):
                    value_class = value.__class__.__name__
                    value_module = getattr(value.__class__, '__module__', '')
                    is_row_value = (
                        value_class == 'Row' or
                        'sqlite3' in value_module or
                        (hasattr(value, 'keys') and not hasattr(value, 'get'))
                    )
                    if is_row_value:
                        # Skip sqlite3.Row values
                        import logging
                        logger = logging.getLogger(__name__)
                        logger.error(f"clean_payload found sqlite3.Row value in dict! Key: {key}, Type: {value_class}")
                        continue
                cleaned[key] = value
            return cleaned
        # If it's not a dict, return empty dict
        return {}

    # Entity associations (for A.2: core entities and tags)
    entity_ids: List[str] = Field(
        default_factory=list,
        description="Associated entity IDs (Person/Project/Artifact/Theme)"
    )

    # Metadata
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata (source, trace_id, etc.)"
    )

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


# ==================== Core Entities and Tags System ====================

class EntityType(str, Enum):
    """Entity type enumeration"""
    PERSON = "person"              # People (users, contacts, collaborators)
    PROJECT = "project"             # Projects (work items, goals, initiatives)
    ARTIFACT = "artifact"          # Artifacts (documents, files, outputs)
    THEME = "theme"                # Themes (topics, categories, concepts)


class TagCategory(str, Enum):
    """Tag category enumeration"""
    THEME = "theme"                # Topic themes (e.g., "AI", "entrepreneurship", "product design")
    PHASE = "phase"                # Project phases (e.g., "planning", "execution", "review")
    MOOD = "mood"                  # Emotional states (e.g., "excited", "stressed", "focused")
    PRIORITY = "priority"          # Priority levels (e.g., "urgent", "important", "nice-to-have")
    RISK = "risk"                  # Risk indicators (e.g., "high-risk", "blocked", "uncertain")


class Entity(BaseModel):
    """
    Core entity model for unified abstraction

    Entities represent the core "things" in the mindspace:
    - Person: People involved (users, contacts, collaborators)
    - Project: Work items, goals, initiatives
    - Artifact: Documents, files, outputs
    - Theme: Topics, categories, concepts
    """
    id: str = Field(..., description="Unique entity identifier")
    entity_type: EntityType = Field(..., description="Type of entity")
    name: str = Field(..., description="Entity name")
    profile_id: str = Field(..., description="Associated profile ID")
    description: Optional[str] = Field(None, description="Entity description")
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata (varies by entity_type)"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class Tag(BaseModel):
    """
    Tag model for semantic labeling

    Tags are used to categorize and label entities with semantic meaning.
    Categories help organize tags by their purpose (theme, phase, mood, etc.)
    """
    id: str = Field(..., description="Unique tag identifier")
    name: str = Field(..., description="Tag name")
    category: TagCategory = Field(..., description="Tag category")
    profile_id: str = Field(..., description="Associated profile ID")
    description: Optional[str] = Field(None, description="Tag description")
    color: Optional[str] = Field(None, description="Optional color code for visualization")
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class EntityTag(BaseModel):
    """
    Entity-Tag association model

    Links entities to tags with optional value.
    The value field allows tags to have associated data (e.g., priority level, phase status).
    """
    entity_id: str = Field(..., description="Entity ID")
    tag_id: str = Field(..., description="Tag ID")
    value: Optional[str] = Field(None, description="Optional tag value")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Association timestamp")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


# ==================== Intent Log for Offline Optimization ====================

class IntentSource(str, Enum):
    """Intent source enumeration"""
    LLM = "llm"
    USER = "user"
    SYSTEM = "system"


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

    # Intent information
    label: str = Field(..., description="Intent label (e.g., 'Grant Proposal Draft', 'December Marketing Plan Support')")
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="Confidence score (0-1)")

    # Status and source
    status: IntentTagStatus = Field(default=IntentTagStatus.CANDIDATE, description="Intent tag status")
    source: IntentSource = Field(..., description="Intent source")

    # Execution context reference (optional)
    execution_id: Optional[str] = Field(None, description="Associated execution ID (if from execution)")

    # Related entities
    playbook_code: Optional[str] = Field(None, description="Suggested playbook code")
    message_id: Optional[str] = Field(None, description="Source message/event ID")

    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")
    confirmed_at: Optional[datetime] = Field(None, description="Confirmation timestamp (if confirmed)")
    rejected_at: Optional[datetime] = Field(None, description="Rejection timestamp (if rejected)")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class IntentLog(BaseModel):
    """
    Intent decision log for offline optimization and evaluation

    Records all intent analysis decisions with pipeline steps,
    allowing offline replay and evaluation.
    """
    id: str = Field(..., description="Unique log identifier")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Log timestamp")

    # Input context
    raw_input: str = Field(..., description="Original user input")
    channel: str = Field(..., description="Channel: api|line|wp|playbook")
    profile_id: str = Field(..., description="User profile ID")
    project_id: Optional[str] = Field(None, description="Associated project ID (if applicable)")
    workspace_id: Optional[str] = Field(None, description="Associated workspace ID (if applicable)")

    # Pipeline execution details
    pipeline_steps: Dict[str, Any] = Field(
        default_factory=dict,
        description="All pipeline layer results (layer1_method, layer2_method, etc.)"
    )

    # Final decision
    final_decision: Dict[str, Any] = Field(
        default_factory=dict,
        description="Final intent analysis result (interaction_type, task_domain, playbook_code, etc.)"
    )

    # User override (manual annotation)
    user_override: Optional[Dict[str, Any]] = Field(
        None,
        description="User manual correction (correct_interaction_type, correct_task_domain, correct_playbook_code)"
    )

    # Metadata
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata (model_version, prompt_version, etc.)"
    )

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
