"""Core playbook models."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from .dependencies import AgentDefinition, ToolDependency
from .enums import (
    InteractionMode,
    PlaybookKind,
    PlaybookOwnerType,
    PlaybookVisibility,
    VisibleIn,
)
from .schema import PlaybookJson


class PlaybookMetadata(BaseModel):
    """Playbook metadata."""

    playbook_code: str = Field(..., description="Unique playbook identifier")
    version: str = Field(default="1.0.0", description="Playbook version")
    locale: str = Field(
        default="zh-TW",
        description="Language locale. Deprecated: use target_language at execution time.",
    )
    name: str = Field(..., description="Playbook name")
    description: str = Field(default="", description="Playbook description")
    tags: List[str] = Field(default_factory=list, description="Tags for categorization")
    language_strategy: str = Field(
        default="model_native",
        description="Language strategy: model_native or i18n_fallback",
    )
    supports_execution_chat: bool = Field(
        default=False,
        description="Whether this playbook supports execution-scoped chat.",
    )
    discussion_agent: Optional[str] = Field(
        default=None, description="Agent persona for execution chat."
    )
    supported_locales: List[str] = Field(
        default_factory=lambda: ["zh-TW", "en"],
        description="Officially tested locales.",
    )
    default_locale: str = Field(
        default="en",
        description="Default locale when user locale is unsupported.",
    )
    auto_localize: bool = Field(
        default=True,
        description="Allow LLM-assisted localization for unsupported locales.",
    )
    capability_code: Optional[str] = Field(
        default=None,
        description="Capability pack code this playbook belongs to.",
    )
    entry_agent_type: Optional[str] = Field(
        default=None, description="Corresponding AI role."
    )
    onboarding_task: Optional[str] = Field(
        default=None, description="Onboarding task identifier"
    )
    icon: Optional[str] = Field(default=None, description="Emoji icon for playbook")
    required_tools: List[str] = Field(
        default_factory=list,
        description="Simple tool list (legacy format)",
    )
    tool_dependencies: List[ToolDependency] = Field(
        default_factory=list,
        description="Detailed tool dependency declarations",
    )
    background: bool = Field(
        default=False,
        description="Whether this playbook is a background routine",
    )
    optional_tools: List[str] = Field(
        default_factory=list,
        description="Optional tools",
    )
    kind: PlaybookKind = Field(
        default=PlaybookKind.USER_WORKFLOW,
        description="Playbook type: user_workflow or system_tool",
    )
    interaction_mode: List[InteractionMode] = Field(
        default_factory=lambda: [InteractionMode.CONVERSATIONAL],
        description="How this playbook interacts with users",
    )
    visible_in: List[VisibleIn] = Field(
        default_factory=lambda: [VisibleIn.WORKSPACE_PLAYBOOK_MENU],
        description="Where this playbook should be visible in UI",
    )
    scope: Optional[Dict[str, Any]] = Field(
        default_factory=lambda: {"visibility": "system", "editable": False},
        description="Legacy scope configuration.",
    )
    owner: Optional[Dict[str, Any]] = Field(
        default_factory=lambda: {"type": "system"},
        description="Legacy owner information.",
    )
    owner_type: PlaybookOwnerType = Field(
        default=PlaybookOwnerType.USER,
        description="Ownership type",
    )
    owner_id: str = Field(
        default="default_user",
        description="Owner ID",
    )
    visibility: PlaybookVisibility = Field(
        default=PlaybookVisibility.WORKSPACE_SHARED,
        description="Visibility level",
    )
    capability_tags: List[str] = Field(
        default_factory=list,
        description="Capability tags for filtering",
    )
    project_types: Optional[List[str]] = Field(
        None,
        description="Applicable project types",
    )
    allowed_tools: Optional[List[str]] = Field(
        None,
        description="Allowed tools/connectors whitelist",
    )
    shared_with_workspaces: List[str] = Field(
        default_factory=list,
        description="Workspace IDs this playbook is shared with",
    )
    runtime_handler: str = Field(
        default="local_llm",
        description="Runtime handler: local_llm, remote_crs, custom",
    )
    runtime_tier: Optional[str] = Field(
        None, description="Runtime tier: local, cloud_recommended, cloud_only"
    )
    runtime: Optional[Dict[str, Any]] = Field(
        None, description="Runtime configuration for cloud execution"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    def get_scope_level(self) -> Optional[str]:
        """Get scope level as string."""
        if not self.scope:
            return None
        return self.scope.get("visibility") or self.scope.get("scope")

    def is_template(self) -> bool:
        """Check if this playbook is a template (shared)."""
        return self.get_scope_level() in ("system", "tenant", "profile")

    def is_instance(self) -> bool:
        """Check if this playbook is a workspace-scoped instance."""
        return self.get_scope_level() == "workspace"

    def can_edit_sop(self) -> bool:
        """Template playbooks cannot edit SOP directly."""
        return self.is_instance()


class Playbook(BaseModel):
    """Complete Playbook definition."""

    metadata: PlaybookMetadata
    sop_content: str = Field(default="", description="SOP content in Markdown")
    user_notes: Optional[str] = Field(
        None, description="User's personal notes about this playbook"
    )
    agent_roster: Optional[Dict[str, AgentDefinition]] = Field(
        None, description="Agent roster for this playbook"
    )

    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})


class PlaybookRun(BaseModel):
    """
    playbook.run = playbook.md + playbook.json.

    Complete playbook definition with human-readable and machine-readable specs.
    """

    playbook: Playbook = Field(
        ..., description="Playbook.md definition (human-readable)"
    )
    playbook_json: Optional[PlaybookJson] = Field(
        None, description="Playbook.json definition (machine-readable)"
    )

    def has_json(self) -> bool:
        """Check if playbook.json exists."""
        return self.playbook_json is not None

    def get_execution_mode(self) -> str:
        """Determine execution mode from available components."""
        if self.has_json():
            return "workflow"
        return "conversation"

    def get_execution_profile(self) -> "ExecutionProfile":
        """Get execution profile for this playbook."""
        from backend.app.core.runtime_port import ExecutionProfile

        if self.playbook_json and self.playbook_json.execution_profile:
            return ExecutionProfile(**self.playbook_json.execution_profile)

        return ExecutionProfile(
            execution_mode="simple",
            supports_resume=False,
            requires_human_approval=False,
            side_effect_level="none",
        )

    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})

