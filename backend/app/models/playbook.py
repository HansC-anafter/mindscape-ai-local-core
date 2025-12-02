"""
Playbook data models
Simplified version for v0 MVP - local Playbook library
"""

from datetime import datetime
from typing import List, Optional, Dict, Any, Literal
from enum import Enum
from pydantic import BaseModel, Field, validator


class PlaybookKind(str, Enum):
    """Playbook type classification"""
    USER_WORKFLOW = "user_workflow"
    SYSTEM_TOOL = "system_tool"


class InteractionMode(str, Enum):
    """How playbook interacts with users"""
    SILENT = "silent"
    NEEDS_REVIEW = "needs_review"
    CONVERSATIONAL = "conversational"


class VisibleIn(str, Enum):
    """Where playbook should be visible in UI"""
    WORKSPACE_PLAYBOOK_MENU = "workspace_playbook_menu"
    WORKSPACE_TOOLS_PANEL = "workspace_tools_panel"
    CONSOLE_ONLY = "console_only"


class ToolDependency(BaseModel):
    """
    Tool dependency declaration

    Supports three tool types:
    1. builtin - Built-in tools (WordPress, Local Files, etc.)
    2. langchain - LangChain tools (Wikipedia, SerpAPI, etc.)
    3. mcp - MCP tools (GitHub, Postgres, etc.)

    Example:
        ToolDependency(
            type="builtin",
            name="wordpress",
            required=True
        )

        ToolDependency(
            type="langchain",
            name="wikipedia",
            source="langchain_community.tools.WikipediaQueryRun",
            required=True
        )

        ToolDependency(
            type="mcp",
            name="github.search_issues",
            source="github",
            config={"env": {"GITHUB_TOKEN": "${GITHUB_TOKEN}"}},
            required=False
        )
    """
    type: Literal["builtin", "langchain", "mcp"] = Field(
        ...,
        description="Tool type: builtin, langchain, or mcp"
    )
    name: str = Field(
        ...,
        description="Tool name or identifier"
    )
    source: Optional[str] = Field(
        None,
        description="Tool source: full class path for LangChain, server ID for MCP"
    )
    config: Dict[str, Any] = Field(
        default_factory=dict,
        description="Tool configuration (API keys, environment variables, etc.), supports ${VAR} syntax"
    )
    required: bool = Field(
        default=True,
        description="Whether the tool is required (execution blocked if missing)"
    )
    fallback: Optional[str] = Field(
        None,
        description="Fallback tool name (when main tool is unavailable)"
    )
    description: Optional[str] = Field(
        None,
        description="Tool purpose description"
    )

    @validator("source")
    def validate_source(cls, v, values):
        """Validate source field"""
        tool_type = values.get("type")

        if tool_type == "langchain" and not v:
            raise ValueError("LangChain tools must provide source (full class path)")

        return v


class PlaybookMetadata(BaseModel):
    """Playbook metadata (simplified for v0)"""
    playbook_code: str = Field(..., description="Unique playbook identifier")
    version: str = Field(default="1.0.0", description="Playbook version")

    locale: str = Field(
        default="zh-TW",
        description="Language locale. Deprecated: use target_language parameter at execution time instead. "
                    "Kept for backward compatibility only."
    )

    name: str = Field(..., description="Playbook name")
    description: str = Field(default="", description="Playbook description")
    tags: List[str] = Field(default_factory=list, description="Tags for categorization")

    language_strategy: str = Field(
        default="model_native",
        description="Language handling strategy: 'model_native' (use LLM's multilingual capabilities), "
                    "'i18n_fallback' (use i18n files for specialized terminology)"
    )

    supports_execution_chat: bool = Field(
        default=False,
        description="Whether this playbook supports execution-scoped chat. "
                    "If true, ExecutionChatPanel will be displayed in ExecutionInspector."
    )

    discussion_agent: Optional[str] = Field(
        default=None,
        description="Agent persona for execution chat (e.g., 'planner', 'coordinator', 'researcher'). "
                    "If not specified, uses default system assistant persona."
    )

    supported_locales: List[str] = Field(
        default_factory=lambda: ["zh-TW", "en"],
        description="Officially tested locales. Not required for execution. "
                    "Playbooks are language-neutral and support any language via target_language parameter."
    )
    default_locale: str = Field(
        default="en",
        description="Default locale when user's locale is not in supported_locales. "
                    "Use target_language parameter at execution time instead."
    )
    auto_localize: bool = Field(
        default=True,
        description="Allow LLM-assisted localization for unsupported locales. "
                    "Default behavior with language_strategy='model_native'."
    )

    # AI Role association (for console-kit export)
    entry_agent_type: Optional[str] = Field(
        default=None,
        description="Corresponding AI role: planner, writer, coach, coder"
    )

    # Onboarding
    onboarding_task: Optional[str] = Field(
        default=None,
        description="Onboarding task identifier (e.g., task2, task3)"
    )
    icon: Optional[str] = Field(
        default=None,
        description="Emoji icon for the playbook"
    )

    required_tools: List[str] = Field(
        default_factory=list,
        description="Simple tool list (legacy format, backward compatible)"
    )

    tool_dependencies: List[ToolDependency] = Field(
        default_factory=list,
        description="Detailed tool dependency declarations (supports LangChain/MCP)"
    )

    # Background routine configuration
    background: bool = Field(
        default=False,
        description="Whether this playbook is a background routine (runs on schedule)"
    )

    optional_tools: List[str] = Field(
        default_factory=list,
        description="Optional tools (playbook can degrade gracefully if missing)"
    )

    # Playbook classification (for workflow orchestration)
    kind: PlaybookKind = Field(
        default=PlaybookKind.USER_WORKFLOW,
        description="Playbook type: user_workflow (for users) or system_tool (for system operations)"
    )

    interaction_mode: List[InteractionMode] = Field(
        default_factory=lambda: [InteractionMode.CONVERSATIONAL],
        description="How this playbook interacts with users: silent, needs_review, or conversational"
    )

    visible_in: List[VisibleIn] = Field(
        default_factory=lambda: [VisibleIn.WORKSPACE_PLAYBOOK_MENU],
        description="Where this playbook should be visible in UI"
    )

    # Scope and Owner
    scope: Optional[Dict[str, Any]] = Field(
        default_factory=lambda: {"visibility": "system", "editable": False},
        description="Scope configuration (visibility, editable)"
    )
    owner: Optional[Dict[str, Any]] = Field(
        default_factory=lambda: {"type": "system"},
        description="Owner information"
    )

    # Runtime configuration
    runtime_handler: str = Field(
        default="local_llm",
        description="Runtime handler: local_llm, remote_crs, custom"
    )

    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Playbook(BaseModel):
    """Complete Playbook definition"""
    metadata: PlaybookMetadata
    sop_content: str = Field(default="", description="SOP content in Markdown")

    # Optional: user notes for personalization
    user_notes: Optional[str] = Field(None, description="User's personal notes about this playbook")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class PlaybookRun(BaseModel):
    """
    playbook.run = playbook.md + playbook.json

    Complete playbook definition with both human-readable description
    and machine-readable execution spec.
    """
    playbook: Playbook = Field(..., description="Playbook.md definition (human-readable)")
    playbook_json: Optional["PlaybookJson"] = Field(None, description="Playbook.json definition (machine-readable)")

    def has_json(self) -> bool:
        """Check if playbook.json exists"""
        return self.playbook_json is not None

    def get_execution_mode(self) -> str:
        """
        Determine execution mode based on available components

        Returns:
            'workflow' if playbook.json exists, 'conversation' otherwise
        """
        if self.has_json():
            return 'workflow'
        return 'conversation'

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class CreatePlaybookRequest(BaseModel):
    """Request to create a new playbook"""
    playbook_code: str
    name: str
    description: str = ""
    tags: List[str] = Field(default_factory=list)
    sop_content: str = ""
    owner: Optional[Dict[str, Any]] = None


class UpdatePlaybookRequest(BaseModel):
    """Request to update a playbook"""
    name: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    sop_content: Optional[str] = None
    user_notes: Optional[str] = None


class PlaybookAssociation(BaseModel):
    """Association between IntentCard and Playbook"""
    intent_id: str
    playbook_code: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


# ============================================================================
# playbook.json Schema Models
# ============================================================================

class PlaybookInput(BaseModel):
    """Input definition for playbook.json"""
    type: str = Field(..., description="Input type (e.g., 'string', 'list[string]', 'integer')")
    required: bool = Field(default=True, description="Whether this input is required")
    default: Optional[Any] = Field(None, description="Default value if not provided")
    description: Optional[str] = Field(None, description="Input description")


class PlaybookOutput(BaseModel):
    """Output definition for playbook.json"""
    type: str = Field(..., description="Output type (e.g., 'string', 'list[object]')")
    description: Optional[str] = Field(None, description="Output description")
    source: str = Field(..., description="Source path (e.g., 'step.ocr.ocr_text')")


class PlaybookStep(BaseModel):
    """Step definition in playbook.json"""
    id: str = Field(..., description="Step unique identifier")
    tool: str = Field(..., description="Tool name to call (e.g., 'core_files.ocr_pdf')")
    inputs: Dict[str, Any] = Field(..., description="Tool input parameters (supports template variables)")
    outputs: Dict[str, str] = Field(..., description="Output mapping (tool return field -> step output name)")
    depends_on: List[str] = Field(default_factory=list, description="Dependencies: list of step IDs that must complete first")


class PlaybookJson(BaseModel):
    """
    playbook.json schema - execution blueprint for runtime/ORS

    This is the compiled form of playbook.md, describing the actual workflow
    to execute. Template variables in steps.inputs use {{input.xxx}}, {{step.xxx.yyy}},
    {{context.xxx}} syntax for playbook-internal data flow.
    """
    version: str = Field(default="1.0", description="Schema version")
    playbook_code: str = Field(..., description="Corresponding playbook code")
    kind: PlaybookKind = Field(..., description="Playbook type: user_workflow or system_tool")
    steps: List[PlaybookStep] = Field(..., description="Execution steps")
    inputs: Dict[str, PlaybookInput] = Field(..., description="Playbook input definitions")
    outputs: Dict[str, PlaybookOutput] = Field(..., description="Playbook output definitions")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


# ============================================================================
# HandoffPlan and WorkflowStep Models
# ============================================================================

class RetryPolicy(BaseModel):
    """Retry policy for workflow step execution"""
    max_retries: int = Field(default=3, description="Maximum number of retry attempts")
    retry_delay: float = Field(default=1.0, description="Delay between retries in seconds")
    exponential_backoff: bool = Field(default=True, description="Use exponential backoff for retry delays")
    retryable_errors: List[str] = Field(
        default_factory=list,
        description="List of error types that should trigger retry (empty means retry all errors)"
    )


class ErrorHandlingStrategy(str, Enum):
    """Error handling strategy for workflow steps"""
    STOP_WORKFLOW = "stop_workflow"
    CONTINUE_ON_ERROR = "continue_on_error"
    SKIP_STEP = "skip_step"
    RETRY_THEN_STOP = "retry_then_stop"
    RETRY_THEN_CONTINUE = "retry_then_continue"


class WorkflowStep(BaseModel):
    """
    Workflow step in HandoffPlan

    This is the "complete version" that goes into WorkflowOrchestrator.
    The "simplified version" from IntentPipeline only has playbook_code + inputs.
    """
    playbook_code: str = Field(..., description="Playbook to execute")
    kind: PlaybookKind = Field(..., description="Playbook type")
    inputs: Dict[str, Any] = Field(..., description="Input parameters (supports $previous, $context syntax)")
    input_mapping: Dict[str, str] = Field(
        default_factory=dict,
        description="Input mapping from previous steps or context (e.g., '$previous.pdf_ocr.outputs.ocr_text')"
    )
    condition: Optional[str] = Field(None, description="Optional execution condition")
    interaction_mode: List[InteractionMode] = Field(
        default_factory=lambda: [InteractionMode.CONVERSATIONAL],
        description="How this step interacts with users"
    )
    retry_policy: Optional[RetryPolicy] = Field(
        None,
        description="Retry policy for this step. If None, uses default policy based on playbook kind."
    )
    error_handling: ErrorHandlingStrategy = Field(
        default=ErrorHandlingStrategy.RETRY_THEN_STOP,
        description="Error handling strategy when step fails"
    )


class HandoffPlan(BaseModel):
    """
    HandoffPlan: Workspace LLM → Playbook LLM handoff protocol

    Generated by Workspace LLM, consumed by Playbook LLM + WorkflowOrchestrator.
    Serialized as JSON in Workspace LLM response within <playbook_handoff>...</playbook_handoff> tags.
    """
    steps: List[WorkflowStep] = Field(..., description="Workflow steps to execute")
    context: Dict[str, Any] = Field(default_factory=dict, description="Initial context (e.g., uploaded files)")
    estimated_duration: Optional[int] = Field(None, description="Estimated execution time in seconds")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
