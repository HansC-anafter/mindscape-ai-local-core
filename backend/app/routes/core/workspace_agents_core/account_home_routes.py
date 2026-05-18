import json
import logging
import shutil
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi import Path as PathParam

from backend.app.models.workspace import Workspace
from backend.app.routes.workspace_dependencies import get_workspace

from .account_home_paths import (
    _account_home_env,
    _ensure_codex_account_home_dirs,
    _has_codex_account_home_target,
    _is_managed_codex_account_home,
    _new_codex_account_home_path,
    _normalize_codex_home_path,
)
from .account_home_probe import _persist_codex_account_home_probe_result
from .account_home_targets import (
    _list_codex_account_home_targets,
    _resolve_codex_account_home_inputs,
)
from .runtime_control import (
    _execute_agent_control,
    _raise_agent_control_failure,
    _resolve_agent_availability,
)
from .schemas import (
    CodexAccountHomeCreateRequest,
    CodexAccountHomeTargetsResponse,
    WorkspaceAgentAuthActionRequest,
    WorkspaceAgentAuthActionResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/{agent_id}/account-homes", response_model=CodexAccountHomeTargetsResponse)
async def list_workspace_agent_account_homes(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    agent_id: str = PathParam(..., description="Agent ID"),
    workspace: Workspace = Depends(get_workspace),
):
    if agent_id != "codex_cli":
        raise HTTPException(
            status_code=400,
            detail=f"Account-home inventory is not implemented for {agent_id}",
        )
    return CodexAccountHomeTargetsResponse(
        agent_id=agent_id,
        workspace_id=workspace_id,
        targets=_list_codex_account_home_targets(),
    )


@router.post("/{agent_id}/account-homes", response_model=WorkspaceAgentAuthActionResponse)
async def create_workspace_agent_account_home(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    agent_id: str = PathParam(..., description="Agent ID"),
    payload: Optional[CodexAccountHomeCreateRequest] = None,
    workspace: Workspace = Depends(get_workspace),
):
    if agent_id != "codex_cli":
        raise HTTPException(
            status_code=400,
            detail=f"Account-home creation is not implemented for {agent_id}",
        )

    codex_home = str(getattr(payload, "codex_home", None) or "").strip()
    if not codex_home:
        codex_home = _new_codex_account_home_path()
    home_path = _ensure_codex_account_home_dirs(codex_home)

    from backend.app.routes.core.cli_token import (
        RegisterHostSessionRuntimeRequest,
        _upsert_host_session_runtime,
    )

    owner_user_id = str(getattr(workspace, "owner_user_id", "") or "").strip()
    if not owner_user_id:
        raise HTTPException(
            status_code=404,
            detail=f"Workspace owner unavailable: {workspace_id}",
        )
    metadata = _account_home_env(str(home_path))
    metadata["codex_seed_kind"] = "account_home"
    runtime = _upsert_host_session_runtime(
        owner_user_id=owner_user_id,
        request=RegisterHostSessionRuntimeRequest(
            workspace_id=workspace_id,
            surface="codex_cli",
            runtime_name=f"Codex account home {home_path.name}",
            metadata=metadata,
            pool_enabled=True,
        ),
    )
    runtime_id = str(runtime.get("runtime_id") or runtime.get("id") or "").strip()
    return WorkspaceAgentAuthActionResponse(
        agent_id=agent_id,
        workspace_id=workspace_id,
        action="create_account_home",
        success=True,
        output=json.dumps(
            {
                "runtime_id": runtime_id,
                "codex_home": str(home_path),
            },
            ensure_ascii=False,
        ),
        note="Account home created. Login will fill email and scope from OpenAI token claims.",
    )


@router.delete(
    "/{agent_id}/account-homes/{runtime_id}",
    response_model=WorkspaceAgentAuthActionResponse,
)
async def delete_workspace_agent_account_home(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    agent_id: str = PathParam(..., description="Agent ID"),
    runtime_id: str = PathParam(..., description="Runtime ID"),
    workspace: Workspace = Depends(get_workspace),
):
    if agent_id != "codex_cli":
        raise HTTPException(
            status_code=400,
            detail=f"Account-home deletion is not implemented for {agent_id}",
        )

    from backend.app.services.codex_pool_health import read_health_metadata
    from backend.app.services.codex_pool_service import CODEX_POOL_GROUP, CodexPoolService

    selected_runtime_id = str(runtime_id or "").strip()
    if not selected_runtime_id:
        raise HTTPException(status_code=400, detail="runtime_id is required.")

    service = CodexPoolService()
    db = service._get_db()
    RuntimeEnvironment = service._get_model()
    try:
        runtime = (
            db.query(RuntimeEnvironment)
            .filter(
                RuntimeEnvironment.id == selected_runtime_id,
                RuntimeEnvironment.pool_group == CODEX_POOL_GROUP,
                RuntimeEnvironment.user_id == workspace.owner_user_id,
            )
            .first()
        )
        if not runtime:
            raise HTTPException(
                status_code=404,
                detail=f"Codex account-home runtime not found: {selected_runtime_id}",
            )
        metadata = dict(getattr(runtime, "extra_metadata", None) or {})
        health = read_health_metadata(
            metadata,
            auth_type=str(getattr(runtime, "auth_type", "") or ""),
        )
        if str(health.get("seed_kind") or "").strip().lower() != "account_home":
            raise HTTPException(
                status_code=409,
                detail="Only managed Codex account-home runtimes can be deleted here.",
            )
        codex_home = str(
            metadata.get("CODEX_HOME")
            or metadata.get("codex_home")
            or metadata.get("host_session_home")
            or ""
        ).strip()
        home_path = _normalize_codex_home_path(codex_home)
        if not _is_managed_codex_account_home(home_path):
            raise HTTPException(
                status_code=409,
                detail=f"Refusing to delete unmanaged Codex account-home path: {home_path}",
            )
        host_delete_result = await _execute_agent_control(
            workspace,
            agent_id,
            "codex_account_home_delete",
            inputs={
                "runtime_id": selected_runtime_id,
                "codex_home": str(home_path),
                "env": _account_home_env(str(home_path)),
            },
        )
        if not bool(getattr(host_delete_result, "success", False)):
            _raise_agent_control_failure(
                "delete account home",
                host_delete_result,
            )
        if home_path.exists():
            if home_path.is_symlink() or not home_path.is_dir():
                raise HTTPException(
                    status_code=409,
                    detail=f"Refusing to delete unsafe Codex account-home path: {home_path}",
                )
            shutil.rmtree(home_path)
        db.delete(runtime)
        db.commit()
        return WorkspaceAgentAuthActionResponse(
            agent_id=agent_id,
            workspace_id=workspace_id,
            action="delete_account_home",
            success=True,
            output=json.dumps(
                {
                    "runtime_id": selected_runtime_id,
                    "codex_home": str(home_path),
                    "home_removed": not home_path.exists(),
                },
                ensure_ascii=False,
            ),
            note="Account home runtime deleted.",
        )
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to delete Codex account-home runtime")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete Codex account home: {exc}",
        ) from exc
    finally:
        db.close()


@router.post("/{agent_id}/account-homes/probe", response_model=WorkspaceAgentAuthActionResponse)
async def probe_workspace_agent_account_home(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    agent_id: str = PathParam(..., description="Agent ID"),
    payload: Optional[WorkspaceAgentAuthActionRequest] = None,
    workspace: Workspace = Depends(get_workspace),
):
    if agent_id != "codex_cli":
        raise HTTPException(
            status_code=400,
            detail=f"Account-home probe is not implemented for {agent_id}",
        )
    _, detail = await _resolve_agent_availability(workspace_id, agent_id)
    if not detail.get("available"):
        raise HTTPException(
            status_code=409,
            detail=f"{agent_id} is not connected for workspace {workspace_id}",
        )
    if not _has_codex_account_home_target(payload):
        raise HTTPException(
            status_code=400,
            detail=(
                "Codex account-home probe requires runtime_id, account_key, "
                "login_email, or codex_home."
            ),
        )

    control_inputs = _resolve_codex_account_home_inputs(payload)
    runtime_id = str(control_inputs.get("runtime_id") or "").strip()
    result = await _execute_agent_control(
        workspace,
        agent_id,
        "codex_probe",
        inputs=control_inputs,
    )
    persisted = _persist_codex_account_home_probe_result(runtime_id, result)
    success = bool(persisted.get("success"))
    error_text = str(
        persisted.get("error_code")
        or getattr(result, "error", None)
        or ""
    ).strip() or None
    output = json.dumps(
        {
            "runtime_id": runtime_id,
            "status": "available" if success else "failed",
            "fault_kind": persisted.get("fault_kind"),
            "error_code": persisted.get("error_code"),
            "output": getattr(result, "output", "") or "",
            "error": getattr(result, "error", None),
        },
        ensure_ascii=False,
    )
    return WorkspaceAgentAuthActionResponse(
        agent_id=agent_id,
        workspace_id=workspace_id,
        action="probe",
        success=success,
        output=output,
        error=None if success else error_text,
        note=(
            "Target-specific Codex token usability probe passed."
            if success
            else "Target-specific Codex token usability probe failed."
        ),
    )
