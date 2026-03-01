"""Enum types for playbook models."""

from enum import Enum


class PlaybookKind(str, Enum):
    """Playbook type classification."""

    USER_WORKFLOW = "user_workflow"
    SYSTEM_TOOL = "system_tool"


class InteractionMode(str, Enum):
    """How playbook interacts with users."""

    SILENT = "silent"
    NEEDS_REVIEW = "needs_review"
    CONVERSATIONAL = "conversational"


class VisibleIn(str, Enum):
    """Where playbook should be visible in UI."""

    WORKSPACE_PLAYBOOK_MENU = "workspace_playbook_menu"
    WORKSPACE_TOOLS_PANEL = "workspace_tools_panel"
    CONSOLE_ONLY = "console_only"


class PlaybookOwnerType(str, Enum):
    """
    Playbook ownership type.

    Determines who owns and controls this playbook.
    """

    SYSTEM = "system"
    TENANT = "tenant"
    WORKSPACE = "workspace"
    USER = "user"
    EXTERNAL_PROVIDER = "external_provider"


class PlaybookVisibility(str, Enum):
    """Playbook visibility / sharing level."""

    PRIVATE = "private"
    WORKSPACE_SHARED = "workspace_shared"
    TENANT_SHARED = "tenant_shared"
    PUBLIC_TEMPLATE = "public_template"


class ErrorHandlingStrategy(str, Enum):
    """Error handling strategy for workflow steps."""

    STOP_WORKFLOW = "stop_workflow"
    CONTINUE_ON_ERROR = "continue_on_error"
    SKIP_STEP = "skip_step"
    RETRY_THEN_STOP = "retry_then_stop"
    RETRY_THEN_CONTINUE = "retry_then_continue"


class InvocationMode(str, Enum):
    """Playbook invocation mode."""

    STANDALONE = "standalone"
    PLAN_NODE = "plan_node"
    SUBROUTINE = "subroutine"


class InvocationTolerance(str, Enum):
    """Tolerance level for data insufficiency."""

    STRICT = "strict"
    LENIENT = "lenient"
    ADAPTIVE = "adaptive"

