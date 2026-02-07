"""
Doer Workspace Configuration Model

Defines the sandbox and execution configuration for Doer workspaces,
which are designed for external agent execution with controlled boundaries.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field


class DoerWorkspaceConfig(BaseModel):
    """
    Doer Workspace sandbox configuration.

    Controls the "three dials" of sandbox security:
    1. Filesystem scope - What paths the agent can read/write
    2. Network allowlist - What hosts the agent can access
    3. Tool acquire/promote policy - How the agent can install new tools
    """

    # ==================== Dial 1: Filesystem Scope ====================
    filesystem_scope: List[str] = Field(
        default=["workspace/sandbox/*"],
        description="Allowed filesystem paths (glob patterns). "
        "Agent can only read/write within these paths.",
    )
    filesystem_readonly: List[str] = Field(
        default=["workspace/artifacts/*"],
        description="Read-only filesystem paths (agent can read but not write)",
    )

    # ==================== Dial 2: Network Allowlist ====================
    network_allowlist: List[str] = Field(
        default=["github.com", "npmjs.com", "pypi.org", "raw.githubusercontent.com"],
        description="Allowed network hosts (egress allowlist). "
        "Agent can only make requests to these hosts.",
    )
    network_denylist: List[str] = Field(
        default=["*.internal", "localhost", "127.0.0.1", "169.254.*"],
        description="Blocked network hosts (takes precedence over allowlist)",
    )

    # ==================== Dial 3: Tool Acquire/Promote Policy ====================
    tool_acquire_policy: Literal["free", "restricted", "blocked"] = Field(
        default="free",
        description="Tool acquisition policy: "
        "free = agent can explore/download freely, "
        "restricted = only from approved sources, "
        "blocked = no new tool acquisition",
    )
    tool_promote_policy: Literal["auto", "decision_card", "blocked"] = Field(
        default="decision_card",
        description="Tool promotion policy: "
        "auto = auto-approve low-risk tools, "
        "decision_card = require user approval, "
        "blocked = no tool installation",
    )
    approved_tool_sources: List[str] = Field(
        default=["github.com/openclaw/*", "github.com/paul-gauthier/*"],
        description="Approved tool sources for 'restricted' acquire policy",
    )

    # ==================== Execution Limits ====================
    max_execution_time_seconds: int = Field(
        default=300,
        ge=30,
        le=3600,
        description="Maximum execution time per task (30s - 1hr, default 5min)",
    )
    max_iterations: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum agent iterations per task",
    )
    max_file_writes_per_task: int = Field(
        default=50,
        ge=1,
        le=500,
        description="Maximum file writes per task (rate limiting)",
    )

    # ==================== Host Access (Break-glass) ====================
    allow_host_access: bool = Field(
        default=False,
        description="Whether to allow host system access (requires break-glass)",
    )
    host_adaptor_operations: List[str] = Field(
        default=[],
        description="Allowed host adaptor operations when break-glass is granted",
    )

    # ==================== Quarantine Configuration ====================
    quarantine_path: str = Field(
        default=".quarantine",
        description="Relative path for downloaded but not-yet-promoted tools",
    )
    auto_cleanup_quarantine_hours: int = Field(
        default=24,
        description="Auto-cleanup quarantine after N hours (0 = no cleanup)",
    )

    # ==================== Metadata ====================
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="Config creation timestamp"
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow, description="Last update timestamp"
    )
    updated_by: Optional[str] = Field(None, description="User ID who last updated")


class DoerWorkspaceConfigUpdate(BaseModel):
    """Request to update Doer workspace configuration"""

    filesystem_scope: Optional[List[str]] = None
    filesystem_readonly: Optional[List[str]] = None
    network_allowlist: Optional[List[str]] = None
    network_denylist: Optional[List[str]] = None
    tool_acquire_policy: Optional[Literal["free", "restricted", "blocked"]] = None
    tool_promote_policy: Optional[Literal["auto", "decision_card", "blocked"]] = None
    approved_tool_sources: Optional[List[str]] = None
    max_execution_time_seconds: Optional[int] = Field(None, ge=30, le=3600)
    max_iterations: Optional[int] = Field(None, ge=1, le=100)
    max_file_writes_per_task: Optional[int] = Field(None, ge=1, le=500)
    allow_host_access: Optional[bool] = None
    host_adaptor_operations: Optional[List[str]] = None
    quarantine_path: Optional[str] = None
    auto_cleanup_quarantine_hours: Optional[int] = None


# ==================== Presets ====================

DOER_CONFIG_PRESETS: Dict[str, DoerWorkspaceConfig] = {
    "conservative": DoerWorkspaceConfig(
        filesystem_scope=["workspace/sandbox/*"],
        network_allowlist=["github.com", "npmjs.com"],
        tool_acquire_policy="restricted",
        tool_promote_policy="decision_card",
        max_execution_time_seconds=120,
        max_iterations=5,
    ),
    "balanced": DoerWorkspaceConfig(
        filesystem_scope=["workspace/sandbox/*", "workspace/temp/*"],
        network_allowlist=[
            "github.com",
            "npmjs.com",
            "pypi.org",
            "raw.githubusercontent.com",
        ],
        tool_acquire_policy="free",
        tool_promote_policy="decision_card",
        max_execution_time_seconds=300,
        max_iterations=10,
    ),
    "permissive": DoerWorkspaceConfig(
        filesystem_scope=["workspace/*"],
        network_allowlist=["*"],
        network_denylist=["*.internal", "localhost", "127.0.0.1"],
        tool_acquire_policy="free",
        tool_promote_policy="auto",
        max_execution_time_seconds=600,
        max_iterations=20,
    ),
}


def get_default_doer_config() -> DoerWorkspaceConfig:
    """Get the default (balanced) Doer workspace configuration"""
    return DOER_CONFIG_PRESETS["balanced"].model_copy()
