from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi import Path as PathParam

from backend.app.models.workspace import Workspace
from backend.app.routes.workspace_dependencies import get_workspace

from .account_home_paths import (
    _ensure_codex_account_home_dirs,
    _has_codex_account_home_target,
)
from .account_home_probe import (
    _codex_identity_from_result,
    _persist_codex_account_home_login_metadata,
    _validate_codex_account_home_login_identity,
)
from .account_home_targets import _resolve_codex_account_home_inputs
from .runtime_control import (
    _execute_agent_control,
    _raise_agent_control_failure,
    _resolve_agent_availability,
)
from .schemas import WorkspaceAgentAuthActionRequest, WorkspaceAgentAuthActionResponse

router = APIRouter()


@router.post("/{agent_id}/login", response_model=WorkspaceAgentAuthActionResponse)
async def login_workspace_agent(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    agent_id: str = PathParam(..., description="Agent ID"),
    payload: Optional[WorkspaceAgentAuthActionRequest] = None,
    workspace: Workspace = Depends(get_workspace),
):
    _, detail = await _resolve_agent_availability(workspace_id, agent_id)
    if not detail.get("available"):
        raise HTTPException(
            status_code=409,
            detail=f"{agent_id} is not connected for workspace {workspace_id}",
        )

    if agent_id != "codex_cli":
        raise HTTPException(
            status_code=400,
            detail=f"Interactive login is not implemented for {agent_id}",
        )

    if not _has_codex_account_home_target(payload):
        raise HTTPException(
            status_code=400,
            detail=(
                "Codex account-home login requires runtime_id, account_key, "
                "login_email, or codex_home. No-target login is disabled."
            ),
        )

    control_inputs = _resolve_codex_account_home_inputs(payload)
    codex_home = str(control_inputs.get("codex_home") or "").strip()
    if codex_home:
        _ensure_codex_account_home_dirs(codex_home)
    result = await _execute_agent_control(
        workspace,
        agent_id,
        "codex_login",
        inputs=control_inputs,
    )
    if not result.success:
        _raise_agent_control_failure("login", result)
    observed_identity = _codex_identity_from_result(result)
    _validate_codex_account_home_login_identity(
        control_inputs,
        observed_identity,
    )
    _persist_codex_account_home_login_metadata(
        control_inputs,
        observed_identity,
    )
    return WorkspaceAgentAuthActionResponse(
        agent_id=agent_id,
        workspace_id=workspace_id,
        action="login",
        success=result.success,
        output=result.output or "",
        error=result.error,
        note=(
            "If Codex opens a browser or device-code flow on the host, finish it there "
            "and then refresh auth status. When an account-home target is provided, "
            "the login is isolated to that CODEX_HOME."
        ),
    )


@router.post("/{agent_id}/logout", response_model=WorkspaceAgentAuthActionResponse)
async def logout_workspace_agent(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    agent_id: str = PathParam(..., description="Agent ID"),
    payload: Optional[WorkspaceAgentAuthActionRequest] = None,
    workspace: Workspace = Depends(get_workspace),
):
    _, detail = await _resolve_agent_availability(workspace_id, agent_id)
    if not detail.get("available"):
        raise HTTPException(
            status_code=409,
            detail=f"{agent_id} is not connected for workspace {workspace_id}",
        )

    if agent_id != "codex_cli":
        raise HTTPException(
            status_code=400,
            detail=f"Logout is not implemented for {agent_id}",
        )

    if not _has_codex_account_home_target(payload):
        raise HTTPException(
            status_code=400,
            detail=(
                "Codex account-home logout requires runtime_id, account_key, "
                "login_email, or codex_home. No-target logout is disabled."
            ),
        )

    control_inputs = _resolve_codex_account_home_inputs(payload)
    result = await _execute_agent_control(
        workspace,
        agent_id,
        "codex_logout",
        inputs=control_inputs,
    )
    if not result.success:
        _raise_agent_control_failure("logout", result)
    return WorkspaceAgentAuthActionResponse(
        agent_id=agent_id,
        workspace_id=workspace_id,
        action="logout",
        success=result.success,
        output=result.output or "",
        error=result.error,
        note="Codex host session logout was executed on the connected runtime surface.",
    )
