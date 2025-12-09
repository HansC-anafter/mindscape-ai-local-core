"""
Playbook Execution API routes
Handles real-time Playbook execution with LLM conversations and structured workflows
"""

from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel

from ...services.playbook_run_executor import PlaybookRunExecutor
from ...services.playbook_runner import PlaybookRunner

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

        # Inject auto_execute into inputs for downstream processing
        if final_auto_execute and inputs:
            inputs["auto_execute"] = True
        elif final_auto_execute:
            inputs = {"auto_execute": True}

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
            # For workflow mode, return workflow result
            return {
                "execution_mode": result.get("execution_mode"),
                "playbook_code": result.get("playbook_code"),
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


@router.get("/execute/active")
async def list_active_executions():
    """
    List all active Playbook executions
    """
    execution_ids = playbook_runner.list_active_executions()
    return {"active_executions": execution_ids}
