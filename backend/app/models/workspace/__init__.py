"""
Workspace models package — split from monolithic workspace.py for maintainability.

All public symbols are re-exported here so that:
    from backend.app.models.workspace import TaskStatus, Workspace, Task, ...
continues to work unchanged.
"""

from .enums import (  # noqa: F401
    SideEffectLevel,
    TaskStatus,
    TimelineItemType,
    ArtifactType,
    PrimaryActionType,
    ExecutionChatMessageType,
    ExecutionMode,
    ExecutionPriority,
    ProjectAssignmentMode,
    WorkspaceType,
    LaunchStatus,
    TaskFeedbackAction,
    TaskFeedbackReasonCode,
    TaskPreferenceAction,
)

from .core import (  # noqa: F401
    Workspace,
    CreateWorkspaceRequest,
    UpdateWorkspaceRequest,
    WorkspaceChatRequest,
    WorkspaceChatResponse,
)

from .task import (  # noqa: F401
    Task,
    TaskFeedback,
    TaskPreference,
)

from .execution import (  # noqa: F401
    ExecutionStep,
    TaskPlan,
    ExecutionPlan,
    ExecutionSession,
    ExecutionChatMessage,
)

from .playbook_execution import (  # noqa: F401
    PlaybookExecution,
    PlaybookExecutionStep,
)

from .timeline import (  # noqa: F401
    TimelineItem,
    ConversationThread,
)

from .artifact import (  # noqa: F401
    Artifact,
    ThreadReference,
    BackgroundRoutine,
)

# Also export the _utc_now helper for backward compat
from ._common import _utc_now  # noqa: F401

__all__ = [
    # Enums
    "SideEffectLevel",
    "TaskStatus",
    "TimelineItemType",
    "ArtifactType",
    "PrimaryActionType",
    "ExecutionChatMessageType",
    "ExecutionMode",
    "ExecutionPriority",
    "ProjectAssignmentMode",
    "WorkspaceType",
    "LaunchStatus",
    "TaskFeedbackAction",
    "TaskFeedbackReasonCode",
    "TaskPreferenceAction",
    # Core
    "Workspace",
    "CreateWorkspaceRequest",
    "UpdateWorkspaceRequest",
    "WorkspaceChatRequest",
    "WorkspaceChatResponse",
    # Task
    "Task",
    "TaskFeedback",
    "TaskPreference",
    # Execution
    "ExecutionStep",
    "TaskPlan",
    "ExecutionPlan",
    "ExecutionSession",
    "ExecutionChatMessage",
    # Playbook Execution
    "PlaybookExecution",
    "PlaybookExecutionStep",
    # Timeline
    "TimelineItem",
    "ConversationThread",
    # Artifact
    "Artifact",
    "ThreadReference",
    "BackgroundRoutine",
    # Utilities
    "_utc_now",
]
