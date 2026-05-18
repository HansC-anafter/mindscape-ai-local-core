from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class WorkspaceAgentInfo(BaseModel):
    """Agent info scoped to a specific workspace."""

    id: str
    name: str
    description: str
    status: str  # 'available', 'unavailable', 'error'
    version: str
    risk_level: str
    cli_command: Optional[str] = None
    transport: Optional[str] = None
    reason: Optional[str] = None


class WorkspaceAgentListResponse(BaseModel):
    """Response for workspace-scoped agent listing."""

    agents: List[WorkspaceAgentInfo]
    total: int
    workspace_id: str
    bridge_script_path: Optional[str] = None


class WorkspaceAgentAuthStatus(BaseModel):
    agent_id: str
    workspace_id: str
    available: bool
    transport: Optional[str] = None
    reason: Optional[str] = None
    mode: str
    status: str
    note: Optional[str] = None
    output: Optional[str] = None
    error: Optional[str] = None
    login_supported: bool = False
    logout_supported: bool = False
    manual_command: Optional[str] = None


class WorkspaceAgentAuthActionResponse(BaseModel):
    agent_id: str
    workspace_id: str
    action: str
    success: bool
    output: str = ""
    error: Optional[str] = None
    note: Optional[str] = None


class WorkspaceAgentAuthActionRequest(BaseModel):
    runtime_id: Optional[str] = None
    login_email: Optional[str] = None
    account_key: Optional[str] = None
    codex_home: Optional[str] = None


class CodexAccountHomeCreateRequest(BaseModel):
    codex_home: Optional[str] = None


class CodexAccountHomeTarget(BaseModel):
    runtime_id: str
    login_email: Optional[str] = None
    account_key: Optional[str] = None
    account_scope_type: Optional[str] = None
    account_scope_label: Optional[str] = None
    account_scope_role: Optional[str] = None
    account_plan_type: Optional[str] = None
    account_organization_id: Optional[str] = None
    account_organization_title: Optional[str] = None
    account_organization_count: Optional[int] = None
    codex_home: str
    auth_json_path: Optional[str] = None
    auth_mtime_ns: Optional[str] = None
    auth_size: Optional[str] = None
    has_access: bool = False
    has_refresh: bool = False
    probe_state: Optional[str] = None
    last_probe_error_code: Optional[str] = None
    last_probe_success_at: Optional[str] = None
    cooldown_until: Optional[str] = None
    last_error_code: Optional[str] = None


class CodexAccountHomeTargetsResponse(BaseModel):
    agent_id: str
    workspace_id: str
    targets: List[CodexAccountHomeTarget]
