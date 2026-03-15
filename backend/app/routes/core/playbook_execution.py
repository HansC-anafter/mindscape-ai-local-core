"""
Playbook Execution API routes
Handles real-time Playbook execution with LLM conversations and structured workflows
"""

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Query, Body
from fastapi.responses import FileResponse

from .execution_schemas import (
    ContinueExecutionRequest,
    StartExecutionRequest,
    CancelExecutionRequest,
    RerunExecutionRequest,
    ResumeExecutionRequest,
)

from .execution_shared import playbook_executor, playbook_runner

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/playbooks", tags=["playbook-execution"])

from .execution_hooks import invoke_lifecycle_hook, async_invoke_lifecycle_hook


def _safe_screenshot_basename(value: str) -> str:
    """
    Accept only a plain filename (no path separators).
    """
    name = (value or "").strip()
    name = os.path.basename(name)
    if not name or name in {".", ".."}:
        raise HTTPException(status_code=400, detail="Invalid file name")
    # Only allow common screenshot types we generate.
    if not (name.endswith(".png") or name.endswith(".jpg") or name.endswith(".jpeg")):
        raise HTTPException(status_code=400, detail="Unsupported file type")
    # Basic character allowlist to avoid weird path tricks.
    for ch in name:
        if ch.isalnum() or ch in "._-":
            continue
        raise HTTPException(status_code=400, detail="Invalid file name")
    return name


@router.get("/execute/{execution_id}/debug/screenshot")
async def get_execution_debug_screenshot(
    execution_id: str, file: str = Query(..., description="Screenshot filename")
):
    """
    Serve execution debug screenshots saved under /app/data.
    UI passes only the basename (e.g. ig_debug_scroll_<exec>_..._dialog.png).
    """
    basename = _safe_screenshot_basename(file)
    path = os.path.join("/app/data", basename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(
        path,
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
    )


from .execution_dispatch import (
    get_execution_mode,
    dispatch_remote_execution,
    resolve_and_acquire_backend,
    release_backend,
)


@router.post("/execute/start")
async def start_playbook_execution(
    playbook_code: str = Query(..., description="Playbook code to execute"),
    profile_id: str = Query("default-user", description="Profile ID"),
    workspace_id: Optional[str] = Query(
        None,
        description="Workspace ID for state persistence (required for multi-turn conversations)",
    ),
    project_id: Optional[str] = Query(
        None, description="Project ID for sandbox context"
    ),
    target_language: Optional[str] = Query(
        None, description="Target language for output (e.g., 'zh-TW', 'en')"
    ),
    variant_id: Optional[str] = Query(
        None, description="Optional personalized variant ID to use"
    ),
    auto_execute: Optional[bool] = Query(
        None, description="If true, skip confirmations and execute tools directly"
    ),
    execution_backend: Optional[str] = Query(
        None,
        description="Neutral execution backend hint: auto|runner|in_process. Routing is always decided by backend.",
    ),
    request: Optional[StartExecutionRequest] = Body(
        None, description="Optional inputs for the playbook"
    ),
):
    """
    Start a new Playbook execution

    Returns the execution_id and initial assistant message

    Note: workspace_id is required for multi-turn conversations to persist execution state.
    Without it, /continue calls will fail with "Execution not found".

    Set auto_execute=true to skip confirmations and execute tools directly (useful for automated testing).
    """
    try:
        inputs = request.inputs if request else None
        final_target_language = target_language or (
            request.target_language if request else None
        )
        final_variant_id = variant_id or (request.variant_id if request else None)

        # Auto-assign variant if not explicitly provided
        if not final_variant_id:
            try:
                from backend.app.services.variant_assigner import assign_variant

                final_variant_id = assign_variant(
                    playbook_code=playbook_code,
                    variant_id=final_variant_id,
                    registry=playbook_runner.playbook_service.registry,
                    workspace_id=workspace_id,
                    target_language=final_target_language,
                )
            except Exception as e:
                logger.warning(f"Variant auto-assignment failed (non-fatal): {e}")
        final_auto_execute = auto_execute or (request.auto_execute if request else None)
        final_execution_backend = (
            (
                execution_backend
                or (request.execution_backend if request else None)
                or "auto"
            )
            if isinstance(
                execution_backend
                or (request.execution_backend if request else None)
                or "auto",
                str,
            )
            else "auto"
        )
        final_execution_backend = (final_execution_backend or "auto").strip().lower()
        if final_execution_backend not in {"auto", "runner", "in_process", "remote"}:
            final_execution_backend = "auto"

        # Extract workspace_id and project_id from inputs if not provided as query params
        # (must happen before any backend branch that needs workspace_id)
        final_workspace_id = workspace_id or (
            inputs.get("workspace_id") if inputs else None
        )
        final_project_id = project_id or (inputs.get("project_id") if inputs else None)

        # If no project_id provided, use workspace.primary_project_id as fallback
        if not final_project_id and final_workspace_id:
            try:
                from ...services.mindscape_store import MindscapeStore

                store = MindscapeStore()
                workspace = await store.get_workspace(final_workspace_id)
                if (
                    workspace
                    and hasattr(workspace, "primary_project_id")
                    and workspace.primary_project_id
                ):
                    final_project_id = workspace.primary_project_id
                    logger.info(
                        f"Using workspace.primary_project_id={final_project_id} for playbook {playbook_code}"
                    )
            except Exception as e:
                logger.warning(f"Failed to get workspace.primary_project_id: {e}")

        # Pool-aware backend selection
        final_execution_backend, pool_acquired_backend = resolve_and_acquire_backend(
            final_execution_backend
        )

        # Remote backend: dispatch to cloud control plane via CloudConnector
        if final_execution_backend == "remote":
            try:
                return await dispatch_remote_execution(
                    playbook_code=playbook_code,
                    inputs=inputs,
                    workspace_id=final_workspace_id,
                    profile_id=profile_id,
                )
            finally:
                release_backend(pool_acquired_backend)

        # Inject auto_execute into inputs for downstream processing
        if final_auto_execute and inputs:
            inputs["auto_execute"] = True
        elif final_auto_execute:
            inputs = {"auto_execute": True}

        # Inject neutral execution backend hint into inputs for downstream processing
        if inputs and isinstance(inputs, dict):
            inputs["execution_backend"] = final_execution_backend
        elif inputs is None:
            inputs = {"execution_backend": final_execution_backend}

        # Update user_meta use_count when playbook is executed
        try:
            from ...services.mindscape_store import MindscapeStore

            store = MindscapeStore()
            await asyncio.to_thread(
                store.update_user_meta,
                profile_id,
                playbook_code,
                {
                    "increment_use_count": True,
                    "last_used_at": _utc_now().isoformat(),
                },
            )
        except Exception as e:
            logger.warning(
                f"Failed to update user_meta for playbook {playbook_code}: {e}"
            )

        exec_mode = get_execution_mode()
        prefer_runner = final_execution_backend == "runner" or (
            final_execution_backend == "auto" and exec_mode == "runner"
        )
        force_in_process = final_execution_backend == "in_process"

        if prefer_runner and not force_in_process:
            playbook_run = await playbook_executor.playbook_service.load_playbook_run(
                playbook_code=playbook_code,
                locale="zh-TW",
                workspace_id=final_workspace_id,
            )
            if (
                playbook_run
                and playbook_run.get_execution_mode() == "workflow"
                and playbook_run.has_json()
            ):
                execution_id = str(uuid.uuid4())
                normalized_inputs = inputs.copy() if isinstance(inputs, dict) else {}
                normalized_inputs["execution_id"] = execution_id
                normalized_inputs["execution_backend"] = final_execution_backend
                if final_workspace_id and "workspace_id" not in normalized_inputs:
                    normalized_inputs["workspace_id"] = final_workspace_id
                if final_project_id and "project_id" not in normalized_inputs:
                    normalized_inputs["project_id"] = final_project_id
                if profile_id and "profile_id" not in normalized_inputs:
                    normalized_inputs["profile_id"] = profile_id

                from backend.app.services.stores.tasks_store import TasksStore
                from backend.app.services.mindscape_store import MindscapeStore
                from backend.app.models.workspace import Task, TaskStatus

                store = MindscapeStore()
                tasks_store = TasksStore()

                # Calculate total_steps from playbook for frontend progress display
                total_steps = (
                    len(playbook_run.playbook_json.steps)
                    if playbook_run.playbook_json and playbook_run.playbook_json.steps
                    else 1
                )
                playbook_name = (
                    playbook_run.playbook.metadata.name
                    if playbook_run.playbook and playbook_run.playbook.metadata
                    else playbook_code
                )

                # Extract concurrency policy from playbook.json (if declared)
                concurrency_config = None
                if (
                    playbook_run.playbook_json
                    and playbook_run.playbook_json.concurrency
                ):
                    c = playbook_run.playbook_json.concurrency
                    concurrency_config = {
                        "lock_key_input": c.lock_key_input,
                        "max_parallel": c.max_parallel,
                        "lock_scope": c.lock_scope,
                    }

                # Extract runner_timeout_seconds from execution_profile (if declared)
                runner_timeout_seconds = None
                if (
                    playbook_run.playbook_json
                    and playbook_run.playbook_json.execution_profile
                ):
                    ep = playbook_run.playbook_json.execution_profile
                    raw_timeout = ep.get("runner_timeout_seconds")
                    if isinstance(raw_timeout, (int, float)) and raw_timeout > 0:
                        max_ceiling = int(
                            os.environ.get(
                                "LOCAL_CORE_RUNNER_MAX_TIMEOUT_SECONDS", "43200"
                            )
                        )
                        runner_timeout_seconds = min(int(raw_timeout), max_ceiling)

                # Extract lifecycle_hooks from playbook spec (if declared)
                lifecycle_hooks_config = None
                if (
                    playbook_run.playbook_json
                    and playbook_run.playbook_json.lifecycle_hooks
                ):
                    lifecycle_hooks_config = playbook_run.playbook_json.lifecycle_hooks

                await asyncio.to_thread(
                    tasks_store.create_task,
                    Task(
                        id=execution_id,
                        workspace_id=final_workspace_id,
                        message_id=str(uuid.uuid4()),
                        execution_id=execution_id,
                        project_id=final_project_id,
                        profile_id=profile_id,
                        pack_id=playbook_code,
                        task_type="playbook_execution",
                        status=TaskStatus.PENDING,
                        execution_context={
                            "playbook_code": playbook_code,
                            "playbook_name": playbook_name,
                            "execution_id": execution_id,
                            "status": "queued",
                            "execution_mode": "runner",
                            "execution_backend_hint": final_execution_backend,
                            "inputs": normalized_inputs,
                            "workspace_id": final_workspace_id,
                            "project_id": final_project_id,
                            "profile_id": profile_id,
                            "total_steps": total_steps,
                            "current_step_index": 0,
                            **(
                                {"concurrency": concurrency_config}
                                if concurrency_config
                                else {}
                            ),
                            **(
                                {"runner_timeout_seconds": runner_timeout_seconds}
                                if runner_timeout_seconds
                                else {}
                            ),
                            **(
                                {"lifecycle_hooks": lifecycle_hooks_config}
                                if lifecycle_hooks_config
                                else {}
                            ),
                        },
                        created_at=_utc_now(),
                        started_at=None,
                    ),
                )

                # Invoke on_queue lifecycle hook (if declared in playbook spec)
                if (
                    playbook_run.playbook_json
                    and playbook_run.playbook_json.lifecycle_hooks
                ):
                    on_queue = playbook_run.playbook_json.lifecycle_hooks.get(
                        "on_queue"
                    )
                    if on_queue and isinstance(on_queue, dict):
                        try:
                            await async_invoke_lifecycle_hook(
                                hook_name="on_queue",
                                hook_spec=on_queue,
                                normalized_inputs=normalized_inputs,
                                execution_context={
                                    "execution_id": execution_id,
                                    "workspace_id": final_workspace_id,
                                    "playbook_code": playbook_code,
                                },
                            )
                        except Exception as e:
                            logger.warning(f"on_queue hook failed (non-fatal): {e}")

                return {
                    "execution_mode": "workflow",
                    "playbook_code": playbook_code,
                    "execution_id": execution_id,
                    "status": "running",
                    "result": {
                        "status": "running",
                        "execution_id": execution_id,
                        "note": "Execution queued",
                    },
                }

        # Use unified executor (automatically selects execution mode)
        result = await playbook_executor.execute_playbook_run(
            playbook_code=playbook_code,
            profile_id=profile_id,
            inputs=inputs,
            workspace_id=final_workspace_id,
            project_id=final_project_id,
            target_language=final_target_language,
            variant_id=final_variant_id,
        )

        # Handle different return formats
        if result.get("execution_mode") == "conversation":
            # For conversation mode, result.result contains PlaybookRunner response
            return result.get("result", result)
        else:
            # For workflow mode, return workflow result with execution_id
            return {
                "execution_mode": result.get("execution_mode"),
                "playbook_code": result.get("playbook_code"),
                "execution_id": result.get("execution_id"),
                **result.get("result", {}),
            }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to start playbook: {str(e)}"
        )


@router.post("/execute/{execution_id}/continue")
async def continue_playbook_execution(
    execution_id: str,
    request: ContinueExecutionRequest = Body(...),
    profile_id: str = Query("default-user", description="Profile ID"),
):
    """
    Continue an ongoing Playbook execution with user response

    Returns the next assistant message and completion status
    """
    try:
        result = await playbook_runner.continue_playbook_execution(
            execution_id=execution_id,
            user_message=request.user_message,
            profile_id=profile_id,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to continue playbook: {str(e)}"
        )


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
        from backend.app.services.mindscape_store import MindscapeStore

        store = MindscapeStore()
        tasks_store = TasksStore()
        task = await asyncio.to_thread(
            tasks_store.get_task_by_execution_id, execution_id
        )
        if not task:
            raise HTTPException(status_code=404, detail="Execution not found")
        ctx = task.execution_context if isinstance(task.execution_context, dict) else {}
        return {
            "execution_id": execution_id,
            "task_status": task.status,
            "status": ctx.get("status") or task.status,
            "execution_context": ctx,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get execution status: {str(e)}"
        )


@router.post("/execute/{execution_id}/resume")
async def resume_playbook_execution(
    execution_id: str,
    request: ResumeExecutionRequest = Body(...),
    profile_id: str = Query("default-user", description="Profile ID"),
):
    """
    Resume a paused workflow execution by approving/rejecting the current gate.
    """
    try:
        from backend.app.services.stores.tasks_store import TasksStore
        from backend.app.services.mindscape_store import MindscapeStore
        from backend.app.models.workspace import TaskStatus

        store = MindscapeStore()
        tasks_store = TasksStore()
        task = await asyncio.to_thread(
            tasks_store.get_task_by_execution_id, execution_id
        )
        if not task:
            raise HTTPException(status_code=404, detail="Execution not found")

        ctx = task.execution_context if isinstance(task.execution_context, dict) else {}
        checkpoint = ctx.get("checkpoint")
        if not isinstance(checkpoint, dict):
            raise HTTPException(
                status_code=409,
                detail="Execution has no checkpoint to resume (not paused?)",
            )

        paused_step_id = checkpoint.get("paused_step_id")
        if not paused_step_id:
            raise HTTPException(
                status_code=409, detail="Checkpoint missing paused_step_id"
            )
        if request.step_id and request.step_id != paused_step_id:
            raise HTTPException(
                status_code=409, detail="step_id does not match paused_step_id"
            )

        if request.action == "reject":
            ctx = dict(ctx)
            ctx["status"] = "failed"
            ctx["error"] = request.comment or "Gate rejected"
            await asyncio.to_thread(
                tasks_store.update_task,
                task.id,
                execution_context=ctx,
                status=TaskStatus.FAILED,
                completed_at=_utc_now(),
                error=ctx["error"],
            )
            return {
                "status": "rejected",
                "execution_id": execution_id,
                "paused_step_id": paused_step_id,
            }

        # Approve: re-run the workflow using the saved checkpoint and gate decision.
        playbook_code = (ctx.get("playbook_code") or task.pack_id or "").strip()
        workspace_id = (ctx.get("workspace_id") or task.workspace_id or "").strip()
        project_id = ctx.get("project_id") or getattr(task, "project_id", None)
        profile_id_effective = (
            ctx.get("profile_id") or profile_id or "default-user"
        ).strip()
        inputs = ctx.get("inputs") if isinstance(ctx.get("inputs"), dict) else {}
        inputs = dict(inputs)
        inputs["execution_id"] = execution_id
        inputs["_workflow_checkpoint"] = checkpoint

        gate_decisions = inputs.get("gate_decisions")
        if not isinstance(gate_decisions, dict):
            gate_decisions = {}
        gate_decisions = dict(gate_decisions)
        gate_decisions[paused_step_id] = {
            "action": "approved",
            "comment": request.comment,
            "decided_at": _utc_now().isoformat(),
        }
        inputs["gate_decisions"] = gate_decisions

        # Mark task back to running before scheduling the resume run.
        ctx2 = dict(ctx)
        ctx2["status"] = "running"
        ctx2["error"] = None
        ctx2["checkpoint"] = checkpoint
        ctx2["inputs"] = inputs
        await asyncio.to_thread(
            tasks_store.update_task,
            task.id,
            execution_context=ctx2,
            status=TaskStatus.RUNNING,
            error=None,
            completed_at=None,
        )

        await playbook_executor.execute_playbook_run(
            playbook_code=playbook_code,
            profile_id=profile_id_effective,
            inputs=inputs,
            workspace_id=workspace_id,
            project_id=project_id,
        )

        return {
            "status": "running",
            "execution_id": execution_id,
            "resumed_from_step_id": paused_step_id,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to resume execution: {str(e)}"
        )


@router.post("/execute/{execution_id}/cancel")
async def cancel_playbook_execution(
    execution_id: str, request: Optional[CancelExecutionRequest] = Body(None)
):
    try:
        from datetime import datetime, timezone
        from backend.app.services.stores.tasks_store import TasksStore
        from backend.app.services.mindscape_store import MindscapeStore
        from backend.app.models.workspace import TaskStatus
        from backend.app.services.execution_task_registry import execution_task_registry
        from backend.app.services.stores.graph_changelog_store import (
            GraphChangelogStore,
        )

        store = MindscapeStore()
        tasks_store = TasksStore()
        task = await asyncio.to_thread(
            tasks_store.get_task_by_execution_id, execution_id
        )
        if not task:
            raise HTTPException(status_code=404, detail="Execution not found")

        execution_task_registry.cancel(execution_id)

        ctx = task.execution_context if isinstance(task.execution_context, dict) else {}
        ctx["status"] = "cancelled"
        ctx["error"] = (
            request.reason if request and request.reason else "Cancelled by user"
        )
        ctx["cancelled_at"] = _utc_now().isoformat()

        # Reject pending graph node if exists (P2: cancellation sync)
        pending_graph_node_id = ctx.get("pending_graph_node_id")
        if pending_graph_node_id:
            try:
                graph_store = GraphChangelogStore()
                result = await asyncio.to_thread(
                    graph_store.reject_change, pending_graph_node_id
                )
                if result.get("success"):
                    logger.info(
                        f"Rejected graph node {pending_graph_node_id} for cancelled task {execution_id}"
                    )
                else:
                    logger.warning(
                        f"Failed to reject graph node {pending_graph_node_id}: {result.get('error')}"
                    )
            except Exception as e:
                logger.warning(f"Error rejecting graph node on cancellation: {e}")

        await asyncio.to_thread(
            tasks_store.update_task,
            task.id,
            execution_context=ctx,
            status=TaskStatus.CANCELLED_BY_USER,
            completed_at=_utc_now(),
            error=ctx["error"],
        )

        return {"status": "cancelled", "execution_id": execution_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to cancel execution: {str(e)}"
        )


# Mount rerun handler from extracted module (main.py zero-change)
from .playbook_rerun import rerun_playbook_execution

router.post("/execute/{execution_id}/rerun")(rerun_playbook_execution)


@router.delete("/execute/{execution_id}")
async def cleanup_playbook_execution(execution_id: str):
    """
    Clean up a completed Playbook execution from memory
    """
    playbook_runner.cleanup_execution(execution_id)
    return {"status": "cleaned up"}


@router.post("/execute/{execution_id}/reset-step")
async def reset_current_step(
    execution_id: str, profile_id: str = Query("default-user", description="Profile ID")
):
    """
    Reset current step to restart from the beginning of current step.

    This will:
    1. Decrement current_step by 1 (if > 0) to restart current step
    2. Clear conversation history from current step onwards (but preserve important context)
    3. Update step event status from 'completed' back to 'running'
    4. Preserve tool call records (already saved in database, no deletion needed)
    5. Preserve sandbox_id in execution_context
    6. Save the reset state

    Useful when a step gets stuck or needs to be retried.

    Note: Tool call records are preserved in ToolCallsStore (database table).
    Step events are updated to reflect the reset state.
    Sandbox context is preserved in execution_context.
    """
    try:
        result = await playbook_runner.reset_current_step(
            execution_id=execution_id, profile_id=profile_id
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reset step: {str(e)}")


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
        from sqlalchemy import text
        from backend.app.services.stores.tasks_store import TasksStore

        tasks_store = TasksStore()

        query_parts = [
            """
            SELECT
                t.id,
                t.workspace_id,
                t.message_id,
                t.execution_id,
                t.project_id,
                t.pack_id,
                t.task_type,
                t.status,
                t.params,
                t.result,
                (
                    t.execution_context::jsonb
                    - 'result'
                    - 'workflow_result'
                    - 'step_outputs'
                    - 'outputs'
                )::json AS execution_context,
                t.storyline_tags,
                t.created_at,
                t.started_at,
                t.completed_at,
                t.error,
                w.title AS workspace_name
            FROM tasks t
            LEFT JOIN workspaces w ON w.id = t.workspace_id
            WHERE 1=1
            """
        ]
        params: dict = {}

        if playbook_code_prefix:
            query_parts.append("AND t.pack_id LIKE :pack_prefix")
            params["pack_prefix"] = f"{playbook_code_prefix}%"

        if status_filter:
            statuses = [s.strip().lower() for s in status_filter.split(",") if s.strip()]
            if statuses:
                query_parts.append("AND LOWER(t.status) = ANY(:statuses)")
                params["statuses"] = statuses

        query_parts.append("ORDER BY t.created_at DESC")
        query_parts.append("LIMIT :limit")
        params["limit"] = limit

        with tasks_store.get_connection() as conn:
            rows = conn.execute(text(" ".join(query_parts)), params).fetchall()

        # Import shared queue cache (process-wide singleton from tasks route)
        from backend.app.routes.core.workspace.tasks import _QUEUE_CACHE

        _QUEUE_CACHE.refresh_if_stale(tasks_store)

        executions = []
        for row in rows:
            task = tasks_store._row_to_task(row)
            d = task.model_dump()
            d["playbook_code"] = d.get("pack_id") or (
                d.get("execution_context") or {}
            ).get("playbook_code")
            d["execution_id"] = d.get("execution_id") or d.get("id")
            d["workspace_name"] = row.workspace_name if hasattr(row, "workspace_name") else None
            d["queue_position"] = _QUEUE_CACHE.get_position(d.get("id") or "")
            d["queue_total"] = _QUEUE_CACHE.total
            executions.append(d)

        return {"executions": executions}
    except Exception as e:
        logger.error(f"Failed to get global executions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

