"""
Execution dispatch and pool management.

Extracted from playbook_execution.py. Contains:
- Remote execution dispatch via CloudConnector
- ExecutionPoolDispatcher access helpers
- Unified pool acquire/release API for start and rerun paths
"""

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple

from fastapi import HTTPException

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


def get_execution_mode() -> str:
    """Read the configured execution mode from environment."""
    return (
        (os.getenv("LOCAL_CORE_EXECUTION_MODE", "in_process") or "in_process")
        .strip()
        .lower()
    )


def get_cloud_connector():
    """Retrieve CloudConnector from global app state.

    Returns None if connector is not initialized.
    """
    try:
        from backend.app.main import app

        return getattr(app.state, "cloud_connector", None)
    except Exception:
        return None


def get_or_create_cloud_connector():
    """Resolve a CloudConnector, falling back to a best-effort ephemeral instance."""
    connector = get_cloud_connector()
    if connector is not None:
        return connector

    try:
        from backend.app.services.cloud_connector.connector import CloudConnector

        return CloudConnector()
    except Exception:
        return None


def get_execution_pool():
    """Retrieve ExecutionPoolDispatcher from global app state.

    Returns None if pool is not initialized.
    """
    try:
        from backend.app.main import app

        return getattr(app.state, "execution_pool", None)
    except Exception:
        return None


async def dispatch_remote_execution(
    playbook_code: str,
    inputs: Optional[Dict[str, Any]],
    workspace_id: Optional[str],
    profile_id: str,
    *,
    project_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    execution_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    remote_job_type: str = "playbook",
    remote_request_payload: Optional[Dict[str, Any]] = None,
    capability_code: Optional[str] = None,
) -> Dict[str, Any]:
    """Dispatch execution to cloud control plane via CloudConnector.

    This is the adapter boundary between local-core and cloud.
    Local-core does not handle tenant routing, quota, or cloud-
    specific logic -- those are resolved by the cloud control plane.

    Args:
        playbook_code: Playbook to execute remotely
        inputs: Execution input data
        workspace_id: Workspace context for state persistence
        profile_id: User profile identifier
        project_id: Optional project context
        tenant_id: Optional tenant identifier (defaults from env)
        execution_id: Optional caller-supplied execution ID
        trace_id: Optional caller-supplied trace ID

    Returns:
        Execution response with cloud execution_id and status

    Raises:
        HTTPException: 503 if CloudConnector unavailable
    """
    try:
        # Use module-level import fallback for connector access
        connector = get_cloud_connector()
        if not connector or not connector.is_connected:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Execution control connector not available. "
                    "Set CLOUD_CONNECTOR_ENABLED=true and configure "
                    "Runtime Environments config_url or "
                    "EXECUTION_CONTROL_API_URL / SITE_HUB_API_URL / CLOUD_API_URL."
                ),
            )

        if not workspace_id:
            raise HTTPException(
                status_code=400,
                detail="workspace_id is required for remote execution",
            )

        # Resolve governance identity up front so local shell and cloud share it.
        tenant_id = tenant_id or os.getenv("CLOUD_TENANT_ID", "default")
        normalized_inputs = dict(inputs or {})
        execution_id = str(
            execution_id
            or normalized_inputs.get("execution_id")
            or uuid.uuid4()
        )
        trace_id = str(
            trace_id
            or normalized_inputs.get("trace_id")
            or execution_id
        )
        normalized_inputs.setdefault("execution_id", execution_id)
        normalized_inputs.setdefault("trace_id", trace_id)
        normalized_inputs.setdefault("tenant_id", tenant_id)
        normalized_inputs.setdefault("profile_id", profile_id)
        if workspace_id:
            normalized_inputs.setdefault("workspace_id", workspace_id)
        if project_id:
            normalized_inputs.setdefault("project_id", project_id)
        cloud_request_payload = _build_remote_request_payload(
            playbook_code=playbook_code,
            profile_id=profile_id,
            normalized_inputs=normalized_inputs,
            remote_job_type=remote_job_type,
            remote_request_payload=remote_request_payload,
        )

        tasks_store, task = _ensure_remote_execution_shell(
            playbook_code=playbook_code,
            workspace_id=workspace_id,
            project_id=project_id,
            profile_id=profile_id,
            tenant_id=tenant_id,
            execution_id=execution_id,
            trace_id=trace_id,
            inputs=normalized_inputs,
        )

        result = await connector.start_remote_execution(
            tenant_id=tenant_id,
            playbook_code=playbook_code,
            request_payload=cloud_request_payload,
            workspace_id=workspace_id,
            capability_code=capability_code,
            execution_id=execution_id,
            trace_id=trace_id,
            job_type=remote_job_type,
            callback_payload={"mode": "local_core_terminal_event"},
        )

        remote_ctx = dict(task.execution_context or {})
        remote_exec = dict(remote_ctx.get("remote_execution") or {})
        remote_exec["cloud_dispatch_state"] = result.get("state", "pending")
        remote_exec["cloud_execution_id"] = result.get("id") or execution_id
        remote_ctx["remote_execution"] = remote_exec
        tasks_store.update_task(task.id, execution_context=remote_ctx)

        cloud_execution_id = result.get("id") or execution_id
        if cloud_execution_id != execution_id:
            logger.warning(
                "Remote execution ID drift detected local=%s cloud=%s playbook=%s",
                execution_id,
                cloud_execution_id,
                playbook_code,
            )

        return {
            "execution_mode": "remote",
            "playbook_code": playbook_code,
            "execution_id": execution_id,
            "trace_id": trace_id,
            "tenant_id": tenant_id,
            "status": result.get("state", "pending"),
            "cloud_execution_id": cloud_execution_id,
            "job_type": remote_job_type,
            "result": {
                "status": result.get("state", "pending"),
                "execution_id": execution_id,
                "note": "Execution dispatched to cloud control plane",
            },
        }
    except HTTPException:
        raise
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="CloudConnector module not available",
        )
    except Exception as e:
        try:
            if "tasks_store" in locals() and "task" in locals():
                remote_ctx = dict(task.execution_context or {})
                remote_exec = dict(remote_ctx.get("remote_execution") or {})
                remote_exec["cloud_dispatch_state"] = "dispatch_failed"
                remote_exec["error"] = str(e)
                remote_ctx["remote_execution"] = remote_exec
                tasks_store.update_task(
                    task.id,
                    execution_context=remote_ctx,
                )
                from backend.app.models.workspace import TaskStatus

                tasks_store.update_task_status(
                    task.id,
                    TaskStatus.FAILED,
                    error=str(e),
                    completed_at=_utc_now(),
                )
        except Exception:
            logger.warning("Failed to mark remote execution shell as failed", exc_info=True)
        logger.error("Remote execution dispatch failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=502,
            detail=f"Cloud dispatch failed: {e}",
        )


def _ensure_remote_execution_shell(
    *,
    playbook_code: str,
    workspace_id: str,
    project_id: Optional[str],
    profile_id: str,
    tenant_id: str,
    execution_id: str,
    trace_id: str,
    inputs: Dict[str, Any],
):
    """Create a local task shell before remote dispatch.

    Remote executions must anchor to a local task/execution record so later
    terminal callbacks can resolve the same execution_id back into governed
    completion handling.
    """
    from backend.app.models.workspace import Task, TaskStatus
    from backend.app.services.stores.tasks_store import TasksStore

    tasks_store = TasksStore()
    existing = tasks_store.get_task_by_execution_id(execution_id)
    if existing:
        return tasks_store, existing

    remote_execution = {
        "tenant_id": tenant_id,
        "trace_id": trace_id,
        "cloud_dispatch_state": "queued",
        "cloud_execution_id": execution_id,
    }
    execution_context = {
        "playbook_code": playbook_code,
        "playbook_name": playbook_code,
        "execution_id": execution_id,
        "trace_id": trace_id,
        "tenant_id": tenant_id,
        "status": "queued",
        "execution_mode": "remote",
        "execution_backend_hint": "remote",
        "inputs": inputs,
        "workspace_id": workspace_id,
        "project_id": project_id,
        "profile_id": profile_id,
        "remote_execution": remote_execution,
        # Prevent the local runner from trying to execute this shell.
        "runner_skip_reason": "remote_execution_shell",
    }
    task = Task(
        id=execution_id,
        workspace_id=workspace_id,
        message_id=str(uuid.uuid4()),
        execution_id=execution_id,
        project_id=project_id,
        pack_id=playbook_code,
        task_type="playbook_execution",
        status=TaskStatus.PENDING,
        execution_context=execution_context,
        created_at=_utc_now(),
        started_at=None,
    )
    tasks_store.create_task(task)
    return tasks_store, task


def _build_remote_request_payload(
    *,
    playbook_code: str,
    profile_id: str,
    normalized_inputs: Dict[str, Any],
    remote_job_type: str,
    remote_request_payload: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build a generic remote payload without embedding pack-specific logic."""
    if not isinstance(remote_request_payload, dict):
        return {
            "inputs": normalized_inputs,
            "profile_id": profile_id,
        }

    payload = dict(remote_request_payload)
    nested_inputs = payload.get("inputs")
    if not isinstance(nested_inputs, dict):
        nested_inputs = {}
    merged_inputs = dict(nested_inputs)
    for key, value in normalized_inputs.items():
        merged_inputs.setdefault(key, value)
    payload["inputs"] = merged_inputs

    if remote_job_type == "playbook":
        payload.setdefault("playbook_code", playbook_code)
        payload.setdefault("profile_id", profile_id)

    return payload


def resolve_and_acquire_backend(hint: str) -> Tuple[str, Optional[str]]:
    """Select backend via pool and acquire a slot.

    Returns:
        (resolved_backend, pool_acquired_backend_or_None).
        If pool_acquired is not None, caller MUST call release_backend()
        in a finally block after dispatch.
    """
    pool = get_execution_pool()
    if not pool or hint == "in_process":
        return hint, None

    resolved = pool.select_backend(hint=hint)
    if resolved != hint:
        logger.info(
            "Pool dispatcher resolved backend: %s -> %s",
            hint,
            resolved,
        )

    if not pool.acquire(resolved):
        logger.warning(
            "Pool capacity exhausted for %s, falling back to in_process",
            resolved,
        )
        return "in_process", None

    return resolved, resolved


def release_backend(pool_acquired: Optional[str]) -> None:
    """Release a pool slot after dispatch completes.

    Args:
        pool_acquired: The backend string returned by resolve_and_acquire_backend,
                       or None if no slot was acquired.
    """
    if pool_acquired:
        pool = get_execution_pool()
        if pool:
            pool.release(pool_acquired)
