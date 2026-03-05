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
                    "Cloud Connector not available. "
                    "Set CLOUD_CONNECTOR_ENABLED=true and "
                    "configure CLOUD_API_URL."
                ),
            )

        # Resolve tenant_id from environment (local-core is single-tenant)
        tenant_id = os.getenv("CLOUD_TENANT_ID", "default")

        result = await connector.start_remote_execution(
            tenant_id=tenant_id,
            playbook_code=playbook_code,
            request_payload={
                "inputs": inputs or {},
                "profile_id": profile_id,
            },
            workspace_id=workspace_id,
        )

        return {
            "execution_mode": "remote",
            "playbook_code": playbook_code,
            "execution_id": result.get("id"),
            "status": result.get("state", "pending"),
            "cloud_execution_id": result.get("id"),
            "result": {
                "status": result.get("state", "pending"),
                "execution_id": result.get("id"),
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
        logger.error("Remote execution dispatch failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=502,
            detail=f"Cloud dispatch failed: {e}",
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
