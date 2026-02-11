"""
Workspace enums — all enum types for the workspace domain.
"""

from enum import Enum


# ==================== Execution Enums ====================


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


# ==================== Workspace Enums ====================


class WorkspaceType(str, Enum):
    """
    Workspace type for different vertical domains

    This is a generic field that supports multiple vertical domains:
    - personal: Personal workspace (default)
    - brand: Brand Mindscape workspace
    - team: Team collaboration workspace
    - course: Course creation workspace (future)
    - research: Research workspace (future)
    """

    PERSONAL = "personal"
    BRAND = "brand"
    TEAM = "team"


class LaunchStatus(str, Enum):
    """
    Workspace launch status

    Determines workspace lifecycle state:
    - pending: Only title/description, nothing assembled
    - ready: Blueprint + intents + first_playbook written
    - active: At least one execution / recent work point
    """

    PENDING = "pending"
    READY = "ready"
    ACTIVE = "active"


# ==================== Content Enums ====================


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


# ==================== Feedback / Preference Enums ====================


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


class TaskPreferenceAction(str, Enum):
    """Task preference action type"""

    ENABLE = "enable"
    DISABLE = "disable"
    AUTO_SUGGEST = "auto_suggest"
    MANUAL_ONLY = "manual_only"
