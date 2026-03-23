"""Remote workflow-tool routing helpers."""

import logging
import os
import uuid
from typing import Any, Callable, Dict, Optional

from backend.app.services.execution_core.clock import utc_now
from backend.app.services.execution_core.errors import RecoverableStepError
from backend.app.services.remote_execution_child_tasks import (
    ensure_remote_workflow_step_child_shell,
)

logger = logging.getLogger(__name__)


def get_cloud_connector() -> Any:
    """Best-effort access to CloudConnector without depending on route modules."""
    try:
        from backend.app.main import app

        connector = getattr(app.state, "cloud_connector", None)
        if connector is not None:
            return connector
    except Exception:
        pass

    try:
        from backend.app.services.cloud_connector.connector import CloudConnector

        return CloudConnector()
    except Exception:
        logger.debug("WorkflowOrchestrator: CloudConnector unavailable", exc_info=True)
        return None


def resolve_remote_tool_route(
    playbook_inputs: Optional[Dict[str, Any]],
    *,
    step_id: str,
    tool_id: str,
) -> Optional[Dict[str, Any]]:
    """Resolve a generic workflow-level remote tool route."""
    if not isinstance(playbook_inputs, dict):
        return None

    routes = playbook_inputs.get("_remote_tool_routes")
    if not isinstance(routes, dict):
        routes = playbook_inputs.get("remote_tool_routes")
    if not isinstance(routes, dict):
        return None

    for route_key in (step_id, tool_id):
        route = routes.get(route_key)
        if not isinstance(route, dict):
            continue
        execution_backend = str(route.get("execution_backend", "remote")).strip().lower()
        if execution_backend != "remote":
            continue

        resolved_route = dict(route)
        resolved_route.setdefault("job_type", "tool")
        resolved_route.setdefault("tool_name", tool_id)
        if not resolved_route.get("capability_code") and "." in str(
            resolved_route["tool_name"]
        ):
            resolved_route["capability_code"] = str(
                resolved_route["tool_name"]
            ).split(".", 1)[0]
        return resolved_route

    return None


def resolve_tool_model_override(
    *,
    tool_id: str,
    playbook_inputs: Optional[Dict[str, Any]],
    remote_route: Optional[Dict[str, Any]] = None,
    execution_profile: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Resolve model override for a tool execution."""
    if not (tool_id.startswith("core_llm.") or "llm" in tool_id.lower()):
        return None

    local_override = None
    if isinstance(playbook_inputs, dict):
        local_override = playbook_inputs.get("_model_override")

    if isinstance(remote_route, dict):
        explicit_override = (
            remote_route.get("model_override") or remote_route.get("_model_override")
        )
        if explicit_override:
            return str(explicit_override)

        if execution_profile:
            try:
                from backend.app.services.capability_profile_resolver import (
                    CapabilityProfileResolver,
                )

                cap_profile = execution_profile.get("reasoning", "standard")
                deployment_scope = str(
                    remote_route.get("model_deployment_scope", "cloud")
                )
                resolved_model, _variant = CapabilityProfileResolver().resolve(
                    cap_profile,
                    execution_profile=execution_profile,
                    deployment_scope=deployment_scope,
                )
                if resolved_model:
                    return str(resolved_model)
            except Exception as exc:
                logger.warning(
                    "remote deployment-scoped model resolve failed (non-fatal): %s",
                    exc,
                )

        if remote_route.get("inherit_model_override") and local_override:
            return str(local_override)
        return None

    if local_override:
        return str(local_override)
    return None


def ensure_remote_tool_child_shell(**kwargs):
    """Compatibility seam for remote child-shell creation."""
    return ensure_remote_workflow_step_child_shell(**kwargs)


async def maybe_execute_tool_via_remote_route(
    *,
    step_id: str,
    tool_id: str,
    tool_inputs: Dict[str, Any],
    playbook_inputs: Dict[str, Any],
    execution_id: Optional[str],
    workspace_id: Optional[str],
    get_cloud_connector_fn: Callable[[], Any] = get_cloud_connector,
    ensure_remote_tool_child_shell_fn: Callable[..., Any] = ensure_remote_tool_child_shell,
) -> tuple[bool, Any]:
    """Dispatch a workflow tool step to remote execution when configured."""
    route = resolve_remote_tool_route(
        playbook_inputs,
        step_id=step_id,
        tool_id=tool_id,
    )
    if not route:
        return False, None

    if str(route.get("job_type", "tool")).strip().lower() != "tool":
        raise ValueError(
            f"Unsupported remote workflow job_type for step {step_id}: "
            f"{route.get('job_type')}"
        )

    if not workspace_id:
        raise ValueError(
            f"workspace_id is required for remote tool routing on step {step_id}"
        )

    connector = get_cloud_connector_fn()
    if connector is None:
        error = "CloudConnector unavailable for remote tool routing"
        if route.get("fallback_local_on_error"):
            logger.warning(
                "WorkflowOrchestrator: %s; falling back to local tool %s",
                error,
                tool_id,
            )
            return False, None
        raise RecoverableStepError(step_id, "remote_connector_unavailable", error)

    parent_trace_id = playbook_inputs.get("trace_id") or execution_id or str(uuid.uuid4())
    child_execution_id = str(uuid.uuid4())
    tenant_id = (
        route.get("tenant_id")
        or playbook_inputs.get("tenant_id")
        or os.getenv("CLOUD_TENANT_ID")
        or getattr(connector, "tenant_id", "default")
        or "default"
    )
    site_key = route.get("site_key") or playbook_inputs.get("site_key") or tenant_id
    target_device_id = route.get("target_device_id")
    timeout_seconds = float(route.get("timeout_seconds", 900.0))
    poll_interval_seconds = float(route.get("poll_interval_seconds", 2.0))
    tool_name = str(route.get("tool_name") or tool_id)
    capability_code = route.get("capability_code")
    remote_inputs = dict(tool_inputs or {})
    remote_inputs.setdefault("workspace_id", workspace_id)
    remote_inputs.setdefault("execution_id", child_execution_id)
    remote_inputs.setdefault("trace_id", parent_trace_id)
    remote_inputs.setdefault("tenant_id", tenant_id)
    if execution_id:
        remote_inputs.setdefault("parent_execution_id", execution_id)
    remote_inputs.setdefault("workflow_step_id", step_id)
    request_payload = {
        "tool_name": tool_name,
        "inputs": dict(remote_inputs),
    }
    parent_playbook_code = (
        playbook_inputs.get("playbook_code")
        if isinstance(playbook_inputs, dict)
        else None
    )
    child_tasks_store = None
    child_task = None
    try:
        child_tasks_store, child_task = ensure_remote_tool_child_shell_fn(
            child_execution_id=child_execution_id,
            parent_execution_id=execution_id,
            workspace_id=workspace_id,
            project_id=playbook_inputs.get("project_id")
            if isinstance(playbook_inputs, dict)
            else None,
            tenant_id=str(tenant_id),
            trace_id=str(parent_trace_id),
            step_id=step_id,
            tool_name=tool_name,
            capability_code=capability_code,
            parent_playbook_code=parent_playbook_code,
            request_payload=request_payload,
            target_device_id=(
                str(target_device_id).strip() if target_device_id else None
            ),
            callback_payload={"mode": "local_core_terminal_event"},
        )
    except Exception:
        logger.warning(
            "WorkflowOrchestrator: failed to create remote child shell for %s/%s",
            step_id,
            tool_id,
            exc_info=True,
        )

    try:
        await connector.start_remote_execution(
            tenant_id=str(tenant_id),
            playbook_code=str(route.get("playbook_code") or tool_name),
            request_payload=request_payload,
            workspace_id=workspace_id,
            capability_code=capability_code,
            execution_id=child_execution_id,
            trace_id=str(parent_trace_id),
            job_type="tool",
            callback_payload={"mode": "local_core_terminal_event"},
            target_device_id=(
                str(target_device_id).strip() if target_device_id else None
            ),
            site_key=str(site_key),
        )
        terminal_result = await connector.wait_for_remote_execution_terminal_result(
            child_execution_id,
            tenant_id=str(tenant_id),
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )
    except Exception as exc:
        if child_tasks_store and child_task:
            try:
                failure_ctx = dict(child_task.execution_context or {})
                failure_remote_execution = dict(failure_ctx.get("remote_execution") or {})
                failure_remote_execution["cloud_dispatch_state"] = "dispatch_failed"
                failure_remote_execution["error"] = str(exc)
                failure_ctx["remote_execution"] = failure_remote_execution
                child_tasks_store.update_task(
                    child_task.id,
                    execution_context=failure_ctx,
                )
                from backend.app.models.workspace import TaskStatus

                child_tasks_store.update_task_status(
                    child_task.id,
                    TaskStatus.FAILED,
                    result={
                        "remote_terminal_status": "dispatch_failed",
                        "provider_metadata": {},
                        "result_payload": None,
                    },
                    error=str(exc),
                    completed_at=utc_now(),
                )
            except Exception:
                logger.warning(
                    "WorkflowOrchestrator: failed to mark child shell dispatch failure",
                    exc_info=True,
                )
        if route.get("fallback_local_on_error"):
            logger.warning(
                "WorkflowOrchestrator: remote dispatch failed for %s/%s: %s; "
                "falling back to local execution",
                step_id,
                tool_id,
                exc,
            )
            return False, None
        raise RecoverableStepError(
            step_id,
            "remote_tool_dispatch_failed",
            str(exc),
        ) from exc

    try:
        from backend.app.services.orchestration.governance_engine import (
            GovernanceEngine,
        )

        local_status = terminal_result.get("status")
        if local_status == "completed":
            callback_status = "succeeded"
        else:
            callback_status = local_status
        GovernanceEngine().process_remote_terminal_event(
            tenant_id=str(tenant_id),
            workspace_id=workspace_id,
            execution_id=child_execution_id,
            trace_id=str(parent_trace_id),
            status=str(callback_status),
            result_payload=terminal_result.get("result_payload"),
            error_message=terminal_result.get("error_message"),
            job_type="tool",
            capability_code=capability_code,
            playbook_code=str(route.get("playbook_code") or tool_name),
            provider_metadata={
                "cloud_execution_id": child_execution_id,
                "cloud_state": terminal_result.get("status"),
                "workflow_step_id": step_id,
                "tool_name": tool_name,
            },
        )
    except Exception:
        logger.warning(
            "WorkflowOrchestrator: failed to sync local child shell terminal result "
            "for %s/%s",
            step_id,
            tool_id,
            exc_info=True,
        )

    terminal_status = str(terminal_result.get("status") or "").strip().lower()
    if terminal_status == "completed":
        result_payload = terminal_result.get("result_payload")
        if isinstance(result_payload, dict) and "result" in result_payload:
            return True, result_payload.get("result")
        return True, result_payload

    error_message = (
        terminal_result.get("error_message")
        or f"remote tool execution ended with status={terminal_status}"
    )
    if route.get("fallback_local_on_error"):
        logger.warning(
            "WorkflowOrchestrator: remote execution failed for %s/%s with %s; "
            "falling back to local execution",
            step_id,
            tool_id,
            terminal_status,
        )
        return False, None
    if terminal_status in {"cancelled", "timeout"}:
        raise RecoverableStepError(
            step_id,
            f"remote_tool_{terminal_status}",
            error_message,
        )
    raise ValueError(f"Remote tool execution failed: {error_message}")
