"""
Workspace-scoped Agent Availability API.

Returns per-workspace agent availability instead of global status.
This prevents the UI from showing "Connected (WS)" when the connection
belongs to a different workspace.
"""

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi import Path as PathParam
from pydantic import BaseModel

from backend.app.services.external_agents.core.registry import get_runtime_registry
from backend.app.services.external_agents.core.base_adapter import RuntimeExecRequest
from backend.app.routes.workspace_dependencies import get_workspace
from backend.app.models.workspace import Workspace

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/agents",
    tags=["workspace-agents"],
)


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


def _account_home_env(codex_home: str) -> Dict[str, str]:
    home = str(codex_home or "").strip()
    if not home:
        return {}
    return {
        "CODEX_HOME": home,
        "HOME": home,
        "XDG_CONFIG_HOME": str(Path(home) / ".config"),
        "XDG_DATA_HOME": str(Path(home) / ".local" / "share"),
        "XDG_STATE_HOME": str(Path(home) / ".local" / "state"),
    }


def _has_codex_account_home_target(
    payload: Optional[WorkspaceAgentAuthActionRequest],
) -> bool:
    if payload is None:
        return False
    return any(
        str(getattr(payload, key, None) or "").strip()
        for key in ("runtime_id", "login_email", "account_key", "codex_home")
    )


def _iso_value(value: Any) -> Optional[str]:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    text = str(value).strip()
    return text or None


def _list_codex_account_home_targets() -> List[CodexAccountHomeTarget]:
    from backend.app.services.codex_account_home_auth_source_service import (
        CodexAccountHomeAuthSourceService,
    )
    from backend.app.services.codex_pool_health import (
        read_health_metadata,
        read_probe_metadata,
    )
    from backend.app.services.codex_pool_service import CODEX_POOL_GROUP, CodexPoolService

    auth_sources = CodexAccountHomeAuthSourceService()
    service = CodexPoolService()
    db = service._get_db()
    RuntimeEnvironment = service._get_model()
    try:
        runtimes = (
            db.query(RuntimeEnvironment)
            .filter(
                RuntimeEnvironment.pool_group == CODEX_POOL_GROUP,
                RuntimeEnvironment.pool_enabled.is_(True),
                RuntimeEnvironment.auth_type.in_(("host_session", "none")),
            )
            .all()
        )
        targets: List[CodexAccountHomeTarget] = []
        changed = False
        for runtime in runtimes:
            auth_type = str(getattr(runtime, "auth_type", "") or "")
            metadata = dict(getattr(runtime, "extra_metadata", None) or {})
            health = read_health_metadata(metadata, auth_type=auth_type)
            if str(health.get("seed_kind") or "").strip().lower() != "account_home":
                continue
            codex_home = str(
                metadata.get("CODEX_HOME")
                or metadata.get("codex_home")
                or metadata.get("host_session_home")
                or ""
            ).strip()
            if not codex_home:
                continue

            auth_metadata = auth_sources.metadata_for_codex_home(
                codex_home,
                metadata=metadata,
            )
            if auth_metadata:
                metadata.update(auth_metadata)
                runtime.extra_metadata = metadata
                changed = True
            identity_details = auth_sources.identity_details_for_codex_home(codex_home)
            if identity_details:
                metadata.update(identity_details)
                runtime.extra_metadata = metadata
                changed = True

            probe = read_probe_metadata(metadata)
            targets.append(
                CodexAccountHomeTarget(
                    runtime_id=str(getattr(runtime, "id", "") or ""),
                    login_email=str(metadata.get("login_email") or "").strip().lower()
                    or None,
                    account_key=str(metadata.get("account_key") or "").strip()
                    or None,
                    account_scope_type=str(metadata.get("account_scope_type") or "").strip()
                    or None,
                    account_scope_label=str(metadata.get("account_scope_label") or "").strip()
                    or None,
                    account_scope_role=str(metadata.get("account_scope_role") or "").strip()
                    or None,
                    account_plan_type=str(metadata.get("account_plan_type") or "").strip()
                    or None,
                    account_organization_id=str(
                        metadata.get("account_organization_id") or ""
                    ).strip()
                    or None,
                    account_organization_title=str(
                        metadata.get("account_organization_title") or ""
                    ).strip()
                    or None,
                    account_organization_count=metadata.get("account_organization_count"),
                    codex_home=codex_home,
                    auth_json_path=str(metadata.get("auth_source_path") or "").strip()
                    or None,
                    auth_mtime_ns=str(
                        metadata.get("auth_mtime_ns")
                        or metadata.get("codex_auth_mtime_ns")
                        or ""
                    ).strip()
                    or None,
                    auth_size=str(
                        metadata.get("auth_size") or metadata.get("codex_auth_size") or ""
                    ).strip()
                    or None,
                    has_access=bool(metadata.get("auth_source_has_access")),
                    has_refresh=bool(metadata.get("auth_source_has_refresh")),
                    probe_state=str(probe.get("probe_state") or "").strip()
                    or None,
                    last_probe_error_code=probe.get("last_probe_error_code"),
                    last_probe_success_at=probe.get("last_probe_success_at"),
                    cooldown_until=_iso_value(getattr(runtime, "cooldown_until", None)),
                    last_error_code=str(getattr(runtime, "last_error_code", "") or "").strip()
                    or None,
                )
            )
        if changed:
            db.commit()
        else:
            db.rollback()
        return sorted(
            targets,
            key=lambda target: (
                target.login_email or "",
                target.account_key or "",
                target.runtime_id,
            ),
        )
    finally:
        db.close()


def _resolve_codex_account_home_inputs(
    payload: Optional[WorkspaceAgentAuthActionRequest],
) -> Dict[str, Any]:
    if payload is None:
        return {}

    runtime_id = str(payload.runtime_id or "").strip()
    login_email = str(payload.login_email or "").strip().lower()
    account_key = str(payload.account_key or "").strip()
    codex_home = str(payload.codex_home or "").strip()
    if codex_home and not any((runtime_id, login_email, account_key)):
        return {
            "codex_home": codex_home,
            "expected_codex_home": codex_home,
            "env": _account_home_env(codex_home),
        }
    if not any((runtime_id, login_email, account_key)):
        return {}

    from backend.app.services.codex_pool_health import read_health_metadata
    from backend.app.services.codex_pool_service import CODEX_POOL_GROUP, CodexPoolService

    db = None
    try:
        service = CodexPoolService()
        db = service._get_db()
        RuntimeEnvironment = service._get_model()
        query = db.query(RuntimeEnvironment).filter(
            RuntimeEnvironment.pool_group == CODEX_POOL_GROUP,
            RuntimeEnvironment.pool_enabled.is_(True),
            RuntimeEnvironment.auth_type.in_(("host_session", "none")),
        )
        if runtime_id:
            query = query.filter(RuntimeEnvironment.id == runtime_id)
        candidates = []
        for runtime in query.all():
            metadata = dict(getattr(runtime, "extra_metadata", None) or {})
            health = read_health_metadata(
                metadata,
                auth_type=str(getattr(runtime, "auth_type", "") or ""),
            )
            if str(health.get("seed_kind") or "").strip().lower() != "account_home":
                continue
            if login_email and str(metadata.get("login_email") or "").strip().lower() != login_email:
                continue
            if account_key and str(metadata.get("account_key") or "").strip() != account_key:
                continue
            if codex_home:
                runtime_home = str(
                    metadata.get("CODEX_HOME") or metadata.get("codex_home") or ""
                ).strip()
                if runtime_home != codex_home:
                    continue
            candidates.append((runtime, metadata))
    finally:
        db.close()

    if not candidates:
        raise HTTPException(status_code=404, detail="No matching Codex account-home runtime")
    if len(candidates) > 1:
        raise HTTPException(
            status_code=409,
            detail=(
                "Multiple Codex account-home runtimes match; provide runtime_id "
                "or account_key to disambiguate"
            ),
        )

    runtime, metadata = candidates[0]
    codex_home = str(metadata.get("CODEX_HOME") or metadata.get("codex_home") or "").strip()
    if not codex_home:
        raise HTTPException(status_code=409, detail="Matched runtime has no CODEX_HOME")
    return {
        "runtime_id": str(getattr(runtime, "id", "") or ""),
        "login_email": str(metadata.get("login_email") or "").strip().lower(),
        "account_key": str(metadata.get("account_key") or "").strip(),
        "codex_home": codex_home,
        "expected_login_email": login_email
        or str(metadata.get("login_email") or "").strip().lower(),
        "expected_account_key": account_key
        or str(metadata.get("account_key") or "").strip(),
        "expected_codex_home": codex_home,
        "env": _account_home_env(codex_home),
    }


def _codex_identity_from_result(result: Any) -> Dict[str, Any]:
    metadata = getattr(result, "agent_metadata", None)
    if not isinstance(metadata, dict):
        return {}
    identity = metadata.get("codex_account_identity")
    if isinstance(identity, dict):
        return dict(identity)
    dispatch_metadata = metadata.get("dispatch_metadata")
    if isinstance(dispatch_metadata, dict):
        identity = dispatch_metadata.get("codex_account_identity")
        if isinstance(identity, dict):
            return dict(identity)
    return {}


def _persist_codex_account_home_login_metadata(
    inputs: Dict[str, Any],
    observed_identity: Dict[str, Any],
) -> None:
    runtime_id = str(inputs.get("runtime_id") or "").strip()
    account_key = str(inputs.get("expected_account_key") or inputs.get("account_key") or "").strip()
    codex_home = str(inputs.get("expected_codex_home") or inputs.get("codex_home") or "").strip()
    if not any((runtime_id, account_key, codex_home)):
        return

    from backend.app.services.codex_pool_health import read_health_metadata
    from backend.app.services.codex_pool_service import CODEX_POOL_GROUP, CodexPoolService

    db = None
    try:
        service = CodexPoolService()
        db = service._get_db()
        RuntimeEnvironment = service._get_model()
        query = db.query(RuntimeEnvironment).filter(
            RuntimeEnvironment.pool_group == CODEX_POOL_GROUP,
            RuntimeEnvironment.pool_enabled.is_(True),
            RuntimeEnvironment.auth_type.in_(("host_session", "none")),
        )
        if runtime_id:
            query = query.filter(RuntimeEnvironment.id == runtime_id)
        candidates = []
        for runtime in query.all():
            metadata = dict(getattr(runtime, "extra_metadata", None) or {})
            health = read_health_metadata(
                metadata,
                auth_type=str(getattr(runtime, "auth_type", "") or ""),
            )
            if str(health.get("seed_kind") or "").strip().lower() != "account_home":
                continue
            runtime_home = str(
                metadata.get("CODEX_HOME")
                or metadata.get("codex_home")
                or metadata.get("host_session_home")
                or ""
            ).strip()
            runtime_account_key = str(metadata.get("account_key") or "").strip()
            if account_key and runtime_account_key != account_key:
                continue
            if codex_home and runtime_home != codex_home:
                continue
            candidates.append((runtime, metadata))

        if len(candidates) != 1:
            db.rollback()
            return

        runtime, metadata = candidates[0]
        previous_auth_mtime = str(
            metadata.get("auth_mtime_ns")
            or metadata.get("codex_auth_mtime_ns")
            or ""
        )
        for key, value in observed_identity.items():
            if value is not None and key != "identity_error":
                metadata[key] = value
        next_auth_mtime = str(
            metadata.get("auth_mtime_ns")
            or metadata.get("codex_auth_mtime_ns")
            or ""
        )
        metadata["last_account_home_login_at"] = datetime.now(
            timezone.utc
        ).isoformat()
        metadata["last_account_home_login_state"] = "succeeded"
        if previous_auth_mtime and next_auth_mtime and previous_auth_mtime != next_auth_mtime:
            metadata["probe_state"] = "unknown"
            metadata["last_probe_error_code"] = None
            metadata["last_probe_runtime_returncode"] = None
        runtime.extra_metadata = metadata
        db.commit()
    except Exception:
        if db is not None:
            db.rollback()
        logger.exception("Failed to persist Codex account-home login metadata")
    finally:
        if db is not None:
            db.close()


def _validate_codex_account_home_login_identity(
    inputs: Dict[str, Any],
    observed_identity: Optional[Dict[str, Any]] = None,
) -> None:
    codex_home = str(inputs.get("codex_home") or "").strip()
    if not codex_home:
        return
    expected_account_key = str(inputs.get("expected_account_key") or "").strip()
    expected_login_email = str(inputs.get("expected_login_email") or "").strip().lower()
    if not expected_account_key and not expected_login_email:
        return

    observed = observed_identity if isinstance(observed_identity, dict) else {}
    if observed:
        actual_account_key = str(observed.get("account_key") or "").strip()
        actual_login_email = str(observed.get("login_email") or "").strip().lower()
        if expected_account_key and actual_account_key == expected_account_key:
            return
        if not expected_account_key and expected_login_email and actual_login_email == expected_login_email:
            return
        if actual_account_key or actual_login_email:
            if expected_account_key and actual_account_key != expected_account_key:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Codex account-home login wrote a different account identity "
                        f"than the selected target: expected account_key={expected_account_key}, "
                        f"actual account_key={actual_account_key or 'unknown'}, "
                        f"actual login_email={actual_login_email or 'unknown'}."
                    ),
                )
            if expected_login_email and actual_login_email != expected_login_email:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Codex account-home login wrote a different login email "
                        f"than the selected target: expected login_email={expected_login_email}, "
                        f"actual login_email={actual_login_email or 'unknown'}."
                    ),
                )

    from backend.app.services.codex_account_home_auth_source_service import (
        CodexAccountHomeAuthSourceService,
    )

    import time

    actual_account_key = ""
    actual_login_email = ""
    deadline = time.monotonic() + 5.0
    while True:
        actual = CodexAccountHomeAuthSourceService.metadata_for_codex_home(codex_home)
        actual_account_key = str(actual.get("account_key") or "").strip()
        actual_login_email = str(actual.get("login_email") or "").strip().lower()
        if expected_account_key and actual_account_key == expected_account_key:
            return
        if not expected_account_key and expected_login_email and actual_login_email == expected_login_email:
            return
        if actual_account_key or actual_login_email or time.monotonic() >= deadline:
            break
        time.sleep(0.25)

    if expected_account_key and actual_account_key != expected_account_key:
        raise HTTPException(
            status_code=409,
            detail=(
                "Codex account-home login wrote a different account identity "
                f"than the selected target: expected account_key={expected_account_key}, "
                f"actual account_key={actual_account_key or 'unknown'}, "
                f"actual login_email={actual_login_email or 'unknown'}."
            ),
        )
    if expected_login_email and actual_login_email != expected_login_email:
        raise HTTPException(
            status_code=409,
            detail=(
                "Codex account-home login wrote a different login email "
                f"than the selected target: expected login_email={expected_login_email}, "
                f"actual login_email={actual_login_email or 'unknown'}."
            ),
        )


async def _resolve_agent_availability(
    workspace_id: str,
    agent_id: str,
) -> tuple[Any, Dict[str, Any]]:
    registry = get_runtime_registry()
    registry.discover_agents()

    adapter = registry.get_adapter(agent_id)
    if not adapter:
        raise HTTPException(status_code=404, detail=f"Unknown agent: {agent_id}")

    transport = None
    reason = None
    if hasattr(adapter, "get_availability_detail"):
        detail = adapter.get_availability_detail(workspace_id=workspace_id)
        available = bool(detail.get("available"))
        transport = detail.get("transport")
        reason = detail.get("reason")
    else:
        available = bool(await adapter.is_available(workspace_id=workspace_id))
        detail = {"available": available}

    detail.update({"transport": transport, "reason": reason})
    return adapter, detail


async def _execute_agent_control(
    workspace: Workspace,
    agent_id: str,
    control_action: str,
    inputs: Optional[Dict[str, Any]] = None,
):
    registry = get_runtime_registry()
    registry.discover_agents()
    adapter = registry.get_adapter(agent_id)
    if not adapter:
        raise HTTPException(status_code=404, detail=f"Unknown agent: {agent_id}")

    sandbox_path = (
        getattr(workspace, "storage_base_path", None)
        or getattr(workspace, "workspace_path", None)
        or "/tmp"
    )
    max_duration_seconds = 300 if control_action == "codex_login" else 45
    request = RuntimeExecRequest(
        task=f"__mindscape_cli_control__:{control_action}",
        sandbox_path=str(sandbox_path),
        workspace_id=workspace.id,
        auth_workspace_id=workspace.id,
        source_workspace_id=workspace.id,
        max_duration_seconds=max_duration_seconds,
        agent_config={
            "control_action": control_action,
            "thread_id": "runtime-auth-settings",
            "conversation_context": "Runtime auth control command",
            "inputs": dict(inputs or {}),
        },
    )
    return await adapter.execute(request)


def _raise_agent_control_failure(action: str, result: Any) -> None:
    message = str(
        getattr(result, "error", None)
        or getattr(result, "output", None)
        or f"Codex {action} did not complete"
    ).strip()
    lower = message.lower()
    status_code = 504 if any(token in lower for token in ("timeout", "timed out", "stalled")) else 409
    raise HTTPException(status_code=status_code, detail=message)


def _classify_codex_status(success: bool, output: str, error: Optional[str]) -> str:
    if success:
        return "authenticated"
    lower = f"{output} {error or ''}".lower()
    auth_markers = (
        "not logged",
        "login",
        "authenticate",
        "auth",
        "credential",
    )
    if any(marker in lower for marker in auth_markers):
        return "not_authenticated"
    return "error"


@router.get("", response_model=WorkspaceAgentListResponse)
async def list_workspace_agents(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    workspace: Workspace = Depends(get_workspace),
):
    """
    List agents with per-workspace availability.

    Unlike /api/v1/agents (global), this checks whether each agent
    has an active connection for the specified workspace.
    """
    try:
        registry = get_runtime_registry()
        registry.discover_agents()

        agents = []
        for agent_name, manifest in registry.get_all_manifests().items():
            adapter = registry.get_adapter(agent_name)

            transport = None
            reason = None
            if adapter and hasattr(adapter, "get_availability_detail"):
                detail = adapter.get_availability_detail(
                    workspace_id=workspace_id,
                )
                is_available = detail["available"]
                transport = detail.get("transport")
                reason = detail.get("reason")
            elif adapter:
                is_available = await adapter.is_available(
                    workspace_id=workspace_id,
                )
            else:
                is_available = False

            agents.append(
                WorkspaceAgentInfo(
                    id=agent_name,
                    name=manifest.name,
                    description=manifest.description,
                    status="available" if is_available else "unavailable",
                    version=manifest.version,
                    risk_level=manifest.risk_level,
                    cli_command=manifest.cli_command,
                    transport=transport,
                    reason=reason,
                )
            )

        host_root = os.environ.get("HOST_PROJECT_PATH")
        if host_root:
            bridge_path = Path(host_root) / "scripts" / "start_cli_bridge.sh"
            script_path = str(bridge_path)
        else:
            project_root = Path(__file__).resolve().parents[4]
            bridge_path = project_root / "scripts" / "start_cli_bridge.sh"
            script_path = str(bridge_path) if bridge_path.exists() else None

        return WorkspaceAgentListResponse(
            agents=agents,
            total=len(agents),
            workspace_id=workspace_id,
            bridge_script_path=script_path,
        )

    except Exception as e:
        logger.error(
            f"[WorkspaceAgentsAPI] Failed to list agents for " f"{workspace_id}: {e}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{agent_id}/auth-status", response_model=WorkspaceAgentAuthStatus)
async def get_workspace_agent_auth_status(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    agent_id: str = PathParam(..., description="Agent ID"),
    workspace: Workspace = Depends(get_workspace),
):
    _, detail = await _resolve_agent_availability(workspace_id, agent_id)
    available = bool(detail.get("available"))
    transport = detail.get("transport")
    reason = detail.get("reason")

    if agent_id == "codex_cli":
        if not available:
            return WorkspaceAgentAuthStatus(
                agent_id=agent_id,
                workspace_id=workspace_id,
                available=False,
                transport=transport,
                reason=reason,
                mode="host_session",
                status="unavailable",
                note="Codex host session can only be inspected when the codex_cli surface is connected for this workspace.",
                login_supported=True,
                logout_supported=True,
                manual_command="codex login",
            )

        result = await _execute_agent_control(workspace, agent_id, "codex_login_status")
        output = result.output or ""
        status = _classify_codex_status(result.success, output, result.error)
        return WorkspaceAgentAuthStatus(
            agent_id=agent_id,
            workspace_id=workspace_id,
            available=True,
            transport=transport,
            reason=reason,
            mode="host_session",
            status=status,
            output=output or None,
            error=result.error,
            note="This checks the real host Codex CLI session, not the API-key setting.",
            login_supported=True,
            logout_supported=True,
            manual_command="codex login",
        )

    if agent_id == "claude_code_cli":
        note = (
            "Claude Code host-token sessions are managed directly on the host with "
            "`claude setup-token`. The backend cannot inspect the token state "
            "without a dedicated CLI status command."
        )
        return WorkspaceAgentAuthStatus(
            agent_id=agent_id,
            workspace_id=workspace_id,
            available=available,
            transport=transport,
            reason=reason,
            mode="host_token",
            status="manual_required" if available else "unavailable",
            note=note,
            login_supported=False,
            logout_supported=False,
            manual_command="claude setup-token",
        )

    raise HTTPException(status_code=400, detail=f"Auth status is not implemented for {agent_id}")


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
