"""
Playbook Execution API routes
Handles real-time Playbook execution with LLM conversations and structured workflows
"""

import logging
import os
import uuid
from datetime import datetime
from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Query, Body
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Literal

from ...services.playbook_run_executor import PlaybookRunExecutor
from ...services.playbook_runner import PlaybookRunner

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/playbooks", tags=["playbook-execution"])

# Initialize unified executor (automatically selects PlaybookRunner or WorkflowOrchestrator)
playbook_executor = PlaybookRunExecutor()
# Keep PlaybookRunner for continue operations (conversation mode)
playbook_runner = PlaybookRunner()


class ContinueExecutionRequest(BaseModel):
    """Request to continue playbook execution"""

    user_message: str


class StartExecutionRequest(BaseModel):
    """Request to start playbook execution"""

    inputs: Optional[dict] = None
    target_language: Optional[str] = None
    variant_id: Optional[str] = None
    auto_execute: Optional[bool] = (
        None  # If True, skip confirmations and execute tools directly
    )
    execution_backend: Optional[Literal["auto", "runner", "in_process"]] = None


class CancelExecutionRequest(BaseModel):
    """Request to cancel playbook execution"""

    reason: Optional[str] = None


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
    return FileResponse(path)


class RerunExecutionRequest(BaseModel):
    """Request to rerun playbook execution with original inputs"""

    override_inputs: Optional[dict] = None


class ResumeExecutionRequest(BaseModel):
    """Request to resume a paused workflow execution"""

    action: Literal["approve", "reject"]
    step_id: Optional[str] = None
    comment: Optional[str] = None


def _get_execution_mode() -> str:
    return (
        (os.getenv("LOCAL_CORE_EXECUTION_MODE", "in_process") or "in_process")
        .strip()
        .lower()
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
        if final_execution_backend not in {"auto", "runner", "in_process"}:
            final_execution_backend = "auto"

        # Extract workspace_id and project_id from inputs if not provided as query params
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
            store.update_user_meta(
                profile_id,
                playbook_code,
                {
                    "increment_use_count": True,
                    "last_used_at": datetime.utcnow().isoformat(),
                },
            )
        except Exception as e:
            logger.warning(
                f"Failed to update user_meta for playbook {playbook_code}: {e}"
            )

        exec_mode = _get_execution_mode()
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
                tasks_store = TasksStore(db_path=store.db_path)

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

                tasks_store.create_task(
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
                        },
                        created_at=datetime.utcnow(),
                        started_at=None,
                    )
                )

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
        tasks_store = TasksStore(db_path=store.db_path)
        task = tasks_store.get_task_by_execution_id(execution_id)

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
        tasks_store = TasksStore(db_path=store.db_path)
        task = tasks_store.get_task_by_execution_id(execution_id)
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
        tasks_store = TasksStore(db_path=store.db_path)
        task = tasks_store.get_task_by_execution_id(execution_id)
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
            tasks_store.update_task(
                task.id,
                execution_context=ctx,
                status=TaskStatus.FAILED,
                completed_at=datetime.utcnow(),
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
            "decided_at": datetime.utcnow().isoformat(),
        }
        inputs["gate_decisions"] = gate_decisions

        # Mark task back to running before scheduling the resume run.
        ctx2 = dict(ctx)
        ctx2["status"] = "running"
        ctx2["error"] = None
        ctx2["checkpoint"] = checkpoint
        ctx2["inputs"] = inputs
        tasks_store.update_task(
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
        from datetime import datetime
        from backend.app.services.stores.tasks_store import TasksStore
        from backend.app.services.mindscape_store import MindscapeStore
        from backend.app.models.workspace import TaskStatus
        from backend.app.services.execution_task_registry import execution_task_registry
        from backend.app.services.stores.graph_changelog_store import (
            GraphChangelogStore,
        )

        store = MindscapeStore()
        tasks_store = TasksStore(db_path=store.db_path)
        task = tasks_store.get_task_by_execution_id(execution_id)
        if not task:
            raise HTTPException(status_code=404, detail="Execution not found")

        execution_task_registry.cancel(execution_id)

        ctx = task.execution_context if isinstance(task.execution_context, dict) else {}
        ctx["status"] = "cancelled"
        ctx["error"] = (
            request.reason if request and request.reason else "Cancelled by user"
        )
        ctx["cancelled_at"] = datetime.utcnow().isoformat()

        # Reject pending graph node if exists (P2: cancellation sync)
        pending_graph_node_id = ctx.get("pending_graph_node_id")
        if pending_graph_node_id:
            try:
                graph_store = GraphChangelogStore()
                result = graph_store.reject_change(pending_graph_node_id)
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

        tasks_store.update_task(
            task.id,
            execution_context=ctx,
            status=TaskStatus.CANCELLED_BY_USER,
            completed_at=datetime.utcnow(),
            error=ctx["error"],
        )

        return {"status": "cancelled", "execution_id": execution_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to cancel execution: {str(e)}"
        )


@router.post("/execute/{execution_id}/rerun")
async def rerun_playbook_execution(
    execution_id: str,
    request: Optional[RerunExecutionRequest] = Body(None),
    execution_backend: Optional[str] = Query(
        None,
        description="Neutral execution backend hint: auto|runner|in_process. Routing is always decided by backend.",
    ),
):
    try:
        from backend.app.services.stores.tasks_store import TasksStore
        from backend.app.services.mindscape_store import MindscapeStore
        from backend.app.services.stores.artifacts_store import ArtifactsStore

        store = MindscapeStore()
        tasks_store = TasksStore(db_path=store.db_path)
        task = tasks_store.get_task_by_execution_id(execution_id)
        if not task:
            raise HTTPException(status_code=404, detail="Execution not found")

        ctx = task.execution_context if isinstance(task.execution_context, dict) else {}
        playbook_code = ctx.get("playbook_code") or task.pack_id
        if not playbook_code:
            raise HTTPException(
                status_code=409, detail="Missing playbook_code for rerun"
            )

        original_inputs = ctx.get("inputs") or task.params or None
        if not isinstance(original_inputs, dict) and original_inputs is not None:
            original_inputs = None

        merged_inputs: Optional[dict] = None
        if isinstance(original_inputs, dict):
            merged_inputs = dict(original_inputs)
        if request and isinstance(request.override_inputs, dict):
            merged_inputs = merged_inputs or {}
            merged_inputs.update(request.override_inputs)

        def _infer_target_username_from_artifacts(
            workspace_id: str, exec_id: str
        ) -> Optional[str]:
            try:
                artifacts_store = ArtifactsStore(db_path=store.db_path)
                arts = artifacts_store.list_artifacts_by_workspace(
                    workspace_id=workspace_id, limit=300
                )
                for a in arts:
                    if getattr(a, "execution_id", None) != exec_id:
                        continue
                    if getattr(a, "playbook_code", None) != "ig_analyze_following":
                        continue
                    meta = a.metadata if isinstance(a.metadata, dict) else {}
                    val = (
                        meta.get("target_username") or meta.get("target_seed") or ""
                    ).strip()
                    if val:
                        return val
                    content = a.content if isinstance(a.content, dict) else {}
                    cm = (
                        content.get("metadata")
                        if isinstance(content.get("metadata"), dict)
                        else {}
                    )
                    val2 = (
                        cm.get("target_username") or cm.get("target_seed") or ""
                    ).strip()
                    if val2:
                        return val2
            except Exception:
                return None
            return None

        if playbook_code == "ig_analyze_following":
            if not merged_inputs:
                merged_inputs = {}
            if not str(merged_inputs.get("target_username") or "").strip():
                workspace_id_for_infer = (
                    ctx.get("workspace_id") or task.workspace_id or ""
                ).strip()
                inferred = (
                    _infer_target_username_from_artifacts(
                        workspace_id_for_infer, execution_id
                    )
                    if workspace_id_for_infer
                    else None
                )
                if inferred:
                    merged_inputs["target_username"] = inferred
            if not str(merged_inputs.get("target_username") or "").strip():
                raise HTTPException(
                    status_code=409,
                    detail="Cannot rerun ig_analyze_following: missing target_username. Provide override_inputs.target_username.",
                )

        final_execution_backend = (execution_backend or "auto").strip().lower()
        if final_execution_backend not in {"auto", "runner", "in_process"}:
            final_execution_backend = "auto"

        if merged_inputs is None:
            merged_inputs = {}
        if isinstance(merged_inputs, dict):
            merged_inputs["execution_backend"] = final_execution_backend

        # Ensure workspace_id and project_id are passed (executor expects them).
        workspace_id = ctx.get("workspace_id") or task.workspace_id
        project_id = ctx.get("project_id") or getattr(task, "project_id", None)
        profile_id = (
            ctx.get("profile_id") or getattr(task, "profile_id", None) or "default-user"
        )

        # If backend is configured for runner (or caller explicitly prefers runner), enqueue workflow-json playbooks.
        exec_mode = _get_execution_mode()
        prefer_runner = final_execution_backend == "runner" or (
            final_execution_backend == "auto" and exec_mode == "runner"
        )
        force_in_process = final_execution_backend == "in_process"
        if prefer_runner and not force_in_process:
            playbook_run = await playbook_executor.playbook_service.load_playbook_run(
                playbook_code=playbook_code,
                locale="zh-TW",
                workspace_id=workspace_id,
            )
            if (
                playbook_run
                and playbook_run.get_execution_mode() == "workflow"
                and playbook_run.has_json()
            ):
                new_execution_id = str(uuid.uuid4())
                normalized_inputs = (
                    merged_inputs.copy() if isinstance(merged_inputs, dict) else {}
                )
                normalized_inputs["execution_id"] = new_execution_id
                normalized_inputs["execution_backend"] = final_execution_backend
                if workspace_id and "workspace_id" not in normalized_inputs:
                    normalized_inputs["workspace_id"] = workspace_id
                if project_id and "project_id" not in normalized_inputs:
                    normalized_inputs["project_id"] = project_id
                if profile_id and "profile_id" not in normalized_inputs:
                    normalized_inputs["profile_id"] = profile_id

                from backend.app.models.workspace import Task, TaskStatus

                tasks_store.create_task(
                    Task(
                        id=new_execution_id,
                        workspace_id=workspace_id,
                        message_id=str(uuid.uuid4()),
                        execution_id=new_execution_id,
                        project_id=project_id,
                        profile_id=profile_id,
                        pack_id=playbook_code,
                        task_type="playbook_execution",
                        status=TaskStatus.PENDING,
                        execution_context={
                            "playbook_code": playbook_code,
                            "execution_id": new_execution_id,
                            "status": "queued",
                            "execution_mode": "runner",
                            "execution_backend_hint": final_execution_backend,
                            "inputs": normalized_inputs,
                            "workspace_id": workspace_id,
                            "project_id": project_id,
                            "profile_id": profile_id,
                        },
                        created_at=datetime.utcnow(),
                        started_at=None,
                    )
                )

                return {
                    "status": "rerun_queued",
                    "original_execution_id": execution_id,
                    "execution_id": new_execution_id,
                    "playbook_code": playbook_code,
                    "execution_backend_hint": final_execution_backend,
                    "note": "Execution queued",
                }

        result = await playbook_executor.execute_playbook_run(
            playbook_code=playbook_code,
            profile_id=profile_id,
            inputs=merged_inputs,
            workspace_id=workspace_id,
            project_id=project_id,
        )

        if result.get("execution_mode") == "conversation":
            return result.get("result", result)

        return {
            "status": "rerun_started",
            "original_execution_id": execution_id,
            "execution_id": result.get("execution_id"),
            "playbook_code": playbook_code,
            **(result.get("result", {}) or {}),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to rerun execution: {str(e)}"
        )


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
