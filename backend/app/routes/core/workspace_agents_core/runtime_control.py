from typing import Any, Dict, Optional

from fastapi import HTTPException

from backend.app.models.workspace import Workspace
from backend.app.services.external_agents.core.base_adapter import RuntimeExecRequest
from backend.app.services.external_agents.core.registry import get_runtime_registry


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
    if control_action == "codex_login":
        max_duration_seconds = 300
    elif control_action == "codex_probe":
        max_duration_seconds = 120
    else:
        max_duration_seconds = 45
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
