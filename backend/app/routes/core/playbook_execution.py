"""
Playbook Execution API routes
Handles real-time Playbook execution with LLM conversations and structured workflows
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel

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
    auto_execute: Optional[bool] = None  # If True, skip confirmations and execute tools directly


@router.post("/execute/start")
async def start_playbook_execution(
    playbook_code: str = Query(..., description="Playbook code to execute"),
    profile_id: str = Query("default-user", description="Profile ID"),
    workspace_id: Optional[str] = Query(None, description="Workspace ID for state persistence (required for multi-turn conversations)"),
    project_id: Optional[str] = Query(None, description="Project ID for sandbox context"),
    target_language: Optional[str] = Query(None, description="Target language for output (e.g., 'zh-TW', 'en')"),
    variant_id: Optional[str] = Query(None, description="Optional personalized variant ID to use"),
    auto_execute: Optional[bool] = Query(None, description="If true, skip confirmations and execute tools directly"),
    request: Optional[StartExecutionRequest] = Body(None, description="Optional inputs for the playbook")
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
        final_target_language = target_language or (request.target_language if request else None)
        final_variant_id = variant_id or (request.variant_id if request else None)
        final_auto_execute = auto_execute or (request.auto_execute if request else None)

        # Extract workspace_id and project_id from inputs if not provided as query params
        final_workspace_id = workspace_id or (inputs.get("workspace_id") if inputs else None)
        final_project_id = project_id or (inputs.get("project_id") if inputs else None)

        # If no project_id provided, use workspace.primary_project_id as fallback
        if not final_project_id and final_workspace_id:
            try:
                from ...services.mindscape_store import MindscapeStore
                store = MindscapeStore()
                workspace = store.get_workspace(final_workspace_id)
                if workspace and hasattr(workspace, 'primary_project_id') and workspace.primary_project_id:
                    final_project_id = workspace.primary_project_id
                    logger.info(f"Using workspace.primary_project_id={final_project_id} for playbook {playbook_code}")
            except Exception as e:
                logger.warning(f"Failed to get workspace.primary_project_id: {e}")

        # Inject auto_execute into inputs for downstream processing
        if final_auto_execute and inputs:
            inputs["auto_execute"] = True
        elif final_auto_execute:
            inputs = {"auto_execute": True}

        # Update user_meta use_count when playbook is executed
        try:
            from ...services.mindscape_store import MindscapeStore
            store = MindscapeStore()
            store.update_user_meta(profile_id, playbook_code, {
                "increment_use_count": True,
                "last_used_at": datetime.utcnow().isoformat()
            })
        except Exception as e:
            logger.warning(f"Failed to update user_meta for playbook {playbook_code}: {e}")

        # Use unified executor (automatically selects execution mode)
        result = await playbook_executor.execute_playbook_run(
            playbook_code=playbook_code,
            profile_id=profile_id,
            inputs=inputs,
            workspace_id=final_workspace_id,
            project_id=final_project_id,
            target_language=final_target_language,
            variant_id=final_variant_id
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
                **result.get("result", {})
            }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start playbook: {str(e)}")


@router.post("/execute/{execution_id}/continue")
async def continue_playbook_execution(
    execution_id: str,
    request: ContinueExecutionRequest = Body(...),
    profile_id: str = Query("default-user", description="Profile ID")
):
    """
    Continue an ongoing Playbook execution with user response

    Returns the next assistant message and completion status
    """
    try:
        result = await playbook_runner.continue_playbook_execution(
            execution_id=execution_id,
            user_message=request.user_message,
            profile_id=profile_id
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to continue playbook: {str(e)}")


@router.get("/execute/{execution_id}/result")
async def get_playbook_result(execution_id: str):
    """
    Get the final structured output from a completed Playbook execution
    """
    result = await playbook_runner.get_playbook_execution_result(execution_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Execution not found or not completed")
    return result


@router.delete("/execute/{execution_id}")
async def cleanup_playbook_execution(execution_id: str):
    """
    Clean up a completed Playbook execution from memory
    """
    playbook_runner.cleanup_execution(execution_id)
    return {"status": "cleaned up"}


@router.post("/execute/{execution_id}/reset-step")
async def reset_current_step(
    execution_id: str,
    profile_id: str = Query("default-user", description="Profile ID")
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
            execution_id=execution_id,
            profile_id=profile_id
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
