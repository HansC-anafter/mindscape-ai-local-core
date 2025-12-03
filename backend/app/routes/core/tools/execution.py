"""
Tool execution routes

Provides unified tool execution interface for Playbook integration.
Supports builtin, langchain, and MCP tools.
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Dict, Any, List, Optional
from pydantic import BaseModel

from backend.app.services.unified_tool_executor import UnifiedToolExecutor, ToolExecutionResult
from backend.app.services.playbook_tool_resolver import ToolDependencyResolver
from backend.app.models.playbook import ToolDependency
from .base import get_tool_registry, raise_api_error

router = APIRouter(prefix="/api/v1/tools", tags=["tools"])


def get_tool_executor() -> UnifiedToolExecutor:
    """
    Get UnifiedToolExecutor instance
    """
    return UnifiedToolExecutor()


def get_tool_resolver() -> ToolDependencyResolver:
    """
    Get ToolDependencyResolver instance
    """
    return ToolDependencyResolver()


class ExecuteToolRequest(BaseModel):
    """Request to execute a tool"""
    tool_name: str
    arguments: Dict[str, Any]
    timeout: Optional[float] = 30.0


class ExecuteToolDependencyRequest(BaseModel):
    """Request to execute a tool dependency"""
    tool_dependency: ToolDependency
    arguments: Dict[str, Any]
    env_overrides: Optional[Dict[str, str]] = None


@router.post("/execute", response_model=Dict[str, Any])
async def execute_tool(
    request: ExecuteToolRequest,
    profile_id: str = Query(..., description="Profile ID"),
    executor: UnifiedToolExecutor = Depends(get_tool_executor),
):
    """
    Execute a tool (unified interface for Playbook)

    Supports multiple tool types:
    - builtin: wordpress, notion, etc.
    - langchain: langchain.wikipedia, etc.
    - mcp: mcp.github.search_issues, etc.

    Args:
        request: Tool execution request
        profile_id: Profile ID
        executor: Unified tool executor

    Returns:
        Tool execution result

    Example:
        POST /api/v1/tools/execute?profile_id=user123
        {
            "tool_name": "wordpress.list_posts",
            "arguments": {"per_page": 10}
        }
    """
    try:
        result = await executor.execute_tool(
            tool_name=request.tool_name,
            arguments=request.arguments,
            timeout=request.timeout
        )
        return result.to_dict()
    except Exception as e:
        raise_api_error(500, f"Tool execution failed: {str(e)}")


@router.post("/execute-dependency", response_model=Dict[str, Any])
async def execute_tool_dependency(
    request: ExecuteToolDependencyRequest,
    profile_id: str = Query(..., description="Profile ID"),
    executor: UnifiedToolExecutor = Depends(get_tool_executor),
):
    """
    Execute a tool dependency (from Playbook configuration)

    Automatically handles:
    - Environment variable substitution
    - Tool lookup
    - Fallback mechanism

    Args:
        request: Tool dependency execution request
        profile_id: Profile ID
        executor: Unified tool executor

    Returns:
        Tool execution result
    """
    try:
        result = await executor.execute_tool_dependency(
            tool_dep=request.tool_dependency,
            arguments=request.arguments,
            env_overrides=request.env_overrides
        )
        return result.to_dict()
    except Exception as e:
        raise_api_error(500, f"Tool dependency execution failed: {str(e)}")


@router.post("/check-dependencies", response_model=Dict[str, Any])
async def check_tool_dependencies(
    tool_dependencies: List[ToolDependency],
    profile_id: str = Query(..., description="Profile ID"),
    resolver: ToolDependencyResolver = Depends(get_tool_resolver),
):
    """
    Check tool dependencies for Playbook

    Args:
        tool_dependencies: List of tool dependencies
        profile_id: Profile ID
        resolver: Tool dependency resolver

    Returns:
        Dependency check result with availability status
    """
    try:
        result = await resolver.resolve_dependencies(tool_dependencies)
        return result
    except Exception as e:
        raise_api_error(500, f"Dependency check failed: {str(e)}")


@router.post("/auto-install", response_model=Dict[str, Any])
async def auto_install_tool(
    tool_dep: ToolDependency,
    profile_id: str = Query(..., description="Profile ID"),
    resolver: ToolDependencyResolver = Depends(get_tool_resolver),
):
    """
    Auto-install a tool if possible

    Supports:
    - langchain tools: Auto-install via pip
    - mcp tools: Connect to MCP server

    Args:
        tool_dep: Tool dependency to install
        profile_id: Profile ID
        resolver: Tool dependency resolver

    Returns:
        Installation result
    """
    try:
        result = await resolver.auto_install_tool(tool_dep)
        return result
    except Exception as e:
        raise_api_error(500, f"Auto-install failed: {str(e)}")


@router.get("/execution-history", response_model=List[Dict[str, Any]])
async def get_execution_history(
    limit: Optional[int] = Query(None, description="Limit number of results"),
    executor: UnifiedToolExecutor = Depends(get_tool_executor),
):
    """
    Get tool execution history

    Args:
        limit: Limit number of results
        executor: Unified tool executor

    Returns:
        List of execution history records
    """
    try:
        history = executor.get_execution_history(limit=limit)
        return history
    except Exception as e:
        raise_api_error(500, f"Failed to get execution history: {str(e)}")


@router.get("/execution-statistics", response_model=Dict[str, Any])
async def get_execution_statistics(
    executor: UnifiedToolExecutor = Depends(get_tool_executor),
):
    """
    Get tool execution statistics

    Returns:
        Execution statistics (success rate, avg time, etc.)
    """
    try:
        stats = executor.get_statistics()
        return stats
    except Exception as e:
        raise_api_error(500, f"Failed to get statistics: {str(e)}")

