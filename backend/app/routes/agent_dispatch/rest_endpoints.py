"""
Agent Dispatch — REST endpoint handlers.

Contains the REST API endpoints for polling-based task dispatch,
result submission, acknowledgment, progress reporting, and diagnostics.
"""

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from .dispatch_manager import get_agent_dispatch_manager
from .models import (
    AgentResultRequest,
    AgentResultResponse,
    AckRequest,
    ProgressRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================
#  REST endpoints (polling fallback + result submit)
# ============================================================


@router.get("/api/v1/mcp/agent/pending")
async def reserve_pending_tasks_endpoint(
    workspace_id: str = Query(..., description="Workspace ID"),
    client_id: str = Query(..., description="Client ID for lease tracking"),
    surface: str = Query(default="gemini_cli", description="Surface type"),
    limit: int = Query(default=5, ge=1, le=20, description="Max tasks to reserve"),
    lease_seconds: float = Query(
        default=60.0, ge=10, le=300, description="Lease duration"
    ),
    wait_seconds: float = Query(
        default=0,
        ge=0,
        le=5,
        description="Long-poll wait time (max 5s to avoid MCP host timeout).",
    ),
):
    """
    REST long-poll endpoint for MCP pull-based task runner.

    When wait_seconds > 0 and the queue is empty, the request blocks
    until a task is enqueued or the timeout expires. This enables
    protocol-level guardian mode without client-side busy polling.
    """
    manager = get_agent_dispatch_manager()
    tasks = manager.reserve_pending_tasks(
        workspace_id=workspace_id,
        client_id=client_id,
        surface_type=surface,
        limit=limit,
        lease_seconds=lease_seconds,
    )

    # Long-poll: if no tasks and wait_seconds > 0, block until signaled
    if not tasks and wait_seconds > 0:
        event = manager._task_events[workspace_id]
        event.clear()
        try:
            await asyncio.wait_for(event.wait(), timeout=wait_seconds)
        except asyncio.TimeoutError:
            pass
        # Re-check queue after wake-up
        tasks = manager.reserve_pending_tasks(
            workspace_id=workspace_id,
            client_id=client_id,
            surface_type=surface,
            limit=limit,
            lease_seconds=lease_seconds,
        )

    return {"tasks": tasks, "count": len(tasks)}


@router.post("/api/v1/mcp/agent/result", response_model=AgentResultResponse)
async def submit_agent_result(body: AgentResultRequest):
    """
    Submit task execution result via REST.

    Used by MCP Gateway's mindscape_task_submit_result tool.
    Handles both reserved (lease) and inflight tasks.
    After accepting, persists result to workspace filesystem + DB (best-effort).
    """
    manager = get_agent_dispatch_manager()
    result_data = body.model_dump(exclude={"execution_id", "client_id", "lease_id"})
    ctx = manager.submit_result(
        execution_id=body.execution_id,
        result_data=result_data,
        client_id=body.client_id,
        lease_id=body.lease_id,
    )
    if ctx is None:
        raise HTTPException(
            status_code=404,
            detail=f"No pending/inflight task found for execution_id={body.execution_id}",
        )

    # Best-effort: persist result to workspace filesystem + DB
    if not ctx.get("duplicate"):
        try:
            from app.services.task_result_landing import TaskResultLandingService
            from app.services.stores.postgres.workspaces_store import (
                PostgresWorkspacesStore,
            )

            workspace_id = ctx.get("workspace_id")
            if workspace_id:
                ws_store = PostgresWorkspacesStore()
                ws = await ws_store.get_workspace(workspace_id)
                storage_base = getattr(ws, "storage_base_path", None) if ws else None
                artifacts_dir = getattr(ws, "artifacts_dir", None) or "artifacts"

                landing = TaskResultLandingService()
                landing.land_result(
                    workspace_id=workspace_id,
                    execution_id=body.execution_id,
                    result_data=result_data,
                    storage_base_path=storage_base,
                    artifacts_dirname=artifacts_dir,
                    thread_id=ctx.get("thread_id"),
                    project_id=ctx.get("project_id"),
                    task_id=ctx.get("task_id"),
                )
                logger.info(
                    "[AgentWS] Result landed for %s (storage=%s)",
                    body.execution_id,
                    storage_base or "DB-only",
                )
        except Exception:
            logger.exception(
                "[AgentWS] Result landing failed for %s (non-blocking)",
                body.execution_id,
            )

    return AgentResultResponse(
        accepted=True,
        execution_id=body.execution_id,
        message="Result accepted",
    )


@router.get("/api/v1/mcp/agent/result/{execution_id}")
async def get_agent_result(execution_id: str):
    """
    Retrieve a landed task result by execution_id.

    Returns status, storage_ref, summary, result_json, and attachments index.
    """
    try:
        from app.services.task_result_landing import TaskResultLandingService

        landing = TaskResultLandingService()
        result = landing.get_landed_result(execution_id)
        if result is None:
            raise HTTPException(
                status_code=404,
                detail=f"No result found for execution_id={execution_id}",
            )
        return result
    except HTTPException:
        raise
    except Exception:
        logger.exception("get_agent_result failed for %s", execution_id)
        raise HTTPException(status_code=500, detail="Internal error")


@router.get("/api/v1/mcp/agent/status")
async def get_dispatch_status():
    """Get current dispatch manager status (diagnostic endpoint)."""
    manager = get_agent_dispatch_manager()
    return manager.get_status()


# ============================================================
#  Ack / Progress / Inflight endpoints
# ============================================================


@router.post("/api/v1/mcp/agent/ack")
async def ack_task_endpoint(body: AckRequest):
    """Acknowledge task pickup and extend lease (30s -> 300s)."""
    manager = get_agent_dispatch_manager()
    result = manager.ack_task(
        execution_id=body.execution_id,
        lease_id=body.lease_id,
        client_id=body.client_id,
    )
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"No reserved task or lease_id mismatch for {body.execution_id}",
        )
    return result


@router.post("/api/v1/mcp/agent/progress")
async def report_progress_endpoint(body: ProgressRequest):
    """Report task progress and reset lease timer."""
    manager = get_agent_dispatch_manager()
    result = manager.report_progress(
        execution_id=body.execution_id,
        lease_id=body.lease_id,
        progress_pct=body.progress_pct,
        message=body.message,
        client_id=body.client_id,
    )
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"No reserved task or lease_id mismatch for {body.execution_id}",
        )
    return result


@router.get("/api/v1/mcp/agent/inflight")
async def list_inflight_endpoint(
    client_id: str = Query(..., description="Client ID to list inflight tasks for"),
):
    """List reserved/inflight tasks for crash recovery."""
    manager = get_agent_dispatch_manager()
    tasks = manager.list_inflight(client_id=client_id)
    return {"tasks": tasks, "count": len(tasks)}
