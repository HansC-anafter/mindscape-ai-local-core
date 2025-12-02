"""
Playbook Execution API routes
Handles real-time Playbook execution with LLM conversations
"""

from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel

from ...services.playbook_runner import PlaybookRunner

router = APIRouter(prefix="/api/playbooks", tags=["playbook-execution"])

# Initialize playbook runner
playbook_runner = PlaybookRunner()


class ContinueExecutionRequest(BaseModel):
    """Request to continue playbook execution"""
    user_message: str


class StartExecutionRequest(BaseModel):
    """Request to start playbook execution"""
    inputs: Optional[dict] = None
    target_language: Optional[str] = None
    variant_id: Optional[str] = None


@router.post("/execute/start")
async def start_playbook_execution(
    playbook_code: str = Query(..., description="Playbook code to execute"),
    profile_id: str = Query("default-user", description="Profile ID"),
    target_language: Optional[str] = Query(None, description="Target language for output (e.g., 'zh-TW', 'en')"),
    variant_id: Optional[str] = Query(None, description="Optional personalized variant ID to use"),
    request: Optional[StartExecutionRequest] = Body(None, description="Optional inputs for the playbook")
):
    """
    Start a new Playbook execution

    Returns the execution_id and initial assistant message
    """
    try:
        inputs = request.inputs if request else None
        final_target_language = target_language or (request.target_language if request else None)
        final_variant_id = variant_id or (request.variant_id if request else None)
        result = await playbook_runner.start_playbook_execution(
            playbook_code=playbook_code,
            profile_id=profile_id,
            inputs=inputs,
            target_language=final_target_language,
            variant_id=final_variant_id
        )
        return result
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
