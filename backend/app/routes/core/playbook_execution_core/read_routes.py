import asyncio
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

from backend.app.routes.core.execution_query_helpers import (
    load_execution_status_payload,
    load_global_execution_rows,
    serialize_global_execution,
)

from .helpers import _load_landed_workflow_result
from .state import logger, playbook_runner

router = APIRouter()

@router.get("/execute/{execution_id}/result")
async def get_playbook_result(execution_id: str):
    """
    Get the final structured output from a completed Playbook execution
    """
    # For workflow mode, check task execution_context first (more reliable)
    # For conversation mode, check playbook_runner first
    try:
        from backend.app.services.stores.tasks_store import TasksStore
        from backend.app.services.mindscape_store import MindscapeStore

        store = MindscapeStore()
        tasks_store = TasksStore()
        task = await asyncio.to_thread(
            tasks_store.get_task_by_execution_id, execution_id
        )

        if task:
            logger.info(
                f"get_playbook_result: Task found for execution_id={execution_id}, status={task.status}, has_context={task.execution_context is not None}"
            )

            # If task failed, return error instead of falling back to conversation mode
            if task.status in ["failed", "FAILED"]:
                error_msg = task.error or "Execution failed"
                logger.warning(
                    f"get_playbook_result: Task failed for execution_id={execution_id}, error={error_msg}"
                )
                raise HTTPException(
                    status_code=500, detail=f"Execution failed: {error_msg}"
                )

            # If task is still running, return 404
            if task.status not in ["completed", "succeeded", "SUCCEEDED"]:
                logger.warning(
                    f"get_playbook_result: Task exists but status is {task.status}, execution may not be completed yet"
                )
                raise HTTPException(
                    status_code=404,
                    detail=f"Execution not completed yet, status: {task.status}",
                )

            if task.execution_context:
                logger.info(
                    f"get_playbook_result: execution_context keys={list(task.execution_context.keys())}"
                )

                # Check for workflow result in execution_context
                workflow_result = task.execution_context.get("workflow_result")
                if workflow_result:
                    if (
                        isinstance(workflow_result, dict)
                        and workflow_result.get("_compacted")
                    ):
                        landed_result = _load_landed_workflow_result(execution_id)
                        if landed_result is not None:
                            return landed_result
                    logger.info(
                        f"get_playbook_result: Found workflow_result for execution_id={execution_id}, keys={list(workflow_result.keys()) if isinstance(workflow_result, dict) else type(workflow_result)}"
                    )
                    return workflow_result

                # Check if result is in execution_context directly
                if "result" in task.execution_context:
                    logger.info(
                        f"get_playbook_result: Found result in execution_context for execution_id={execution_id}"
                    )
                    return task.execution_context["result"]

                # Check for step_outputs in execution_context (workflow mode structure)
                if "step_outputs" in task.execution_context:
                    step_outputs = task.execution_context["step_outputs"]
                    outputs = task.execution_context.get("outputs", {})
                    logger.info(
                        f"get_playbook_result: Found step_outputs for execution_id={execution_id}, keys={list(step_outputs.keys()) if isinstance(step_outputs, dict) else type(step_outputs)}"
                    )
                    return {
                        "status": "completed",
                        "execution_id": execution_id,
                        "step_outputs": step_outputs,
                        "outputs": outputs,
                    }

                landed_result = _load_landed_workflow_result(execution_id)
                if landed_result is not None:
                    return landed_result

                if isinstance(getattr(task, "result", None), dict) and task.result:
                    return task.result

                # Task is completed but no result in context - this shouldn't happen for workflow mode
                logger.error(
                    f"get_playbook_result: Task completed but no result in execution_context for execution_id={execution_id}"
                )
                raise HTTPException(
                    status_code=500,
                    detail="Execution completed but no result found in execution context",
                )
        else:
            logger.warning(
                f"get_playbook_result: Task not found for execution_id={execution_id}"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Failed to get workflow result from task: {e}", exc_info=True)

    # Fallback to conversation mode result (only if task doesn't exist or has no context)
    result = await playbook_runner.get_playbook_execution_result(execution_id)
    if result is not None:
        # Only return conversation mode result if it's not the generic "completed" message
        # or if task doesn't exist (which means it's truly conversation mode)
        if (
            isinstance(result, dict)
            and result.get("note")
            == "Execution completed (conversation mode, no structured output)"
        ):
            # This means execution finished but we couldn't find workflow result
            # Return 404 instead of generic message
            logger.warning(
                f"get_playbook_result: Got conversation mode completion note for execution_id={execution_id}, but task may not have workflow result"
            )
        return result

    raise HTTPException(status_code=404, detail="Execution not found or not completed")


@router.get("/execute/{execution_id}/status")
async def get_playbook_status(execution_id: str):
    """
    Get current execution status (including paused workflow state).

    Unlike /result, this endpoint returns execution_context even when execution is still running or paused.
    """
    try:
        from backend.app.services.stores.tasks_store import TasksStore

        tasks_store = TasksStore()

        payload = await asyncio.to_thread(
            load_execution_status_payload,
            tasks_store,
            execution_id,
        )
        if not payload:
            raise HTTPException(status_code=404, detail="Execution not found")
        ctx = payload["execution_context"]
        return {
            "execution_id": payload["execution_id"],
            "task_status": payload["task_status"],
            "status": ctx.get("status") or payload["task_status"],
            "execution_context": ctx,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get execution status: {str(e)}"
        )


@router.get("/execute/active")
async def list_active_executions():
    """
    List all active Playbook executions
    """
    execution_ids = playbook_runner.list_active_executions()
    return {"active_executions": execution_ids}


@router.post("/execute/reindex", response_model=Dict[str, Any])
async def reindex_playbooks_for_executor():
    """
    Reindex playbooks for the execution subsystem.

    Note: /api/v1/playbooks/reindex refreshes the PlaybookService instance used by the playbook library routes.
    The execution subsystem uses its own PlaybookService instance inside PlaybookRunExecutor.
    This endpoint refreshes that instance to avoid requiring backend restarts after installing new packs.
    """
    try:
        playbook_executor.playbook_service.registry.invalidate_cache()
        playbook_executor.playbook_service.registry._loaded = False
        await playbook_executor.playbook_service.registry._ensure_loaded()
        return {"success": True, "message": "Playbooks reindexed for executor"}
    except Exception as e:
        logger.error(f"Failed to reindex playbooks for executor: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/executions/global")
async def get_global_executions(
    limit: int = Query(30, description="Maximum number of executions"),
    playbook_code_prefix: Optional[str] = Query(
        None, description="Filter by playbook code prefix (e.g., 'ig_')"
    ),
    status_filter: Optional[str] = Query(
        None, description="Comma-separated status filter (e.g., 'running,pending')"
    ),
):
    """List executions across ALL workspaces for global visibility.

    Enables cross-workspace awareness: users can see which tasks are
    occupying runner slots or holding browser locks even if they belong
    to a different workspace.
    """
    try:
        from backend.app.services.stores.tasks_store import TasksStore

        tasks_store = TasksStore()
        rows = load_global_execution_rows(
            tasks_store,
            limit=limit,
            playbook_code_prefix=playbook_code_prefix,
            status_filter=status_filter,
        )

        from backend.app.services.queue_position_cache import QUEUE_CACHE as _QUEUE_CACHE

        _QUEUE_CACHE.refresh_if_stale(tasks_store)

        executions = []
        for row in rows:
            task = tasks_store._row_to_task(row)
            executions.append(
                serialize_global_execution(
                    tasks_store,
                    task,
                    row,
                    _QUEUE_CACHE,
                )
            )

        return {"executions": executions}
    except Exception as e:
        logger.error(f"Failed to get global executions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
