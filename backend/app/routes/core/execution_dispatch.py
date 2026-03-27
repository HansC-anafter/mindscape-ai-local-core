"""
Execution dispatch and pool management.

Extracted from playbook_execution.py. Contains:
- Remote execution dispatch via CloudConnector
- ExecutionPoolDispatcher access helpers
- Unified pool acquire/release API for start and rerun paths
"""

import logging
import os
from typing import Optional, Dict, Any, Tuple

from fastapi import HTTPException

logger = logging.getLogger(__name__)


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
        from backend.app.services.remote_execution_launch_service import (
            RemoteExecutionLaunchService,
        )
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="Remote execution launch service not available",
        )
    service = RemoteExecutionLaunchService(connector=get_cloud_connector())
    return await service.dispatch(
        playbook_code=playbook_code,
        inputs=inputs,
        workspace_id=workspace_id,
        profile_id=profile_id,
        project_id=project_id,
        tenant_id=tenant_id,
        execution_id=execution_id,
        trace_id=trace_id,
        remote_job_type=remote_job_type,
        remote_request_payload=remote_request_payload,
        capability_code=capability_code,
    )


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
