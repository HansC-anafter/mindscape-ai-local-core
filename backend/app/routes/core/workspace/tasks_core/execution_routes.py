"""Workspace execution list and group routes."""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi import Path as PathParam

from backend.app.routes.core.read_executor import run_ui_read
from backend.app.services.runner_live_state import RunnerLiveStateStore
from backend.app.services.task_execution_projection import (
    build_execution_group_summary,
    project_execution_for_api,
)
from backend.app.services.workspace_execution_activity import (
    WorkspaceExecutionActivityStore,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def _attach_live_runner_state_to_execution(
    execution: Dict[str, Any],
    *,
    live_state_store: Optional[RunnerLiveStateStore] = None,
) -> Dict[str, Any]:
    """Overlay Redis live runner heartbeat onto active execution list rows."""
    if str(execution.get("status") or "").strip().lower() != "running":
        return execution

    task_id = str(
        execution.get("task_id") or execution.get("id") or execution.get("execution_id") or ""
    ).strip()
    if not task_id:
        return execution

    try:
        live_payload = (live_state_store or RunnerLiveStateStore()).get_task_heartbeat(task_id)
    except Exception:
        live_payload = None
    if not isinstance(live_payload, dict):
        return execution

    heartbeat_at = live_payload.get("heartbeat_at")
    runner_id = live_payload.get("runner_id")
    if heartbeat_at:
        execution["heartbeat_at"] = heartbeat_at
    if runner_id:
        execution["runner_id"] = runner_id

    context = execution.get("execution_context")
    if isinstance(context, dict):
        if heartbeat_at:
            context["heartbeat_at"] = heartbeat_at
            context.setdefault("runner_heartbeat_at", heartbeat_at)
        if runner_id:
            context["runner_id"] = runner_id

    return execution


@router.get("/{workspace_id}/executions")
async def get_workspace_executions(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    limit: int = Query(30, ge=1, le=200, description="Maximum number of executions"),
    offset: int = Query(0, ge=0, description="Execution list offset"),
    status: Optional[List[str]] = Query(
        None,
        description="Execution statuses to include",
    ),
    playbook_code_prefix: Optional[str] = Query(
        None, description="Filter by playbook code prefix (e.g., 'ig_')"
    ),
    playbook_code: Optional[List[str]] = Query(
        None, description="Filter by exact playbook code"
    ),
    exclude_playbook_code: Optional[List[str]] = Query(
        None, description="Exact playbook codes to exclude"
    ),
    parent_execution_id: Optional[str] = Query(
        None,
        description="Filter child executions by exact parent execution ID",
    ),
    active_only: bool = Query(
        False,
        description="Use active execution defaults and hide admission-deferred rows",
    ),
    order_by: str = Query("created_at", description="Field to order by"),
    order: str = Query("desc", description="Sort order: asc or desc"),
    include_execution_context: bool = Query(
        False,
        description=(
            "Legacy parameter. Execution lists always return compact projection context."
        ),
    ),
    group_by_parent: bool = Query(
        False, description="Group results by parent_execution_id"
    ),
) -> Dict[str, Any]:
    """List executions (tasks) for a workspace with optional playbook filters."""
    try:
        activity_store = WorkspaceExecutionActivityStore()
        payload = await run_ui_read(
            activity_store.list_executions,
            workspace_id,
            limit=limit,
            offset=offset,
            statuses=status,
            playbook_code=playbook_code,
            playbook_code_prefix=playbook_code_prefix,
            parent_execution_id=parent_execution_id,
            exclude_playbook_code=exclude_playbook_code,
            active_only=active_only,
            order_by=order_by,
            order=order,
        )

        executions = []
        live_state_store = RunnerLiveStateStore()
        for task_payload in payload["executions"]:
            execution = project_execution_for_api(
                task_payload,
                queue_position=None,
                queue_total=None,
            )
            executions.append(
                _attach_live_runner_state_to_execution(
                    execution,
                    live_state_store=live_state_store,
                )
            )

        if group_by_parent:
            groups = {}
            ungrouped = []
            for d in executions:
                pid = d.get("parent_execution_id")
                if pid:
                    groups.setdefault(pid, []).append(d)
                else:
                    ungrouped.append(d)

            group_summaries = []
            for pid, tasks_list in groups.items():
                group_summaries.append(
                    {
                        "parent_execution_id": pid,
                        "tasks": tasks_list,
                        "summary": build_execution_group_summary(tasks_list),
                    }
                )
            return {
                "groups": group_summaries,
                "ungrouped": ungrouped,
                "limit": payload["limit"],
                "offset": payload["offset"],
                "returned": payload["returned"],
                "has_more": payload["has_more"],
                "next_offset": payload["next_offset"],
            }

        return {
            **payload,
            "executions": executions,
        }
    except Exception as e:
        logger.error(f"Failed to get workspace executions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{workspace_id}/execution-groups")
async def get_workspace_execution_groups(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of groups"),
    offset: int = Query(0, ge=0, description="Execution group offset"),
    status: Optional[List[str]] = Query(
        None,
        description="Execution statuses to include",
    ),
    playbook_code_prefix: Optional[str] = Query(
        None, description="Filter by playbook code prefix (e.g., 'ig_')"
    ),
    playbook_code: Optional[List[str]] = Query(
        None, description="Filter by exact playbook code"
    ),
    exclude_playbook_code: Optional[List[str]] = Query(
        None, description="Exact playbook codes to exclude"
    ),
) -> Dict[str, Any]:
    """List grouped workspace executions from the core projection."""
    try:
        activity_store = WorkspaceExecutionActivityStore()
        payload = await run_ui_read(
            activity_store.list_execution_groups,
            workspace_id,
            limit=limit,
            offset=offset,
            statuses=status,
            playbook_code=playbook_code,
            playbook_code_prefix=playbook_code_prefix,
            exclude_playbook_code=exclude_playbook_code,
        )
        groups = []
        for group in payload["groups"]:
            representative = project_execution_for_api(
                group["representative"],
                queue_position=None,
                queue_total=None,
            )
            groups.append(
                {
                    "parent_execution_id": group["parent_execution_id"],
                    "summary": group["summary"],
                    "latest_at": group["latest_at"],
                    "representative_run": representative,
                }
            )
        ungrouped = [
            project_execution_for_api(item, queue_position=None, queue_total=None)
            for item in payload["ungrouped"]
        ]
        return {
            **payload,
            "groups": groups,
            "ungrouped": ungrouped,
        }
    except Exception as e:
        logger.error(f"Failed to get workspace execution groups: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{workspace_id}/execution-groups/{parent_execution_id}/children")
async def get_workspace_execution_group_children(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    parent_execution_id: str = PathParam(..., description="Parent execution ID"),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of children"),
    offset: int = Query(0, ge=0, description="Execution child offset"),
    status: Optional[List[str]] = Query(
        None,
        description="Execution statuses to include",
    ),
    playbook_code_prefix: Optional[str] = Query(
        None, description="Filter by playbook code prefix (e.g., 'ig_')"
    ),
    playbook_code: Optional[List[str]] = Query(
        None, description="Filter by exact playbook code"
    ),
    exclude_playbook_code: Optional[List[str]] = Query(
        None, description="Exact playbook codes to exclude"
    ),
) -> Dict[str, Any]:
    """List child executions for one parent execution from the core projection."""
    try:
        activity_store = WorkspaceExecutionActivityStore()
        payload = await run_ui_read(
            activity_store.list_execution_group_children,
            workspace_id,
            parent_execution_id=parent_execution_id,
            limit=limit,
            offset=offset,
            statuses=status,
            playbook_code=playbook_code,
            playbook_code_prefix=playbook_code_prefix,
            exclude_playbook_code=exclude_playbook_code,
        )
        executions = [
            project_execution_for_api(item, queue_position=None, queue_total=None)
            for item in payload["executions"]
        ]
        return {
            **payload,
            "executions": executions,
        }
    except Exception as e:
        logger.error(
            f"Failed to get workspace execution group children for {parent_execution_id}: {e}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=str(e))
