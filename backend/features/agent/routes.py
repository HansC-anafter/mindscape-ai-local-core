"""
Agent API routes
Handles AI agent execution endpoints
"""

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Path, Query

from backend.app.models.mindscape import (
    RunAgentRequest, AgentResponse, AgentExecution
)
from backend.app.services.agent_runner import AgentRunner

router = APIRouter(tags=["agent"])

# Initialize agent runner
agent_runner = AgentRunner()

# Create a separate router for backward compatibility
agents_router = APIRouter(prefix="/api/v1", tags=["agent"])


@router.post("/run", response_model=AgentResponse)
async def run_agent(
    profile_id: str = Query(..., description="Profile ID"),
    request: RunAgentRequest = None
):
    """Execute an AI agent with the given task"""
    if not request:
        raise HTTPException(status_code=400, detail="Run request required")

    if not request.task:
        raise HTTPException(status_code=400, detail="Task description required")

    valid_agent_types = ["planner", "writer", "coach", "coder", "visual_design_partner"]
    if request.agent_type not in valid_agent_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid agent type. Must be one of: {', '.join(valid_agent_types)}"
        )

    try:
        response = await agent_runner.run_agent(profile_id, request)
        return response

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent execution failed: {str(e)}")


@router.get("/executions/{execution_id}", response_model=AgentExecution)
async def get_execution(execution_id: str = Path(..., description="Execution ID")):
    """Get agent execution status by ID"""
    execution = await agent_runner.get_execution_status(execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")
    return execution


@router.get("/executions", response_model=List[AgentExecution])
async def list_executions(
    profile_id: str = Query(..., description="Profile ID"),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of executions to return")
):
    """List recent agent executions for a profile"""
    executions = await agent_runner.list_executions(profile_id, limit=limit)
    return executions


@router.get("/agents", response_model=List[dict])
async def list_available_agents():
    """Get list of available agent types"""
    agents = agent_runner.get_available_agents()
    return agents


@router.get("/agents/{agent_type}", response_model=dict)
async def get_agent_detail(agent_type: str = Path(..., description="Agent type")):
    """Get detailed information about a specific agent type, including AI team structure"""
    agent_detail = agent_runner.get_agent_detail(agent_type)
    if not agent_detail:
        raise HTTPException(status_code=404, detail=f"Agent type '{agent_type}' not found")
    return agent_detail


# Backward compatibility: also expose /api/v1/agents endpoint
@agents_router.get("/agents", response_model=List[dict])
async def list_available_agents_compat():
    """Get list of available agent types (backward compatibility endpoint)"""
    agents = agent_runner.get_available_agents()
    return agents


@agents_router.get("/agents/{agent_type}", response_model=dict)
async def get_agent_detail_compat(agent_type: str = Path(..., description="Agent type")):
    """Get detailed information about a specific agent type (backward compatibility endpoint)"""
    agent_detail = agent_runner.get_agent_detail(agent_type)
    if not agent_detail:
        raise HTTPException(status_code=404, detail=f"Agent type '{agent_type}' not found")
    return agent_detail


@router.get("/providers", response_model=List[str])
async def list_available_providers():
    """Get list of available LLM providers"""
    providers = agent_runner.get_available_providers()
    return providers


@router.post("/run-all", response_model=List[AgentResponse])
async def run_all_agents(
    profile_id: str = Query(..., description="Profile ID"),
    request: RunAgentRequest = None
):
    """Execute all AI agents in parallel for the same task"""
    if not request:
        raise HTTPException(status_code=400, detail="Run request required")

    if not request.task:
        raise HTTPException(status_code=400, detail="Task description required")

    try:
        # Run all agent types in parallel
        agent_types = ["planner", "writer", "coach", "coder", "visual_design_partner"]
        responses = await agent_runner.run_agents_parallel(
            profile_id=profile_id,
            task=request.task,
            agent_types=agent_types,
            use_mindscape=request.use_mindscape,
            intent_ids=request.intent_ids or []
        )
        return responses

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Parallel agent execution failed: {str(e)}")


@router.post("/suggest-scene", response_model=dict)
async def suggest_work_scene(
    profile_id: str = Query(..., description="Profile ID"),
    task: str = Query(..., description="Task description")
):
    """Use LLM to suggest the best work scene for a given task"""
    if not task:
        raise HTTPException(status_code=400, detail="Task description required")

    try:
        suggestion = await agent_runner.suggest_work_scene(profile_id, task)
        return suggestion

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scene suggestion failed: {str(e)}")
