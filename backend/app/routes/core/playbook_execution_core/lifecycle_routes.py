import asyncio
from typing import Optional

from fastapi import APIRouter, Body, HTTPException, Query

from backend.app.routes.core.execution_schemas import (
    CancelExecutionRequest,
    ContinueExecutionRequest,
    ResumeExecutionRequest,
)
from backend.app.services.workspace_capability_admission.child_snapshot_verifier import (
    verify_child_snapshot,
)

from .state import _utc_now, logger, playbook_executor, playbook_runner

router = APIRouter()


@router.post("/execute/{execution_id}/continue")
async def continue_playbook_execution(
    execution_id: str,
    request: ContinueExecutionRequest = Body(...),
    profile_id: str = Query("default-user", description="Profile ID"),
):
    """Continue an ongoing conversational execution."""
    try:
        return await playbook_runner.continue_playbook_execution(
            execution_id=execution_id,
            user_message=request.user_message,
            profile_id=profile_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to continue playbook: {str(exc)}",
        ) from exc


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
        admission_snapshot = ctx.get("execution_admission_snapshot")
        if workspace_id:
            if not isinstance(admission_snapshot, dict):
                raise HTTPException(
                    status_code=409,
                    detail="execution_admission_snapshot_required",
                )
            verify_child_snapshot(
                admission_snapshot,
                expected_workspace_id=workspace_id,
                expected_root_execution_id=execution_id,
            )
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

        try:
            from backend.app.services.playbook_runner_core.run_state import (
                build_run_state_changed_event,
            )

            cancel_inputs = (
                task.params if isinstance(task.params, dict) else {}
            ) or (
                ctx.get("inputs") if isinstance(ctx.get("inputs"), dict) else {}
            )
            previous_state = (
                getattr(task.status, "value", task.status) or "running"
            )
            cancelled_event = build_run_state_changed_event(
                profile_id=task.profile_id,
                project_id=task.project_id,
                workspace_id=task.workspace_id,
                execution_id=execution_id,
                previous_state=str(previous_state).upper(),
                new_state="CANCELLED",
                reason="execution_cancelled",
                playbook_code=task.pack_id or "",
                inputs=cancel_inputs,
            )
            playbook_runner.store.create_event(cancelled_event)
        except Exception as emit_error:
            logger.warning(
                "Failed to emit CANCELLED RUN_STATE_CHANGED event for %s: %s",
                execution_id,
                emit_error,
            )

        return {"status": "cancelled", "execution_id": execution_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to cancel execution: {str(e)}"
        )


# Mount rerun handler from extracted module (main.py zero-change)
from backend.app.routes.core.playbook_rerun import rerun_playbook_execution

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
