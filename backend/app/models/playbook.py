"""
Playbook data models
Simplified version for v0 MVP - local Playbook library
"""

from datetime import datetime
from typing import List, Optional, Dict, Any, Literal
from enum import Enum
from pydantic import BaseModel, Field, validator

try:
    from pydantic import model_validator
except ImportError:
    # Pydantic v1 fallback
    from pydantic import root_validator

    def model_validator(*args, **kwargs):
        return root_validator(*args, skip_on_failure=True, **kwargs)


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


class PlaybookOwnerType(str, Enum):
    """
    Playbook ownership type

    Determines who owns and controls this playbook:
    - system: Official Mindscape playbooks (e.g., basic writing, SEO, vectorization)
    - tenant: Tenant-level shared playbooks (multi-workspace)
    - workspace: Workspace-level shared playbooks (team SOPs)
    - user: Personal playbooks (individual workflows)
    - external_provider: Playbooks from external integrations
    """

    SYSTEM = "system"
    TENANT = "tenant"
    WORKSPACE = "workspace"
    USER = "user"
    EXTERNAL_PROVIDER = "external_provider"


class PlaybookVisibility(str, Enum):
    """
    Playbook visibility / sharing level

    Controls who can see and use this playbook:
    - private: Only owner can use
    - workspace_shared: Visible to all users in the same workspace
    - tenant_shared: Visible to all workspaces in the same tenant
    - public_template: Can be copied as template, but execution requires importing to own space
    """

    PRIVATE = "private"
    WORKSPACE_SHARED = "workspace_shared"
    TENANT_SHARED = "tenant_shared"
    PUBLIC_TEMPLATE = "public_template"


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
        ..., description="Tool type: builtin, langchain, or mcp"
    )
    name: str = Field(..., description="Tool name or identifier")
    source: Optional[str] = Field(
        None,
        description="Tool source: full class path for LangChain, server ID for MCP",
    )
    config: Dict[str, Any] = Field(
        default_factory=dict,
        description="Tool configuration (API keys, environment variables, etc.), supports ${VAR} syntax",
    )
    required: bool = Field(
        default=True,
        description="Whether the tool is required (execution blocked if missing)",
    )
    fallback: Optional[str] = Field(
        None, description="Fallback tool name (when main tool is unavailable)"
    )
    description: Optional[str] = Field(None, description="Tool purpose description")

    @validator("source")
    def validate_source(cls, v, values):
        """Validate source field"""
        tool_type = values.get("type")

        if tool_type == "langchain" and not v:
            raise ValueError("LangChain tools must provide source (full class path)")

        return v


class AgentDefinition(BaseModel):
    """Agent Definition - Agent 定義（球員名單中的一個球員）"""

    agent_id: str = Field(
        ..., description="Unique agent ID (e.g., 'researcher', 'writer', 'reviewer')"
    )
    agent_name: str = Field(..., description="Display name")

    # Agent 定義（可解析的定義）
    system_prompt: Optional[str] = Field(
        None, description="Agent-specific system prompt"
    )
    role: Optional[str] = Field(
        None, description="Agent role (e.g., 'researcher', 'engineer', 'reviewer')"
    )
    tools: List[str] = Field(
        default_factory=list, description="Tool IDs this agent can use"
    )
    memory_scope: Optional[str] = Field(
        None, description="Memory scope: workspace/session/task"
    )
    responsibility_boundary: Optional[str] = Field(
        None, description="Responsibility boundary description"
    )

    # Capability profile
    capability_profile: Optional[str] = Field(
        None, description="Capability profile for this agent"
    )


class PlaybookMetadata(BaseModel):
    """Playbook metadata (simplified for v0)"""

    playbook_code: str = Field(..., description="Unique playbook identifier")
    version: str = Field(default="1.0.0", description="Playbook version")

    locale: str = Field(
        default="zh-TW",
        description="Language locale. Deprecated: use target_language parameter at execution time instead. "
        "Kept for backward compatibility only.",
    )

    name: str = Field(..., description="Playbook name")
    description: str = Field(default="", description="Playbook description")
    tags: List[str] = Field(default_factory=list, description="Tags for categorization")

    language_strategy: str = Field(
        default="model_native",
        description="Language handling strategy: 'model_native' (use LLM's multilingual capabilities), "
        "'i18n_fallback' (use i18n files for specialized terminology)",
    )

    supports_execution_chat: bool = Field(
        default=False,
        description="Whether this playbook supports execution-scoped chat. "
        "If true, ExecutionChatPanel will be displayed in ExecutionInspector.",
    )

    discussion_agent: Optional[str] = Field(
        default=None,
        description="Agent persona for execution chat (e.g., 'planner', 'coordinator', 'researcher'). "
        "If not specified, uses default system assistant persona.",
    )

    supported_locales: List[str] = Field(
        default_factory=lambda: ["zh-TW", "en"],
        description="Officially tested locales. Not required for execution. "
        "Playbooks are language-neutral and support any language via target_language parameter.",
    )
    default_locale: str = Field(
        default="en",
        description="Default locale when user's locale is not in supported_locales. "
        "Use target_language parameter at execution time instead.",
    )
    auto_localize: bool = Field(
        default=True,
        description="Allow LLM-assisted localization for unsupported locales. "
        "Default behavior with language_strategy='model_native'.",
    )

    capability_code: Optional[str] = Field(
        default=None,
        description="Capability pack code this playbook belongs to (e.g., 'ig', 'web_generation'). "
        "Set when playbook is loaded from a capability pack manifest.",
    )

    # AI Role association (for external export)
    entry_agent_type: Optional[str] = Field(
        default=None, description="Corresponding AI role: planner, writer, coach, coder"
    )

    # Onboarding
    onboarding_task: Optional[str] = Field(
        default=None, description="Onboarding task identifier (e.g., task2, task3)"
    )
    icon: Optional[str] = Field(default=None, description="Emoji icon for the playbook")

    required_tools: List[str] = Field(
        default_factory=list,
        description="Simple tool list (legacy format, backward compatible)",
    )

    tool_dependencies: List[ToolDependency] = Field(
        default_factory=list,
        description="Detailed tool dependency declarations (supports LangChain/MCP)",
    )

    # Background routine configuration
    background: bool = Field(
        default=False,
        description="Whether this playbook is a background routine (runs on schedule)",
    )

    optional_tools: List[str] = Field(
        default_factory=list,
        description="Optional tools (playbook can degrade gracefully if missing)",
    )

    # Playbook classification (for workflow orchestration)
    kind: PlaybookKind = Field(
        default=PlaybookKind.USER_WORKFLOW,
        description="Playbook type: user_workflow (for users) or system_tool (for system operations)",
    )

    interaction_mode: List[InteractionMode] = Field(
        default_factory=lambda: [InteractionMode.CONVERSATIONAL],
        description="How this playbook interacts with users: silent, needs_review, or conversational",
    )

    visible_in: List[VisibleIn] = Field(
        default_factory=lambda: [VisibleIn.WORKSPACE_PLAYBOOK_MENU],
        description="Where this playbook should be visible in UI",
    )

    # Scope and Owner (legacy fields, kept for backward compatibility)
    scope: Optional[Dict[str, Any]] = Field(
        default_factory=lambda: {"visibility": "system", "editable": False},
        description="Scope configuration (visibility, editable). "
        "Values: system, tenant, profile, workspace. "
        "system/tenant/profile = template (shared), workspace = instance (forked). "
        "DEPRECATED: Use owner_type, owner_id, visibility instead.",
    )
    owner: Optional[Dict[str, Any]] = Field(
        default_factory=lambda: {"type": "system"},
        description="Owner information. DEPRECATED: Use owner_type, owner_id instead.",
    )

    # Identity and ownership (new fields)
    owner_type: PlaybookOwnerType = Field(
        default=PlaybookOwnerType.USER,
        description="Playbook ownership type: system, tenant, workspace, user, external_provider",
    )
    owner_id: str = Field(
        default="default_user",
        description="Owner ID: system_id / tenant_id / workspace_id / user_id / provider_id",
    )
    visibility: PlaybookVisibility = Field(
        default=PlaybookVisibility.WORKSPACE_SHARED,
        description="Visibility level: private, workspace_shared, tenant_shared, public_template",
    )

    # Scope and capability tags
    capability_tags: List[str] = Field(
        default_factory=list,
        description="Capability tags for filtering (e.g., ['writing', 'seo', 'vectorization'])",
    )
    project_types: Optional[List[str]] = Field(
        None,
        description="Applicable project types (e.g., ['writing', 'website', 'course'])",
    )
    allowed_tools: Optional[List[str]] = Field(
        None,
        description="Allowed tools / connectors for this playbook (whitelist). NOTE: v1 not enabled, reserved field only",
    )

    # Workspace sharing for user-owned playbooks
    shared_with_workspaces: List[str] = Field(
        default_factory=list,
        description="List of workspace IDs this user-owned playbook is shared with (for workspace_shared visibility)",
    )

    def get_scope_level(self) -> Optional[str]:
        """
        Get scope level as string

        Returns:
            "system", "tenant", "profile", "workspace", or None
        """
        if not self.scope:
            return None
        return self.scope.get("visibility") or self.scope.get("scope")

    def is_template(self) -> bool:
        """
        Check if this playbook is a template (shared)

        Returns:
            True if scope is system/tenant/profile (template), False if workspace (instance)
        """
        scope_level = self.get_scope_level()
        return scope_level in ("system", "tenant", "profile")

    def is_instance(self) -> bool:
        """
        Check if this playbook is an instance (workspace-scoped)

        Returns:
            True if scope is workspace (instance), False otherwise
        """
        return self.get_scope_level() == "workspace"

    def can_edit_sop(self) -> bool:
        """
        Check if SOP can be edited

        Template playbooks (system/tenant/profile) cannot have their SOP edited directly.
        Only workspace-scoped instances can be fully edited.

        Returns:
            True if SOP can be edited, False otherwise
        """
        # Only workspace-scoped instances can edit SOP
        return self.is_instance()

    # Runtime configuration
    runtime_handler: str = Field(
        default="local_llm",
        description="Runtime handler: local_llm, remote_crs, custom",
    )

    # Runtime tier (new)
    runtime_tier: Optional[str] = Field(
        None, description="Runtime tier: local, cloud_recommended, cloud_only"
    )

    # Runtime configuration (new)
    runtime: Optional[Dict[str, Any]] = Field(
        None, description="Runtime configuration for cloud execution"
    )

    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Playbook(BaseModel):
    """Complete Playbook definition"""

    metadata: PlaybookMetadata
    sop_content: str = Field(default="", description="SOP content in Markdown")

    # Optional: user notes for personalization
    user_notes: Optional[str] = Field(
        None, description="User's personal notes about this playbook"
    )

    # 階段 2 擴展：Agent Roster（球員名單）
    agent_roster: Optional[Dict[str, AgentDefinition]] = Field(
        None, description="Agent roster for this playbook: {agent_id: AgentDefinition}"
    )

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class PlaybookRun(BaseModel):
    """
    playbook.run = playbook.md + playbook.json

    Complete playbook definition with both human-readable description
    and machine-readable execution spec.
    """

    playbook: Playbook = Field(
        ..., description="Playbook.md definition (human-readable)"
    )
    playbook_json: Optional["PlaybookJson"] = Field(
        None, description="Playbook.json definition (machine-readable)"
    )

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
            return "workflow"
        return "conversation"

    def get_execution_profile(self) -> "ExecutionProfile":
        """
        Get execution profile for this playbook

        Returns:
            ExecutionProfile instance with runtime selection criteria
        """
        from backend.app.core.runtime_port import ExecutionProfile

        if self.playbook_json and self.playbook_json.execution_profile:
            return ExecutionProfile(**self.playbook_json.execution_profile)

        # Default profile (simple mode)
        return ExecutionProfile(
            execution_mode="simple",
            supports_resume=False,
            requires_human_approval=False,
            side_effect_level="none",
        )

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


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
    playbook_json: Optional[Dict[str, Any]] = None


class PlaybookAssociation(BaseModel):
    """Association between IntentCard and Playbook"""

    intent_id: str
    playbook_code: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


# ============================================================================
# playbook.json Schema Models
# ============================================================================


class PlaybookInput(BaseModel):
    """Input definition for playbook.json"""

    type: str = Field(
        ..., description="Input type (e.g., 'string', 'list[string]', 'integer')"
    )
    required: bool = Field(default=True, description="Whether this input is required")
    default: Optional[Any] = Field(None, description="Default value if not provided")
    description: Optional[str] = Field(None, description="Input description")


class PlaybookOutput(BaseModel):
    """Output definition for playbook.json"""

    type: str = Field(..., description="Output type (e.g., 'string', 'list[object]')")
    description: Optional[str] = Field(None, description="Output description")
    source: str = Field(..., description="Source path (e.g., 'step.ocr.ocr_text')")


class ToolPolicy(BaseModel):
    """
    Tool execution policy constraints

    Controls what tools can be called and under what conditions.
    Used for security and workflow control.
    """

    risk_level: Literal["read", "write"] = Field(
        default="read", description="Risk level: read-only or write operations"
    )
    env: Literal["sandbox_only", "allow_prod"] = Field(
        default="sandbox_only",
        description="Environment constraint: sandbox only or allow production",
    )
    requires_preview: bool = Field(
        default=True,
        description="Whether write operations require preview before execution",
    )
    allowed_slots: Optional[List[str]] = Field(
        None, description="List of allowed tool slots (alternative to tool_slot field)"
    )
    allowed_tool_patterns: Optional[List[str]] = Field(
        None,
        description="Allowed tool ID patterns (e.g., ['wp-*.wordpress.*', 'canva-*.canva.*'])",
    )


class GateSpec(BaseModel):
    """
    Gate specification for a playbook step.

    Used by workflow runtimes to pause execution for human approval.
    """

    required: bool = Field(
        default=False, description="Whether this step requires human approval"
    )
    type: Literal["validation", "modification"] = Field(
        default="validation", description="Gate type"
    )
    operation: Optional[str] = Field(
        default=None, description="Operation name (e.g., 'batch_update', 'publish')"
    )
    checkpoint_required: Optional[bool] = Field(
        default=None,
        description="Whether checkpoint is required for rollback (typically for modification gates)",
    )


class PlaybookStep(BaseModel):
    """
    Step definition in playbook.json

    Supports two modes:
    1. Legacy mode: tool field (concrete tool ID, e.g., 'wp-ets1.wordpress.update_footer')
    2. Slot mode: tool_slot field (logical slot, e.g., 'cms.footer.apply_style')

    Tool slot mode allows workspace/project-level tool binding without modifying playbook.
    """

    id: str = Field(..., description="Step unique identifier")

    # Legacy mode: concrete tool ID (backward compatible)
    tool: Optional[str] = Field(
        None,
        description="Concrete tool ID to call (e.g., 'wp-ets1.wordpress.update_footer'). "
        "Legacy field, use tool_slot for new playbooks.",
    )

    # Slot mode: logical tool slot (recommended for new playbooks)
    tool_slot: Optional[str] = Field(
        None,
        description="Logical tool slot identifier (e.g., 'cms.footer.apply_style'). "
        "Resolved to concrete tool_id at runtime via workspace/project mapping.",
    )

    # Policy constraints for tool execution
    tool_policy: Optional[ToolPolicy] = Field(
        None,
        description="Tool execution policy constraints (risk level, environment, preview requirements)",
    )

    inputs: Dict[str, Any] = Field(
        ..., description="Tool input parameters (supports template variables)"
    )
    outputs: Dict[str, str] = Field(
        ..., description="Output mapping (tool return field -> step output name)"
    )
    depends_on: List[str] = Field(
        default_factory=list,
        description="Dependencies: list of step IDs that must complete first",
    )
    condition: Optional[str] = Field(
        None,
        description="Optional execution condition (e.g., '{{input.xxx or input.yyy}}')",
    )

    # Loop/iteration support
    for_each: Optional[str] = Field(
        None,
        description="Path to array to iterate over (e.g., 'step.search_photos.photos'). "
        "If specified, the step will be executed once for each item in the array. "
        "The current item is available as '{{item}}' in inputs, and the index as '{{index}}'.",
    )

    # Loop/iteration support
    for_each: Optional[str] = Field(
        None,
        description="Path to array to iterate over (e.g., 'step.search_photos.photos'). "
        "If specified, the step will be executed once for each item in the array. "
        "The current item is available as '{{item}}' in inputs, and the index as '{{index}}'.",
    )

    @model_validator(mode="before")
    @classmethod
    def validate_tool_or_slot(cls, values):
        """
        Ensure either tool (legacy) or tool_slot (new) is provided

        Backward compatibility: old playbooks with tool field still work.
        New playbooks should use tool_slot for flexibility.
        """
        # In 'before' mode, values is a dict
        if isinstance(values, dict):
            tool = values.get("tool")
            tool_slot = values.get("tool_slot")

            # At least one must be provided
            if not tool and not tool_slot:
                raise ValueError(
                    "Either 'tool' (legacy) or 'tool_slot' (recommended) must be provided"
                )

            # Both cannot be provided
            if tool and tool_slot:
                raise ValueError(
                    "Cannot specify both 'tool' and 'tool_slot'. Use 'tool_slot' for new playbooks."
                )

        return values

    gate: Optional[GateSpec] = Field(
        default=None,
        description="Optional gate configuration for human approval (pause/resume support)",
    )


class ConcurrencyPolicy(BaseModel):
    """Runner-level concurrency control for playbook execution.

    Allows playbooks to declare lock constraints so the runner can prevent
    conflicting parallel executions (e.g., same IG profile, same sandbox).

    Example in playbook.json:
        "concurrency": {
            "lock_key_input": "user_data_dir",
            "max_parallel": 1,
            "lock_scope": "input"
        }
    """

    lock_key_input: str = Field(
        ...,
        description="Name of the input parameter whose value is used as the lock key "
        "(e.g., 'user_data_dir' for IG playbooks).",
    )
    max_parallel: int = Field(
        default=1,
        description="Maximum concurrent executions sharing the same lock key value. "
        "Default 1 means exclusive (no overlap).",
    )
    lock_scope: str = Field(
        default="input",
        description="Lock scope: 'input' (lock by input value), 'playbook' (lock by playbook_code), "
        "'workspace' (lock by workspace).",
    )


class PlaybookJson(BaseModel):
    """
    playbook.json schema - execution blueprint for runtime/ORS

    This is the compiled form of playbook.md, describing the actual workflow
    to execute. Template variables in steps.inputs use {{input.xxx}}, {{step.xxx.yyy}},
    {{context.xxx}} syntax for playbook-internal data flow.
    """

    version: str = Field(default="1.0", description="Schema version")
    playbook_code: str = Field(..., description="Corresponding playbook code")
    kind: PlaybookKind = Field(
        ..., description="Playbook type: user_workflow or system_tool"
    )
    steps: List[PlaybookStep] = Field(..., description="Execution steps")
    inputs: Dict[str, PlaybookInput] = Field(
        ..., description="Playbook input definitions"
    )
    outputs: Dict[str, PlaybookOutput] = Field(
        ..., description="Playbook output definitions"
    )
    execution_profile: Optional[Dict[str, Any]] = Field(
        None,
        description="Execution profile for runtime selection (execution_mode, supports_resume, concurrency, etc.)",
    )
    concurrency: Optional["ConcurrencyPolicy"] = Field(
        None,
        description="Runner-level concurrency control. Declares lock constraints "
        "so the runner can prevent conflicting parallel executions.",
    )

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


# ============================================================================
# HandoffPlan and WorkflowStep Models
# ============================================================================


class RetryPolicy(BaseModel):
    """Retry policy for workflow step execution"""

    max_retries: int = Field(default=3, description="Maximum number of retry attempts")
    retry_delay: float = Field(
        default=1.0, description="Delay between retries in seconds"
    )
    exponential_backoff: bool = Field(
        default=True, description="Use exponential backoff for retry delays"
    )
    retryable_errors: List[str] = Field(
        default_factory=list,
        description="List of error types that should trigger retry (empty means retry all errors)",
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
    inputs: Dict[str, Any] = Field(
        ..., description="Input parameters (supports $previous, $context syntax)"
    )
    input_mapping: Dict[str, str] = Field(
        default_factory=dict,
        description="Input mapping from previous steps or context (e.g., '$previous.pdf_ocr.outputs.ocr_text')",
    )
    condition: Optional[str] = Field(None, description="Optional execution condition")
    interaction_mode: List[InteractionMode] = Field(
        default_factory=lambda: [InteractionMode.CONVERSATIONAL],
        description="How this step interacts with users",
    )
    retry_policy: Optional[RetryPolicy] = Field(
        None,
        description="Retry policy for this step. If None, uses default policy based on playbook kind.",
    )
    error_handling: ErrorHandlingStrategy = Field(
        default=ErrorHandlingStrategy.RETRY_THEN_STOP,
        description="Error handling strategy when step fails",
    )


class HandoffPlan(BaseModel):
    """
    HandoffPlan: Workspace LLM → Playbook LLM handoff protocol

    Generated by Workspace LLM, consumed by Playbook LLM + WorkflowOrchestrator.
    Serialized as JSON in Workspace LLM response within <playbook_handoff>...</playbook_handoff> tags.
    """

    steps: List[WorkflowStep] = Field(..., description="Workflow steps to execute")
    context: Dict[str, Any] = Field(
        default_factory=dict, description="Initial context (e.g., uploaded files)"
    )
    estimated_duration: Optional[int] = Field(
        None, description="Estimated execution time in seconds"
    )

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


# ============================================================================
# Playbook Invocation Context and Strategy Models
# ============================================================================


class InvocationMode(str, Enum):
    """Playbook invocation mode"""

    STANDALONE = "standalone"
    PLAN_NODE = "plan_node"
    SUBROUTINE = "subroutine"


class InvocationTolerance(str, Enum):
    """Tolerance level for data insufficiency"""

    STRICT = "strict"
    LENIENT = "lenient"
    ADAPTIVE = "adaptive"


class InvocationStrategy(BaseModel):
    """
    Invocation strategy for playbook execution

    Defines how a playbook should behave in a specific invocation context.
    Different strategies allow the same playbook to adapt to different scenarios.
    """

    max_lookup_rounds: int = Field(
        default=3,
        description="Maximum number of lookup rounds for data gathering (standalone mode)",
    )
    allow_spawn_new_tasks: bool = Field(
        default=False, description="Whether this playbook can spawn new tasks"
    )
    allow_expansion: bool = Field(
        default=False,
        description="Whether this playbook can expand (create new scripts)",
    )
    wait_for_upstream_tasks: bool = Field(
        default=True,
        description="Whether to wait for upstream tasks in plan (plan_node mode)",
    )
    tolerance: InvocationTolerance = Field(
        default=InvocationTolerance.STRICT,
        description="Tolerance level when data is insufficient",
    )


class PlanContext(BaseModel):
    """Plan context for plan_node mode"""

    plan_summary: str = Field(..., description="Plan summary")
    reasoning: str = Field(..., description="Plan reasoning")
    steps: List[Dict[str, Any]] = Field(
        default_factory=list, description="Execution steps"
    )
    dependencies: List[str] = Field(
        default_factory=list, description="Dependencies: list of task IDs"
    )


class PlaybookInvocationContext(BaseModel):
    """
    Playbook invocation context

    Describes the execution scenario for a playbook invocation.
    The same playbook can have different behaviors based on the context.
    """

    mode: InvocationMode = Field(
        ..., description="Execution mode: standalone, plan_node, or subroutine"
    )
    project_id: Optional[str] = Field(None, description="Project ID")
    phase_id: Optional[str] = Field(None, description="Project Phase ID")
    plan_id: Optional[str] = Field(None, description="Plan ID (if mode is plan_node)")
    task_id: Optional[str] = Field(None, description="Task ID (if mode is plan_node)")
    plan_context: Optional[PlanContext] = Field(
        None, description="Plan context (if mode is plan_node)"
    )
    visible_state: Optional[Dict[str, Any]] = Field(
        None,
        description="Visible state snapshot (workspace state visible to this invocation)",
    )
    strategy: InvocationStrategy = Field(
        default_factory=lambda: InvocationStrategy(),
        description="Invocation strategy for this context",
    )
    trace_id: str = Field(
        ..., description="Global trace ID for this user request/execution"
    )
    parent_run_id: Optional[str] = Field(
        None, description="Parent run ID (if mode is subroutine)"
    )

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}
