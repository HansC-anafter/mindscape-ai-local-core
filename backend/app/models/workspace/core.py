"""
Workspace core models — Workspace entity and API request/response models.
"""

from datetime import datetime
from typing import Optional, Dict, Any, List

from pydantic import BaseModel, Field

from ._common import _utc_now
from .enums import (
    WorkspaceType,
    LaunchStatus,
    ProjectAssignmentMode,
)
from ..workspace_blueprint import WorkspaceBlueprint


# ==================== Workspace Model ====================


class Workspace(BaseModel):
    """
    Workspace model - unified frontend interface container

    A Workspace is a top-level container that represents a user's working context.
    It aggregates events from multiple channels (local_chat, line, wp, etc.)
    and provides a unified timeline view.

    Key characteristics:
    - One Workspace can be associated with one or more Projects/Themes
    - Multiple channels can feed events into the same Workspace
    - All user interactions (chat, file upload, playbook execution) happen within a Workspace
    """

    id: str = Field(..., description="Unique workspace identifier")
    title: str = Field(..., description="Workspace display title")
    description: Optional[str] = Field(None, description="Workspace description")

    # Workspace type for vertical domain support
    workspace_type: Optional[WorkspaceType] = Field(
        default=WorkspaceType.PERSONAL,
        description="Workspace type: personal (default) | brand | team | course | research",
    )

    # Owner and primary associations
    owner_user_id: str = Field(..., description="Owner profile ID")
    primary_project_id: Optional[str] = Field(
        None, description="Primary associated project ID (if applicable)"
    )

    # Optional configuration
    default_playbook_id: Optional[str] = Field(
        None, description="Default playbook to use for this workspace"
    )
    default_locale: Optional[str] = Field(
        None, description="Default locale for this workspace (e.g., 'zh-TW', 'en')"
    )
    mode: Optional[str] = Field(
        None,
        description="Workspace mode: 'research' | 'publishing' | 'planning' | null",
    )
    data_sources: Optional[Dict[str, Any]] = Field(
        None,
        description="Data sources configuration: local_folder, obsidian_vault, wordpress, rag_source",
    )
    playbook_auto_execution_config: Optional[Dict[str, Any]] = Field(
        None,
        description="Playbook auto-execution configuration: {playbook_code: {confidence_threshold: float, auto_execute: bool}}",
    )
    suggestion_history: Optional[List[Dict[str, Any]]] = Field(
        None,
        description="Suggestion history (last 3 rounds): [{round_id, timestamp, suggestions: [...]}]",
    )

    # Storage configuration
    storage_base_path: Optional[str] = Field(
        None,
        description="Workspace base storage path (e.g., ~/Documents/Mindscape/workspace_name)",
    )
    artifacts_dir: Optional[str] = Field(
        "artifacts", description="Artifacts subdirectory (default: 'artifacts')"
    )
    uploads_dir: Optional[str] = Field(
        "uploads", description="Uploads subdirectory (default: 'uploads')"
    )
    storage_config: Optional[Dict[str, Any]] = Field(
        None, description="Storage configuration (bucket rules, naming rules, etc.)"
    )
    playbook_storage_config: Optional[Dict[str, Dict[str, Any]]] = Field(
        None,
        description="Playbook-specific storage configuration: "
        "{playbook_code: {base_path: str, artifacts_dir: str}}",
    )

    # Execution mode configuration
    execution_mode: Optional[str] = Field(
        default="qa",
        description="Workspace execution mode: 'qa' | 'execution' | 'hybrid'",
    )
    expected_artifacts: Optional[List[str]] = Field(
        default=None,
        description="Expected artifact types for this workspace (e.g., ['pptx', 'xlsx', 'docx'])",
    )
    execution_priority: Optional[str] = Field(
        default="medium", description="Execution priority: 'low' | 'medium' | 'high'"
    )

    # Project assignment configuration
    project_assignment_mode: Optional[ProjectAssignmentMode] = Field(
        default=ProjectAssignmentMode.AUTO_SILENT,
        description="Project assignment automation level",
    )

    # Capability profile override for staged model switching
    capability_profile: Optional[str] = Field(
        None,
        description="Workspace-level capability profile override (fast/standard/precise/tool_strict/safe_write). "
        "Overrides system default for this workspace.",
    )

    # External Agent configuration (unified for all workspaces)
    # Users explicitly choose which agent to use; governance applies automatically
    preferred_agent: Optional[str] = Field(
        None,
        description="Currently selected external agent for task execution (e.g., 'openclaw', 'aider'). "
        "When set, tasks are routed to this agent instead of Mindscape LLM. "
        "All workspaces can use external agents - governance/sandbox applies automatically.",
    )
    sandbox_config: Optional[Dict[str, Any]] = Field(
        None,
        description="Sandbox configuration for external agent execution: "
        "{filesystem_scope: [...], network_allowlist: [...], tool_policies: {...}, max_execution_time_seconds: int}. "
        "Applied automatically when using external agents.",
    )
    agent_fallback_enabled: bool = Field(
        default=True,
        description="If preferred_agent fails or is unavailable, fallback to Mindscape LLM",
    )

    # Extensible metadata for features (core_memory, preferences, etc.)
    metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Extensible metadata storage for workspace features (core_memory, preferences, etc.)",
    )

    # Workspace launch enhancement fields
    workspace_blueprint: Optional[WorkspaceBlueprint] = Field(
        None,
        description="Workspace blueprint configuration: goals, initial_intents, ai_team, playbooks, tool_connections",
    )
    launch_status: "LaunchStatus" = Field(
        default=LaunchStatus.PENDING,
        description="Launch status: pending / ready / active",
    )
    starter_kit_type: Optional[str] = Field(
        None,
        description="Starter kit type: content_generation / client_delivery / knowledge_base / custom",
    )

    # Timestamps
    created_at: datetime = Field(
        default_factory=_utc_now, description="Creation timestamp"
    )
    updated_at: datetime = Field(
        default_factory=_utc_now, description="Last update timestamp"
    )

    model_config = {
        "from_attributes": True,
        "json_encoders": {datetime: lambda v: v.isoformat()},
    }


# ==================== API Request/Response Models ====================


class CreateWorkspaceRequest(BaseModel):
    """Request to create a new workspace"""

    title: str = Field(..., description="Workspace title")
    description: Optional[str] = Field(None, description="Workspace description")
    workspace_type: Optional[WorkspaceType] = Field(
        default=WorkspaceType.PERSONAL,
        description="Workspace type: personal (default) | brand | team",
    )
    primary_project_id: Optional[str] = Field(
        None, description="Primary project ID to associate"
    )
    default_playbook_id: Optional[str] = Field(None, description="Default playbook ID")
    default_locale: Optional[str] = Field(None, description="Default locale")
    storage_base_path: Optional[str] = Field(
        None, description="Storage base path (allows manual specification)"
    )
    artifacts_dir: Optional[str] = Field(
        None, description="Artifacts directory name (default: 'artifacts')"
    )
    execution_mode: Optional[str] = Field(
        None, description="Execution mode: 'qa' | 'execution' | 'hybrid'"
    )
    expected_artifacts: Optional[List[str]] = Field(
        None, description="Expected artifact types"
    )
    execution_priority: Optional[str] = Field(
        None, description="Execution priority: 'low' | 'medium' | 'high'"
    )
    # External Agent configuration (unified for all workspaces)
    preferred_agent: Optional[str] = Field(
        None,
        description="Selected external agent (e.g., 'openclaw'). Null = Mindscape LLM",
    )
    sandbox_config: Optional[Dict[str, Any]] = Field(
        None, description="Sandbox configuration for agent execution"
    )
    agent_fallback_enabled: bool = Field(
        default=True, description="Fallback to Mindscape LLM if agent fails"
    )
    # Workspace launch enhancement fields (optional, can be set via seed/blueprint flow)
    workspace_blueprint: Optional[WorkspaceBlueprint] = Field(
        None, description="Workspace blueprint configuration"
    )
    starter_kit_type: Optional[str] = Field(None, description="Starter kit type")


class UpdateWorkspaceRequest(BaseModel):
    """Request to update an existing workspace"""

    title: Optional[str] = Field(None, description="Workspace title")
    description: Optional[str] = Field(None, description="Workspace description")
    workspace_type: Optional[WorkspaceType] = Field(
        None, description="Workspace type: personal | brand | team"
    )
    primary_project_id: Optional[str] = Field(None, description="Primary project ID")
    default_playbook_id: Optional[str] = Field(None, description="Default playbook ID")
    default_locale: Optional[str] = Field(None, description="Default locale")
    mode: Optional[str] = Field(
        None,
        description="Workspace mode: 'research' | 'publishing' | 'planning' | null",
    )
    storage_base_path: Optional[str] = Field(
        None,
        description="Storage base path (Changing this may affect existing artifacts)",
    )
    artifacts_dir: Optional[str] = Field(
        None,
        description="Artifacts directory name (Changing this may affect existing artifacts)",
    )
    playbook_storage_config: Optional[Dict[str, Dict[str, Any]]] = Field(
        None,
        description="Playbook-specific storage configuration: "
        "{playbook_code: {base_path: str, artifacts_dir: str}}",
    )
    execution_mode: Optional[str] = Field(
        None, description="Execution mode: 'qa' | 'execution' | 'hybrid'"
    )
    expected_artifacts: Optional[List[str]] = Field(
        None, description="Expected artifact types"
    )
    execution_priority: Optional[str] = Field(
        None, description="Execution priority: 'low' | 'medium' | 'high'"
    )
    capability_profile: Optional[str] = Field(
        None,
        description="Workspace-level capability profile override (fast/standard/precise/tool_strict/safe_write). "
        "Overrides system default for this workspace.",
    )
    # External Agent configuration (unified for all workspaces)
    preferred_agent: Optional[str] = Field(
        None,
        description="Selected external agent (e.g., 'openclaw'). Null = Mindscape LLM",
    )
    sandbox_config: Optional[Dict[str, Any]] = Field(
        None, description="Sandbox configuration for agent execution"
    )
    agent_fallback_enabled: Optional[bool] = Field(
        None, description="Fallback to Mindscape LLM if agent fails"
    )
    # Workspace launch enhancement fields (optional)
    workspace_blueprint: Optional[WorkspaceBlueprint] = Field(
        None, description="Workspace blueprint configuration"
    )
    launch_status: Optional[LaunchStatus] = Field(
        None, description="Launch status: pending / ready / active"
    )
    starter_kit_type: Optional[str] = Field(None, description="Starter kit type")


class WorkspaceChatRequest(BaseModel):
    """Request for workspace chat interaction"""

    message: Optional[str] = Field(None, description="User message")
    files: list[str] = Field(
        default_factory=list, description="List of uploaded file IDs"
    )
    mode: str = Field(
        default="auto",
        description="Interaction mode: 'auto' | 'qa_only' | 'force_playbook'",
    )
    stream: bool = Field(default=True, description="Enable streaming response (SSE)")
    project_id: Optional[str] = Field(
        None, description="Project ID for project context"
    )
    thread_id: Optional[str] = Field(
        None, description="Conversation thread ID for conversation threading"
    )
    # CTA trigger fields
    timeline_item_id: Optional[str] = Field(
        None, description="Timeline item ID for CTA action"
    )
    action: Optional[str] = Field(
        None,
        description="Action type: 'add_to_intents' | 'add_to_tasks' | 'publish_to_wordpress' | 'execute_playbook' | 'use_tool' | 'create_intent' | 'start_chat' | 'upload_file'",
    )
    confirm: Optional[bool] = Field(
        None, description="Confirmation flag for external_write actions"
    )
    model_name: Optional[str] = Field(
        None, description="Override LLM model name (e.g. 'gemini-2.5-pro')"
    )
    action_params: Optional[Dict[str, Any]] = Field(
        None, description="Action parameters (for dynamic suggestions)"
    )


class WorkspaceChatResponse(BaseModel):
    """Response from workspace chat interaction"""

    workspace_id: str = Field(..., description="Workspace ID")
    display_events: list[dict] = Field(
        default_factory=list, description="Recent events to display in timeline"
    )
    triggered_playbook: Optional[dict] = Field(
        None, description="Triggered playbook information (if any)"
    )
    pending_tasks: list[dict] = Field(
        default_factory=list, description="Pending task status cards"
    )
